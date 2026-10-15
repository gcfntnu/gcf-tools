"""Exact selected-cell behavior and publication failures on invented records."""
import hashlib
import json
import threading
from pathlib import Path

import pytest

from testdata import create_testdata as producer, parse_cells
from parse_fixture import parse_source
from producer_fixture import PROJECT, contents, records, write_records


def inspect(fixture):
    return producer.BFQoutput(fixture[0], libprep_config=fixture[1], project_id=PROJECT)


def test_exact_all_pairs_both_aliases_background_and_repeatable_hashes(tmp_path):
    fixture = parse_source(tmp_path / "input")
    before = contents(fixture[0])
    for name in ("one", "two"):
        inspect(fixture).sample_parse_cells(tmp_path / name, fixture[2])
    assert contents(tmp_path / "one") == contents(tmp_path / "two")
    output = tmp_path / "one"
    provenance = json.loads((output / "testdata.provenance.json").read_text())
    for library, expected in fixture[4].items():
        for mate in (1, 2):
            path = output / PROJECT / (library + "_R{}.fastq.gz".format(mate))
            actual = records(path)
            original = records(fixture[0] / PROJECT / path.name)
            assert [row[0].rsplit("/", 1)[0] for row in actual] == expected
            assert actual == [row for index, row in enumerate(original) if index % 8 < 6]
        stats = provenance["samples"][library]
        assert (stats["available_pairs"], stats["selected_pairs"]) == (24, 18)
        assert stats["cells"] == {"cellA": 6, "cellB": 6, "backgroundA": 3, "backgroundB": 3}
        assert sorted(stats["r2_keys"].values()) == [3] * 6
    assert provenance["selection_sha256"] == hashlib.sha256(fixture[2].read_bytes()).hexdigest()
    assert (output / "RunInfo.xml").read_bytes() == before["RunInfo.xml"]
    for relative, digest in provenance["source_sha256"].items():
        assert digest == hashlib.sha256((fixture[0] / relative).read_bytes()).hexdigest()
    for line in (output / ("md5sum_" + PROJECT + "_fastq.txt")).read_text().splitlines():
        digest, relative = line.split()
        assert digest == hashlib.md5((output / relative).read_bytes()).hexdigest()
    assert contents(fixture[0]) == before


@pytest.mark.parametrize("damage", ["unknown_field", "version", "profile", "lengths", "minimum", "empty_libraries",
    "unknown_library", "unknown_bio", "extra_bio", "wells", "duplicate_cell", "duplicate_key", "bad_key",
    "bad_role", "empty_cells", "missing_signal_sample"])
def test_strict_manifest_rejects_before_staging(tmp_path, damage):
    fixture = parse_source(tmp_path / "input")
    data = json.loads(fixture[2].read_text())
    cells = data["sublibraries"]["001"]["cells"]
    if damage == "unknown_field": data["ignored"] = True
    elif damage in ("version", "profile", "lengths", "minimum"):
        key, value = {"version": ("schema_version", True), "profile": ("profile", "other"),
                      "lengths": ("read_lengths", [75, 58]), "minimum": ("minimum_signal_pairs", 0)}[damage]
        data[key] = value
    elif damage == "empty_libraries": data["sublibraries"] = {}
    elif damage == "unknown_library": data["sublibraries"]["missing"] = data["sublibraries"].pop("001")
    elif damage == "unknown_bio": cells[0]["biological_sample"] = "missing"
    elif damage == "extra_bio": data["biological_samples"]["extra"] = {"wells": "C1"}
    elif damage == "wells": data["biological_samples"]["001"] = {"wells": "C1"}
    elif damage == "duplicate_cell": cells[1]["cell_id"] = cells[0]["cell_id"]
    elif damage == "duplicate_key": cells[1]["r2_keys"] = cells[0]["r2_keys"]
    elif damage == "bad_key": cells[0]["r2_keys"] = ["N" * 24]
    elif damage == "bad_role": cells[0]["role"] = "unknown"
    elif damage == "empty_cells": data["sublibraries"]["001"]["cells"] = []
    else: cells[1]["role"] = "background"
    fixture[2].write_text(json.dumps(data))
    before = contents(tmp_path)
    with pytest.raises(ValueError): inspect(fixture).sample_parse_cells(tmp_path / "output", fixture[2])
    assert contents(tmp_path) == before
    assert not list(tmp_path.glob(".*-stage-*"))


def test_duplicate_json_keys_rejected(tmp_path):
    fixture = parse_source(tmp_path / "input")
    fixture[2].write_text(fixture[2].read_text().replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        inspect(fixture).sample_parse_cells(tmp_path / "output", fixture[2])


@pytest.mark.parametrize("change", ["geometry", "chemistry", "assay", "method"])
def test_wrong_source_profile_is_rejected(tmp_path, change):
    fixture = parse_source(tmp_path / "input")
    if change == "geometry":
        path = fixture[0] / "Stats/Stats.json"
        path.write_text(path.read_text().replace('"NumCycles": 64', '"NumCycles": 63'))
    else:
        replacement = {"chemistry": ("chemistry: v4", "chemistry: v3"), "assay": ("assay: wt", "assay: tcr"),
                       "method": ("method: splitpipe", "method: parsebio_starsolo")}[change]
        fixture[1].write_text(fixture[1].read_text().replace(*replacement))
    with pytest.raises(ValueError, match="WT v4 gene expression"):
        inspect(fixture).sample_parse_cells(tmp_path / "output", fixture[2])
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("damage", ["unselected_bad_quality", "unselected_wrong_geometry", "minimum", "empty"])
def test_full_stream_validation_and_minimum_fail_without_publication(tmp_path, damage):
    fixture = parse_source(tmp_path / "input")
    if damage == "minimum":
        selection = json.loads(fixture[2].read_text());selection["minimum_signal_pairs"] = 7
        fixture[2].write_text(json.dumps(selection))
    else:
        path = fixture[0] / PROJECT / "001_R2.fastq.gz"
        rows = [list(row) for row in records(path)]
        if damage == "unselected_bad_quality": rows[-1][3] = " " + rows[-1][3][1:]
        elif damage == "unselected_wrong_geometry":
            rows[-1][1] = rows[-1][1][:-1];rows[-1][3] = rows[-1][3][:-1]
        else:
            import gzip
            for mate in (1, 2): (fixture[0] / PROJECT / ("001_R{}.fastq.gz".format(mate))).write_bytes(gzip.compress(b""))
        if damage != "empty": write_records(path, rows)
    before = contents(fixture[0])
    with pytest.raises(ValueError): inspect(fixture).sample_parse_cells(tmp_path / "output", fixture[2])
    assert contents(fixture[0]) == before
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".*-stage-*"))


def test_worker_cancellation_is_polled_and_partial_outputs_are_not_published(tmp_path, monkeypatch):
    fixture = parse_source(tmp_path / "input")
    cancel = threading.Event();seen = []
    def long_stream(*args):
        first = b"@synthetic/1\n" + b"A" * 64 + b"\n+\n" + b"I" * 64 + b"\n"
        second = b"@synthetic/2\n" + b"A" * 58 + b"\n+\n" + b"I" * 58 + b"\n"
        for number in range(100000):
            if number == 3: cancel.set()
            seen.append(number)
            yield b"synthetic", first, second
    monkeypatch.setattr(parse_cells, "paired_records", long_stream)
    data = json.loads(fixture[2].read_text());project = tmp_path / "worker";project.mkdir()
    with pytest.raises(parse_cells._Cancelled):
        parse_cells._filter_library("001", [], data["sublibraries"]["001"]["cells"], 4, project, cancel)
    assert len(seen) == 10000 and cancel.is_set()


def test_selection_change_after_workers_and_existing_destination_are_protected(tmp_path, monkeypatch):
    fixture = parse_source(tmp_path / "input")
    existing = tmp_path / "existing";existing.mkdir();(existing / "sentinel").write_text("preserve")
    with pytest.raises(FileExistsError): inspect(fixture).sample_parse_cells(existing, fixture[2], overwrite=True)
    assert (existing / "sentinel").read_text() == "preserve"
    original = parse_cells._extract_libraries
    def changed(*args):
        result = original(*args);fixture[2].write_text(fixture[2].read_text() + "\n");return result
    monkeypatch.setattr(parse_cells, "_extract_libraries", changed)
    with pytest.raises(ValueError, match="Input changed"):
        inspect(fixture).sample_parse_cells(tmp_path / "output", fixture[2])
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".*-stage-*"))


@pytest.mark.parametrize("damage", ["absent", "allblank", "partial"])
def test_prepared_wells_must_be_present_and_nonempty(tmp_path, damage):
    from openpyxl import load_workbook
    fixture = parse_source(tmp_path / "input")
    path = fixture[0] / "Sample-Submission-Form.xlsx"
    book = load_workbook(path);sheet = book["Cell Multiplexing"]
    if damage == "absent": sheet.delete_cols(2)
    else:
        sheet["B2"] = None
        if damage == "allblank": sheet["B3"] = None
    book.save(path)
    with pytest.raises(ValueError, match="Wells"):
        inspect(fixture).sample_parse_cells(tmp_path / "output", fixture[2])
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".*-stage-*"))


def test_runinfo_is_optional_copied_without_geometry_fallback(tmp_path):
    fixture = parse_source(tmp_path / "input")
    (fixture[0] / "RunInfo.xml").unlink()
    output = inspect(fixture).sample_parse_cells(tmp_path / "output", fixture[2])
    assert not (output / "RunInfo.xml").exists()
    (fixture[0] / "RunInfo.xml").write_text("opaque optional bytes")
    (fixture[0] / "Stats/Stats.json").unlink()
    with pytest.raises(OSError): inspect(fixture)
