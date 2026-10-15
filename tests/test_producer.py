"""Real paired records and failure preservation; only injected faults are mocked."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil

import pytest

from configmaker.libprep import LibprepConfigError
from configmaker.validation import InputValidationError, validate_inputs
from testdata import create_testdata as producer
from producer_fixture import PROJECT, contents, modern_source, records, write_records


@pytest.fixture
def source(tmp_path):
    return modern_source(tmp_path / "source")


def inspect(source):
    run, config = source
    return producer.BFQoutput(run, libprep_config=config, project_id=PROJECT)


def generate(source, output, **kwargs):
    options = dict(samples="001,CTRL", n_reads=8, no_fastq_rename=True)
    options.update(kwargs)
    return inspect(source).sample(output, **options)


def assert_no_stage(parent):
    assert not list(parent.glob(".*-stage-*"))


def test_parser_preserves_arguments_and_explicit_restrictions(source, tmp_path):
    parser = producer.create_argparser()
    args = parser.parse_args(["source", "--output", "result", "--samples", "001,CTRL",
                             "--n-reads", "8", "--n-samples", "2", "--no-fastq-rename",
                             "--libprep-config", "kits.yaml", "--project-id", PROJECT,
                             "--seed", "42", "--verbose"])
    assert vars(args) == dict(runfolder="source", output="result", samples="001,CTRL",
                             n_reads=8, n_samples=2, no_fastq_rename=True,
                             libprep_config="kits.yaml", project_id=PROJECT, seed=42, verbose=True)
    defaults = parser.parse_args(["source"])
    assert (defaults.n_reads, defaults.n_samples, defaults.seed) == (1000, 3, 123456)
    run, config = source
    with pytest.raises(ValueError, match="project-id"):
        producer.BFQoutput(run, libprep_config=config)
    with pytest.raises(ValueError, match="downloads are disabled"):
        producer.BFQoutput(run, project_id=PROJECT)
    assert_no_stage(tmp_path)


def test_exact_ids_metadata_authority_geometry_selection_and_source_immutability(source, tmp_path):
    run, config = source
    # These stale derived/legacy artifacts must not override curated metadata.
    (run / (PROJECT + "_samplesheet.tsv")).write_text("Sample_ID\n1\nWRONG\n")
    (run / "bcl.done").write_text("synthetic obsolete marker")
    (run / "state.json").write_text("synthetic state placeholder, never copied")
    config.write_text("Synthetic SE:\n  workflow: wrong\nSynthetic PE:\n  workflow: rnaseq\n")
    before = contents(run)
    obj = inspect(source)
    assert obj.pipeline == "rnaseq"
    assert obj.fastq_files["001"] == ["001_R1.fastq.gz", "001_R2.fastq.gz"]
    output = obj.sample(tmp_path / "output", samples="001", n_reads=9, no_fastq_rename=True)
    assert set(p.name for p in (output / PROJECT).iterdir()) == {"001_R1.fastq.gz", "001_R2.fastq.gz"}
    assert not (output / "bcl.done").exists()
    assert not (output / "state.json").exists()
    assert not (output / (PROJECT + "_samplesheet.tsv")).exists()
    assert contents(run) == before
    validation = validate_inputs(output / "SampleSheet.csv", output / "Sample-Submission-Form.xlsx")
    assert validation.ok
    assert validation.samples.Sample_ID.tolist() == ["001"]
    assert (output / "Sample-Submission-Form.xlsx").read_bytes() == before["Sample-Submission-Form.xlsx"]
    assert (output / "Stats/Stats.json").read_bytes() == before["Stats/Stats.json"]


@pytest.mark.parametrize("content", ["- wrong\n", "!!python/object/apply:os.system ['false']",
                                      "Unknown PE:\n  workflow: rnaseq\n"])
def test_local_configuration_failures_do_not_download_or_write(source, tmp_path, content):
    source[1].write_text(content)
    before = contents(tmp_path)
    with pytest.raises(LibprepConfigError):
        generate(source, tmp_path / "output")
    assert contents(tmp_path) == before


@pytest.mark.parametrize("options,match", [
    ({"samples": None}, "Explicit --samples"), ({"samples": "001,001"}, "duplicate"),
    ({"samples": "001, 001A"}, "path component"), ({"samples": "1"}, "Unknown exact"),
    ({"samples": ""}, "path component"), ({"samples": "../escape"}, "path component"),
    ({"n_reads": 0}, "positive integer"), ({"n_reads": -1}, "positive integer"),
    ({"n_reads": True}, "positive integer"), ({"no_fastq_rename": False}, "no-fastq-rename"),
    ({"seed": 1.5}, "integer"),
])
def test_bad_selection_fails_before_output(source, tmp_path, options, match):
    before = contents(tmp_path)
    with pytest.raises(ValueError, match=match):
        generate(source, tmp_path / "output", **options)
    assert contents(tmp_path) == before
    assert_no_stage(tmp_path)


@pytest.mark.parametrize("project", ["../escape", "/absolute", "..", "A/B", "A B", "A,B"])
def test_project_cannot_escape_source(source, project):
    with pytest.raises(ValueError, match="path component"):
        producer.BFQoutput(source[0], libprep_config=source[1], project_id=project)


def test_deterministic_pairs_counts_bytes_and_checksums(source, tmp_path):
    first = generate(source, tmp_path / "one")
    second = generate(source, tmp_path / "two", samples="CTRL,001")
    third = generate(source, tmp_path / "three", seed=9876)
    assert contents(first) == contents(second)
    for sample in ("001", "CTRL"):
        selected = []
        for mate in (1, 2):
            relative = f"{PROJECT}/{sample}_R{mate}.fastq.gz"
            actual = records(first / relative)
            original = records(source[0] / relative)
            assert len(actual) == 8
            positions = [original.index(record) for record in actual]
            assert positions == sorted(set(positions))
            selected.append([record[0].rsplit("/", 1)[0] for record in actual])
            assert (first / relative).read_bytes() != (third / relative).read_bytes()
        assert selected[0] == selected[1]
    provenance = json.loads((first / "testdata.provenance.json").read_text())
    assert provenance["samples"] == {sid: {"available_pairs": 24, "selected_pairs": 8} for sid in ("001", "CTRL")}
    assert "original-source" in provenance["statistics"]
    manifest = dict(line.split()[::-1] for line in (first / f"md5sum_{PROJECT}_fastq.txt").read_text().splitlines())
    assert len(manifest) == 4
    for filename, digest in manifest.items():
        assert hashlib.md5((first / filename).read_bytes()).hexdigest() == digest
        assert hashlib.sha256((first / filename).read_bytes()).hexdigest() == provenance["output_fastq_sha256"][filename]
    for filename, digest in provenance["source_sha256"].items():
        assert hashlib.sha256((source[0] / filename).read_bytes()).hexdigest() == digest
    small = generate(source, tmp_path / "all", n_reads=999)
    assert records(small / PROJECT / "001_R1.fastq.gz") == records(source[0] / PROJECT / "001_R1.fastq.gz")
    assert json.loads((small / "testdata.provenance.json").read_text())["samples"]["001"]["selected_pairs"] == 24


@pytest.mark.parametrize("damage,match", [
    ("reordered", "IDs/order"), ("missing_pair", "counts differ"),
    ("empty", "empty"), ("truncated_record", "Incomplete"),
    ("bad_header", "header"), ("bad_separator", "separator"),
    ("bad_sequence", "sequence"), ("bad_quality", "quality"),
    ("short_quality", "quality"), ("wrong_mate", "mate label"),
    ("truncated_gzip", "gzip"), ("unselected_last", "quality"),
])
def test_all_pair_records_are_validated_and_fail_without_writes(source, tmp_path, damage, match):
    first = source[0] / PROJECT / "001_R1.fastq.gz"
    second = source[0] / PROJECT / "001_R2.fastq.gz"
    rows = [list(row) for row in records(second)]
    if damage == "reordered":
        rows.reverse()
    elif damage == "missing_pair":
        rows.pop()
    elif damage == "empty":
        first.write_bytes(gzip.compress(b"", mtime=0)); rows = []
    elif damage in ("bad_quality", "unselected_last"):
        rows[-1][3] = " " + rows[-1][3][1:]
    elif damage == "short_quality":
        rows[-1][3] = "I"
    elif damage == "bad_header":
        rows[-1][0] = "missing at sign"
    elif damage == "bad_separator":
        rows[-1][2] = "+wrong"
    elif damage == "bad_sequence":
        rows[-1][1] = "X" + rows[-1][1][1:]
    elif damage == "wrong_mate":
        rows[-1][0] = rows[-1][0][:-1] + "1"
    if rows:
        write_records(second, rows)
    else:
        second.write_bytes(gzip.compress(b"", mtime=0))
    if damage == "truncated_record":
        second.write_bytes(gzip.compress(b"@incomplete/2\nACGT\n+\n", mtime=0))
    elif damage == "truncated_gzip":
        second.write_bytes(second.read_bytes()[:-5])
    if damage == "unselected_last":
        # Independent fixed-seed expectation: reservoir(24, N=1, seed123456)
        # retains zero-based position16; damage at23 must still be rejected.
        import random
        rng, position = random.Random(123456), 0
        for index in range(1, 24):
            if rng.randrange(index + 1) == 0:
                position = index
        assert position == 16 and position != 23
    before = contents(tmp_path)
    with pytest.raises(ValueError, match=match):
        generate(source, tmp_path / "output", samples="001", n_reads=1)
    assert contents(tmp_path) == before
    assert not (tmp_path / "output").exists()
    assert_no_stage(tmp_path)


@pytest.mark.parametrize("style", ["unlabeled", "illumina", "both", "contradictory"])
def test_supported_read_id_conventions(source, tmp_path, style):
    for mate in (1, 2):
        path = source[0] / PROJECT / f"001_R{mate}.fastq.gz"
        rows = [list(row) for row in records(path)]
        for row in rows:
            if style in ("unlabeled", "illumina"):
                row[0] = row[0].rsplit("/", 1)[0]
            if style in ("illumina", "both", "contradictory"):
                row[0] += f" {3 - mate if style == 'contradictory' else mate}:N:0:ACGT"
        write_records(path, rows)
    if style == "contradictory":
        with pytest.raises(ValueError, match="mate label"):
            generate(source, tmp_path / "output", samples="001")
    else:
        output = generate(source, tmp_path / "output", samples="001")
        assert len(records(output / PROJECT / "001_R1.fastq.gz")) == 8


@pytest.mark.parametrize("layout", ["lane", "chunk", "nested", "extra_index", "directory_link"])
def test_unsupported_layouts_fail(source, tmp_path, layout):
    project = source[0] / PROJECT
    first = project / "001_R1.fastq.gz"
    if layout == "lane":
        first.rename(project / "001_S1_L001_R1_001.fastq.gz")
    elif layout == "chunk":
        shutil.copyfile(first, project / "001_S1_R1_002.fastq.gz")
    elif layout == "nested":
        (project / "001").mkdir()
    elif layout == "extra_index":
        shutil.copyfile(first, project / "001_I1.fastq.gz")
    else:
        (project / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    before = contents(source[0])
    with pytest.raises(ValueError, match="Unsupported FASTQ"):
        generate(source, tmp_path / "output")
    assert contents(source[0]) == before
    assert not (tmp_path / "output").exists()


def test_file_links_and_spaces_make_regular_self_contained_output(tmp_path):
    source = modern_source(tmp_path / "source with spaces")
    external = tmp_path / "linked target with spaces.fastq.gz"
    first = source[0] / PROJECT / "001_R1.fastq.gz"
    first.rename(external)
    first.symlink_to(external)
    before = external.read_bytes()
    output = generate(source, tmp_path / "result with spaces", samples="001")
    actual = output / PROJECT / first.name
    assert actual.is_file() and not actual.is_symlink()
    assert external.read_bytes() == before and first.is_symlink()
    assert len(records(actual)) == 8


@pytest.mark.parametrize("kind", ["broken", "same_mate", "metadata_link", "stats_dir_link"])
def test_unsafe_or_broken_links_refuse_without_output(source, tmp_path, kind):
    first = source[0] / PROJECT / "001_R1.fastq.gz"
    if kind == "broken":
        first.unlink(); first.symlink_to(tmp_path / "absent")
    elif kind == "same_mate":
        second = first.with_name("001_R2.fastq.gz")
        second.unlink(); second.symlink_to(first)
    elif kind == "metadata_link":
        path = source[0] / "SampleSheet.csv"
        path.rename(tmp_path / "metadata.csv"); path.symlink_to(tmp_path / "metadata.csv")
    else:
        path = source[0] / "Stats"
        path.rename(tmp_path / "stats"); path.symlink_to(tmp_path / "stats", target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        generate(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()
    assert_no_stage(tmp_path)


@pytest.mark.parametrize("kind", ["source", "ancestor", "descendant", "existing", "empty", "broken_link", "alias_parent", "missing_parent"])
def test_destinations_are_never_deleted(source, tmp_path, kind):
    if kind == "source":
        output = source[0]
    elif kind == "ancestor":
        output = tmp_path
    elif kind == "descendant":
        output = source[0] / "new"
    elif kind == "alias_parent":
        alias = tmp_path / "alias"
        alias.symlink_to(source[0], target_is_directory=True)
        output = alias / "new"
    elif kind == "missing_parent":
        output = tmp_path / "absent/new"
    else:
        output = tmp_path / "output"
        if kind == "broken_link":
            output.symlink_to(tmp_path / "absent")
        else:
            output.mkdir()
            if kind == "existing":
                (output / "sentinel").write_text("keep")
    before = contents(source[0])
    with pytest.raises((ValueError, OSError)):
        generate(source, output, overwrite=True)
    assert contents(source[0]) == before
    if kind == "existing":
        assert (output / "sentinel").read_text() == "keep"
    if kind == "empty":
        assert output.is_dir() and not list(output.iterdir())
    if kind == "broken_link":
        assert output.is_symlink()
    assert_no_stage(tmp_path)


@pytest.mark.parametrize("which", ["fastq", "metadata", "config", "link_target"])
def test_source_change_during_generation_is_detected(source, tmp_path, monkeypatch, which):
    original = producer.sample_pairs
    if which == "link_target":
        path = source[0] / PROJECT / "001_R1.fastq.gz"
        target = tmp_path / "target.fastq.gz"
        path.rename(target); path.symlink_to(target)
    else:
        target = {"fastq": source[0] / PROJECT / "001_R1.fastq.gz",
                  "metadata": source[0] / "SampleSheet.csv", "config": source[1]}[which]
    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        target.write_bytes(target.read_bytes() + b"\n")
        return value
    monkeypatch.setattr(producer, "sample_pairs", changed)
    with pytest.raises(ValueError, match="Input changed"):
        generate(source, tmp_path / "output", samples="001")
    assert not (tmp_path / "output").exists()
    assert_no_stage(tmp_path)


@pytest.mark.parametrize("fault", ["write", "publish", "rival"])
def test_staged_failures_and_competing_empty_destination_preserve_source(source, tmp_path, monkeypatch, fault):
    output = tmp_path / "output"
    before = contents(source[0])
    if fault == "write":
        def fail(*args, **kwargs):
            raise OSError("injected disk failure")
        monkeypatch.setattr(producer.gzip.GzipFile, "write", fail)
    else:
        original = producer.publish_noreplace
        def fail(stage, destination):
            if fault == "rival":
                destination.mkdir()
                return original(stage, destination)
            raise OSError("injected publication failure")
        monkeypatch.setattr(producer, "publish_noreplace", fail)
    with pytest.raises(OSError):
        generate(source, output)
    assert contents(source[0]) == before
    assert_no_stage(tmp_path)
    if fault == "rival":
        assert output.is_dir() and list(output.iterdir()) == []
    else:
        assert not output.exists()


def test_csv_filter_preserves_quoted_values_sections_and_exact_project(source, tmp_path):
    run, _ = source
    sheet = run / "SampleSheet.csv"
    text = sheet.read_text().replace("[Data]", "[BCLConvert_Data]")
    text = text.replace("Sample_ID,Sample_Project", "Sample_ID,Sample_Project,Description")
    text = text.replace("001," + PROJECT, '001,' + PROJECT + ',"quoted, field\nsecond line"')
    text += "[Settings]\nPreserve,yes\n"
    sheet.write_text(text)
    output = generate(source, tmp_path / "output", samples="001")
    rows = list(csv.reader(io.StringIO((output / "SampleSheet.csv").read_text())))
    assert ["001", PROJECT, "quoted, field\nsecond line"] in rows
    assert ["[Settings]"] in rows and ["Preserve", "yes"] in rows
    assert not any(row and row[0] in ("001A", "CTRL") for row in rows)


def test_explicit_project_ignores_experiment_name_and_filters_other_projects(source, tmp_path):
    sheet = source[0] / "SampleSheet.csv"
    text = sheet.read_text().replace("ExperimentName," + PROJECT, "ExperimentName,not-the-project")
    sheet.write_text(text + "OTHER,GCF-2099-002\n")
    output = generate(source, tmp_path / "output", samples="001")
    validation = validate_inputs(output / "SampleSheet.csv", output / "Sample-Submission-Form.xlsx")
    assert validation.ok
    assert validation.samples.Sample_ID.tolist() == ["001"]
    assert validation.samples.Project_ID.tolist() == [[PROJECT]]
    assert "OTHER" not in (output / "SampleSheet.csv").read_text()


def test_shared_metadata_failure_precedes_generation(source, tmp_path):
    sheet = source[0] / "SampleSheet.csv"
    sheet.write_text(sheet.read_text() + "ABSENT," + PROJECT + "\n")
    before = contents(tmp_path)
    with pytest.raises(InputValidationError, match="ABSENT"):
        generate(source, tmp_path / "output")
    assert contents(tmp_path) == before
    assert not (tmp_path / "output").exists()
