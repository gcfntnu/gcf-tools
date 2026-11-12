"""Synthetic sheet-only intake/CSV contracts, including SS Manager PR #19 cases."""

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from configmaker import __version__
from configmaker.indexes import normalize_indexes
from configmaker.samplesheet import SHEET_API_VERSION, validate_samplesheet, validate_samplesheet_bytes
from configmaker.validation import VALIDATION_API_VERSION, validate_inputs
from test_validation import customer_row, submission_form

PROJECT = "GCF-2099-001"
COLUMNS = ["Sample_ID", "Sample_Name", "index", "index2", "Sample_Project"]
ROWS = [["SAMPLE_A", "SAMPLE_A", "ACGTTGCA", "TTAACCGG", PROJECT],
        ["SAMPLE_B", "SAMPLE_B", "AGTCCGTA", "CCAATTGG", PROJECT]]
PREFIX = "[Header]\nIEMFileVersion,4\n[Reads]\n151\n151\n[Settings]\nAdapter,ACGTACGT\nAdapterRead2,TTAACCGG\n"


def sheet(rows=None, columns=None, prefix=PREFIX, section="Data"):
    output = io.StringIO(newline="")
    output.write(prefix)
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerows([["[{}]".format(section)], COLUMNS if columns is None else columns,
                     *(ROWS if rows is None else rows)])
    return output.getvalue().encode("utf-8")


def check(content, profile="portable-converter"):
    result = validate_samplesheet_bytes(content, source="synthetic-upload.csv", profile=profile)
    report = result.to_dict()
    json.dumps(report, ensure_ascii=False)
    assert report["kind"] == "samplesheet" and report["sheet_api_version"] == SHEET_API_VERSION == 1
    assert report["schema_version"] == 1 and report["validator"]["version"] == __version__
    assert result.ok == (report["status"] == "passed") == (not report["errors"])
    assert report["inputs"] == [dict(kind="samplesheet", path="synthetic-upload.csv",
                                     sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))]
    assert report["summary"]["validation_complete"] == result.ok
    assert "physical_run" in report["summary"]["deferred_checks"]
    assert result.render_text().startswith("SampleSheet preflight ({})".format(profile))
    return result


def codes(result, severity="error"):
    return {item["code"] for item in result.findings if item["severity"] == severity}


def contract_case(case):
    rows, columns, prefix, section = copy.deepcopy(ROWS), list(COLUMNS), PREFIX, "Data"
    if case in ("zero-prefixed-id", "punctuation-id", "outer-whitespace-id", "non-ascii-id", "literal-na-id"):
        rows[0][0] = rows[0][1] = {"zero-prefixed-id": "001", "punctuation-id": "SAMPLE.A",
            "outer-whitespace-id": " SAMPLE_A ", "non-ascii-id": "SAMPLE_Æ", "literal-na-id": "NA"}[case]
    elif case in ("index-prefix", "index-n"):
        rows[0][2] = "ACGT!GCA" if case == "index-prefix" else "ACGTNGCA"
    elif case == "lane-text":
        columns.insert(0, "Lane")
        rows = [["lane1", *rows[0]], ["lane2", *rows[1]]]
    elif case == "distinct-lanes":
        columns.insert(0, "Lane")
        rows = [["1", *rows[0]], ["2", *rows[0]]]
    elif case in ("multiple-oligos", "exact-duplicate"):
        rows[1][0:2] = rows[0][0:2]
        if case == "exact-duplicate":
            rows[1] = list(rows[0])
    elif case == "two-singleton-projects":
        rows[1][-1] = "GCF-2099-002"
    elif case == "four-digit-counter":
        for row in rows:
            row[-1] = "GCF-2099-1000"  # Facility numbering policy belongs to SS Manager.
    elif case in ("quoted-description", "unicode-description"):
        columns.insert(0, "Description")
        rows = [["synthetic, note" if case == "quoted-description" else "synthetic æ", *rows[0]], ["plain", *rows[1]]]
    elif case == "custom-options":
        prefix += '[CustomOptions]\nLibprep,Synthetic friendly kit\nPriority,0.25\nInitialHold,True\nFutureOption,"synthetic, value"\n'
    elif case == "conflicting-option":
        prefix += "[CustomOptions]\nFutureOption,first\nFutureOption,second\n"
    elif case == "unknown-section":
        prefix += '[Synthetic_Metadata]\nLabel,"synthetic, value"\n'
    elif case == "bcl-convert-v2":
        prefix = prefix.replace("[Reads]\n151\n151\n", "").replace("[Settings]", "[BCLConvert_Settings]")
        section = "BCLConvert_Data"
    content = sheet(rows, columns, prefix, section)
    if case == "utf8-bom":
        content = b"\xef\xbb\xbf" + content
    if case == "semicolon":
        content = content.replace(b",", b";")
    return content


@pytest.mark.parametrize("case,error", [
    ("iem", None), ("zero-prefixed-id", None), ("punctuation-id", "sample.invalid_portable_id"),
    ("outer-whitespace-id", "sample.invalid_portable_id"), ("non-ascii-id", "sample.non_ascii_id"),
    ("literal-na-id", None), ("index-prefix", "index.invalid_sequence"), ("index-n", None),
    ("lane-text", "samplesheet.invalid_lane"), ("distinct-lanes", None), ("multiple-oligos", None),
    ("exact-duplicate", "sample.duplicate_definition"), ("two-singleton-projects", None),
    ("four-digit-counter", None), ("quoted-description", None), ("unicode-description", None),
    ("custom-options", None), ("conflicting-option", "samplesheet.conflicting_option"),
    ("unknown-section", None), ("bcl-convert-v2", None), ("utf8-bom", None),
    ("semicolon", "samplesheet.missing_columns"),
])
def test_contract_targets(case, error):
    result = check(contract_case(case))
    if error:
        assert not result.ok and error in codes(result), result.render_text()
    else:
        assert result.ok, result.render_text()
        assert result.assignments
    if case == "index-n":
        assert result.assignments[0]["index"] == "ACGTNGCA"
    if case == "zero-prefixed-id":
        assert result.assignments[0]["sample_id"] == "001"
    if case == "literal-na-id":
        assert result.assignments[0]["sample_id"] == "NA"
    if case == "unknown-section":
        assert "samplesheet.unknown_section" in codes(result, "info")
    if case == "two-singleton-projects":
        assert result.summary["sample_count"] == 2 and len(result.summary["project_ids"]) == 2


@pytest.mark.parametrize("case", ["punctuation-id", "outer-whitespace-id", "index-prefix", "lane-text"])
def test_strict_profile_is_opt_in_and_needs_no_workbook(case):
    result = check(contract_case(case), profile="metadata")
    assert result.ok, result.render_text()
    assert result.assignments == []
    assert "input.missing_submission_form" not in codes(result)


def test_preserved_cells_round_trip_with_preamble_unknowns_blanks_and_multiline_values():
    prefix = ('preamble,"synthetic, context"\r\n\r\n[Header],,\r\nIEMFileVersion,4\r\n'
              '[CustomOptions]\r\nFutureTrue,TrUe\r\nFutureFalse,false\r\nFutureBlank,\r\n'
              'FutureDecimal,1e-05\r\nFutureSpace,  kept  \r\nFutureNote,"synthetic, \'quoted\'\r\nsecond line æ"\r\n'
              '[Synthetic_Metadata]\r\nlabel,"a ""quote""",extra\r\n')
    content = b"\xef\xbb\xbf" + sheet([["001", "001", "acgtn", "ttaa", PROJECT, 'text, "quote"\nline æ', ""]],
                                     COLUMNS + ["Description", ""], prefix=prefix)
    result = check(content)
    assert result.ok, result.render_text()
    expected = list(csv.reader(io.StringIO(content.decode("utf-8-sig"), newline="")))
    assert [row["cells"] for row in result.document["rows"]] == expected
    assert result.document["bom"] and result.document["columns"][-1] == ""
    assert [item["value"] for item in result.custom_options] == ["TrUe", "false", "", "1e-05", "  kept  ", "synthetic, 'quoted'\r\nsecond line æ"]
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\r\n").writerows(row["cells"] for row in result.document["rows"])
    repeated = check(output.getvalue().encode())
    assert repeated.ok and [row["cells"] for row in repeated.document["rows"]] == expected
    assert result.assignments[0]["index"] == "ACGTN" and result.assignments[0]["index2"] == "TTAA"
    assert result.assignments[0]["index_provenance"]["original_index"] == "acgtn"


def test_diagnostics_use_original_physical_start_and_end_lines():
    content = sheet([["SAMPLE.A", "SAMPLE.A", "ACGT!", "TTAA", PROJECT, "first\nsecond"]],
                    COLUMNS + ["Description"], prefix="[Header]\nIEMFileVersion,4\n")
    result = check(content)
    findings = {item["code"]: item for item in result.findings if item["severity"] == "error"}
    for code, column, value in [("sample.invalid_portable_id", "Sample_ID", "SAMPLE.A"), ("index.invalid_sequence", "index", "ACGT!")]:
        finding = findings[code]
        assert (finding["row"], finding["end_row"], finding["column"], finding["details"]["value"]) == (5, 6, column, value)
        assert finding["file"] == "synthetic-upload.csv"
    bad = check(content.replace(b"SAMPLE.A", "SAMPLE_Æ".encode()))
    finding = next(item for item in bad.findings if item["code"] == "sample.non_ascii_id")
    assert (finding["row"], finding["end_row"], finding["details"]["value"]) == (5, 6, "SAMPLE_Æ")


@pytest.mark.parametrize("value", ["0", "-1", "+1", "1.0", "lane1", "1x", " 1", "1 ", "１", "١", "\t"])
def test_lane_requires_whole_positive_ascii_decimal(value):
    result = check(sheet([["A", "A", "ACGT", "", PROJECT, value]], COLUMNS + ["Lane"]))
    assert "samplesheet.invalid_lane" in codes(result)
    finding = next(item for item in result.findings if item["code"] == "samplesheet.invalid_lane")
    assert finding["column"] == "Lane" and finding["details"]["value"] == value


@pytest.mark.parametrize("values,error", [(["01", "2"], None), (["01", "1"], "sample.duplicate_definition"),
                                           (["", "1"], "samplesheet.mixed_lane_scope")])
def test_normalized_lane_scope_and_duplicate_detection(values, error):
    rows = [[*ROWS[0], value] for value in values]
    if values == ["", "1"]:
        rows[1][2:4] = ROWS[1][2:4]  # Otherwise the legacy duplicate rule already rejects the rows.
    result = check(sheet(rows, COLUMNS + ["Lane"]))
    if error:
        assert error in codes(result), result.render_text()
    else:
        assert result.ok and [item["lane"] for item in result.assignments] == [1, 2]
        assert "samplesheet.lane_normalized" in codes(result, "info")
        assert result.document["rows"][-2]["cells"][-1] == "01"


@pytest.mark.parametrize("index,index2,error,column", [
    ("ACGT!suffix", "", "index.invalid_sequence", "index"),
    ("ACGT", "ACGT!suffix", "index.invalid_sequence", "index2"),
    ("AC GT", "", "index.invalid_sequence", "index"),
    ("", "ACGT", "index.incomplete_pair", "index2"),
    ("ACGT", "SI-TT-A1", "index.incomplete_pair", "index2"),
    ("SI-TT-A1", "SI-TT-A2", "index.conflicting_pair", "index2"),
    ("SI-UNKNOWN-A1", "", "index.unknown_name", "index"),
])
def test_complete_shared_index_validation_context(index, index2, error, column):
    result = check(sheet([["A", "A", index, index2, PROJECT]]))
    finding = next(item for item in result.findings if item["code"] == error)
    assert finding["column"] == column and finding["details"]["value"] == {"index": index, "index2": index2}[column]


@pytest.mark.parametrize("name,orientation,count", [("SI-GA-A1", None, 4), ("SI-TT-A1", "forward", 1),
                                                     ("SI-TT-A1", "reverse-complement", 1)])
def test_catalogue_expansion_preserves_id_and_provenance(name, orientation, count):
    prefix = PREFIX + ("[CustomOptions]\nIndex2Orientation,{}\n".format(orientation) if orientation else "")
    result = check(sheet([["001", "001", name, "", PROJECT]], prefix=prefix))
    assert result.ok, result.render_text()
    assert len(result.assignments) == count and result.summary["sample_count"] == 1
    assert [dict(index=item["index"], index2=item["index2"]) for item in result.assignments] == normalize_indexes(name, i5_orientation=orientation or "forward")
    for assignment in result.assignments:
        assert assignment["sample_id"] == "001" and assignment["index_provenance"]["original_index"] == name
        assert assignment["index_provenance"]["catalogue"]["sha256"]
    assert result.document["rows"][-1]["cells"][2] == name


def test_named_dual_orientation_is_required_and_literal_sequences_are_not_reoriented():
    result = check(sheet([["A", "A", "SI-TT-A1", "", PROJECT]]))
    assert "index.orientation" in codes(result)
    prefix = PREFIX + "[CustomOptions]\nIndex2Orientation,reverse-complement\n"
    literal = check(sheet([["A", "A", "acgt", "aacc", PROJECT]], prefix=prefix))
    assert literal.ok and literal.assignments[0]["index2"] == "AACC"
    invalid = check(sheet(prefix=PREFIX + "[CustomOptions]\nIndex2Orientation,automatic\n"))
    assert "index.orientation" in codes(invalid)


def test_symbolic_and_literal_duplicate_assignments_are_rejected():
    rows = [["A", "A", "SI-GA-A1", "", PROJECT], ["A", "A", normalize_indexes("SI-GA-A1")[0]["index"], "", PROJECT]]
    result = check(sheet(rows))
    assert "sample.duplicate_definition" in codes(result), result.render_text()
    finding = next(item for item in result.findings if item["code"] == "sample.duplicate_definition")
    assert finding["details"]["previous_rows"] == [result.document["rows"][-2]["row"]]


def test_exact_cross_library_collision_and_deferred_mismatch_checks():
    duplicate = copy.deepcopy(ROWS)
    duplicate[1][2:4] = duplicate[0][2:4]
    result = check(sheet(duplicate))
    assert "samplesheet.index_collision" in codes(result)
    duplicate[1][2] = "ACGTTGCT"  # A mismatch-aware run preflight may reject this later.
    result = check(sheet(duplicate))
    assert result.ok and "mismatch_collisions" in result.summary["deferred_checks"]
    rows = [[*row, str(index)] for index, row in enumerate([duplicate[0], ["B", "B", *duplicate[0][2:]]], 1)]
    assert check(sheet(rows, COLUMNS + ["Lane"])).ok


@pytest.mark.parametrize("section", ["Header", "Reads", "Settings", "CustomOptions", "Synthetic_Metadata"])
def test_repeated_sections_are_ambiguous_including_case_variants(section):
    prefix = "[{}]\nX,1\n[{}]\nX,1\n".format(section, section.lower())
    result = check(sheet(prefix=prefix))
    assert "samplesheet.duplicate_section" in codes(result)
    finding = next(item for item in result.findings if item["code"] == "samplesheet.duplicate_section")
    assert finding["row"] == 3 and finding["details"]["previous_rows"] == [1]


def test_both_data_variants_and_duplicate_column_aliases_fail():
    result = check(sheet() + sheet(prefix="", section="BCLConvert_Data"))
    assert "samplesheet.duplicate_data_section" in codes(result)
    for column in ("Sample_ID", "sample_id"):
        result = check(sheet([[*ROWS[0], "extra"]], COLUMNS + [column]))
        assert "samplesheet.duplicate_columns" in codes(result)


@pytest.mark.parametrize("section", ["Header", "Settings", "BCLConvert_Settings", "CustomOptions"])
def test_conflicting_and_identical_option_keys(section):
    prefix = "[{}]\nFutureOption,false\nFutureOption,true\n".format(section)
    result = check(sheet(prefix=prefix))
    assert "samplesheet.conflicting_option" in codes(result)
    identical = check(sheet(prefix=prefix.replace("FutureOption,true", "FutureOption,false")))
    assert identical.ok and "samplesheet.duplicate_option" in codes(identical, "info")


@pytest.mark.parametrize("key", ["priority", " PRIORITY ", "initialhold", "LIBPREP", "ReverseComplementIndexp5"])
def test_known_logical_aliases_cannot_hide_conflicting_values(key):
    canonical = {"priority": "Priority", "initialhold": "InitialHold", "libprep": "Libprep",
                 "reversecomplementindexp5": "ReverseComplementIndexP5"}[key.strip().lower()]
    prefix = "[CustomOptions]\n{},false\n{},False\n".format(canonical, key)
    result = check(sheet(prefix=prefix))
    assert "samplesheet.conflicting_option" in codes(result)
    assert "samplesheet.option_alias" in codes(result, "warning")
    assert result.custom_options[1]["key"] == key and result.custom_options[1]["logical_key"] == canonical
    identical = check(sheet(prefix=prefix.replace(",False", ",false")))
    assert identical.ok and len(identical.custom_options) == 2


def test_unknown_option_spellings_are_not_case_normalized():
    result = check(sheet(prefix="[CustomOptions]\nFutureOption,false\nfutureoption,true\n"))
    assert result.ok and [item["logical_key"] for item in result.custom_options] == ["FutureOption", "futureoption"]


@pytest.mark.parametrize("content,error", [
    (b"\xff", "samplesheet.parse_failed"),
    (b'[Data]\nSample_ID,Sample_Project\n"unclosed,P\n', "samplesheet.parse_failed"),
    (b'[Data]\nSample_ID,Sample_Project\na"b,P\n', "samplesheet.parse_failed"),
    (b'[Data]\nSample_ID,Sample_Project\n"a"suffix,P\n', "samplesheet.parse_failed"),
    (b"[Header]\nName,synthetic\n", "samplesheet.missing_data"),
    (b"[Data]\n", "samplesheet.missing_data"),
    (b"[Data]\nSample_ID,Sample_Project\n", "samplesheet.empty"),
    (b"[Data]\nSample_ID\nA\n", "samplesheet.missing_columns"),
    (b"[Data]\nSample_ID,Sample_Project\n,P\n", "sample.missing_id"),
    (b"[Data]\nSample_ID,Sample_Project\nA,\n", "sample.missing_project"),
    (b"[Data]\nSample_ID,Sample_Project\nA,P,extra\n", "samplesheet.row_width"),
    (b"[Data]\nSample_ID,Sample_Project,\nA,P,extra\n", "samplesheet.missing_column_header"),
    (b"[CustomOptions]\n,orphan\n[Data]\nSample_ID,Sample_Project\nA,P\n", "samplesheet.missing_option_key"),
    (b"[CustomOptions]\nKey,one,two\n[Data]\nSample_ID,Sample_Project\nA,P\n", "samplesheet.option_width"),
])
def test_malformed_and_incomplete_inputs_are_diagnostic_only(content, error):
    result = check(content)
    assert not result.ok and error in codes(result), result.render_text()


@pytest.mark.parametrize("column,value,code", [("Sample_Project", "another-project", "sample.conflicting_projects"),
                                               ("Sample_Name", "other-name", "sample.conflicting_definition")])
def test_repeated_logical_library_metadata_must_agree(column, value, code):
    rows = [list(ROWS[0]), [*ROWS[0][:2], *ROWS[1][2:4], PROJECT]]
    rows[1][COLUMNS.index(column)] = value
    result = check(sheet(rows))
    assert code in codes(result)


def test_sample_name_requires_visible_review_without_replacing_cells():
    rows = [list(ROWS[0])]
    rows[0][1] = "different-name"
    result = check(sheet(rows))
    assert result.ok and "sample.name_review" in codes(result, "warning")
    assert result.document["rows"][-1]["cells"][1] == "different-name"


def test_path_bytes_fingerprints_single_read_and_no_input_or_result_mutation(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.csv"
    content = b"\xef\xbb\xbf" + sheet()
    path.write_bytes(content)
    original_read = Path.read_bytes
    calls = []
    def read_once(candidate):
        calls.append(candidate)
        return original_read(candidate)
    monkeypatch.setattr(Path, "read_bytes", read_once)
    result = validate_samplesheet(path, profile="portable-converter")
    assert result.ok and calls.count(path) == 1
    assert result.inputs[0]["sha256"] == hashlib.sha256(content).hexdigest()
    assert original_read(path) == content and set(tmp_path.iterdir()) == {path}
    before = result.to_dict()
    report = result.to_dict()
    report["document"]["rows"][0]["cells"].append("changed")
    report["assignments"][0]["index_provenance"]["catalogue"]["version"] = "changed"
    report["inputs"][0]["sha256"] = "changed"
    report["summary"]["deferred_checks"].clear()
    assert result.to_dict() == before


def test_unreadable_path_and_invalid_python_arguments(tmp_path):
    result = validate_samplesheet(tmp_path / "absent.csv")
    assert not result.ok and "input.unreadable" in codes(result)
    assert result.inputs[0]["sha256"] is None and result.inputs[0]["size_bytes"] is None
    json.dumps(result.to_dict())
    for value in ("text", None, bytearray(b"text")):
        with pytest.raises(TypeError):
            validate_samplesheet_bytes(value)
    with pytest.raises(TypeError):
        validate_samplesheet_bytes(b"", source=tmp_path)
    with pytest.raises(ValueError):
        validate_samplesheet_bytes(b"", profile="unknown")
    with pytest.raises(ValueError):
        validate_samplesheet(tmp_path / "absent.csv", profile="unknown")


def test_existing_metadata_api_and_legacy_option_types_remain_unchanged(tmp_path):
    content = sheet([[" SAMPLE.A ", " SAMPLE.A ", "ACGT!", "", PROJECT]], prefix=PREFIX +
                    "[CustomOptions]\nFutureTrue,TrUe\nFutureFalse,false\nOrganism,N/A\nPriority,1e-5\n")
    path = tmp_path / "SampleSheet.csv"
    path.write_bytes(content)
    form = submission_form(tmp_path / "form.xlsx", [customer_row(" SAMPLE.A ", project=PROJECT)])
    result = validate_inputs(path, form)
    assert result.ok, result.render_text()
    assert VALIDATION_API_VERSION == 1 and result.to_dict()["schema_version"] == 1
    assert result.custom_options == {"FutureTrue": True, "FutureFalse": "false", "Organism": None, "Priority": "1e-5"}
    assert list(result.samples["Sample_ID"]) == [" SAMPLE.A "]
    assert "input.missing_submission_form" in codes(validate_inputs(path, []))
    raw = check(content, profile="metadata")
    assert raw.ok and [item["value"] for item in raw.custom_options] == ["TrUe", "false", "N/A", "1e-5"]
    assert path.read_bytes() == content


def test_import_is_passive_and_needs_no_bfq_or_workflow_configuration(tmp_path):
    command = ('import logging, pathlib; before = list(logging.getLogger().handlers); '
               'import configmaker.samplesheet; assert list(logging.getLogger().handlers) == before; '
               'assert not list(pathlib.Path.cwd().iterdir())')
    subprocess.run([sys.executable, "-c", command], cwd=tmp_path, check=True)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_undecodable_bytes_report_exact_source_offset_including_bom(bom):
    content = bom + b"[Header]\nName," + b"\xff"
    result = check(content)
    finding = next(item for item in result.findings if item["code"] == "samplesheet.parse_failed")
    assert finding["details"]["byte_offset"] == len(content) - 1


@pytest.mark.parametrize("newline", ["\n", "\r", "\r\n"])
def test_multiline_duplicate_context_refers_to_original_physical_rows(newline):
    rows = [[*ROWS[0], "first" + newline + "second"]] * 2
    result = check(sheet(rows, COLUMNS + ["Description"], prefix=""))
    finding = next(item for item in result.findings if item["code"] == "sample.duplicate_definition")
    assert finding["row"] == 5 and finding["end_row"] == 6
    assert finding["details"]["previous_rows"] == [3]
    assert finding["details"]["value"] == "SAMPLE_A"


def test_optional_missing_trailing_cells_and_blank_export_columns_are_preserved():
    content = b"[Data]\nSample_ID,Sample_Project,index,Description,\n001,SyntheticProject,ACGT\n,,,\n"
    result = check(content)
    assert result.ok and result.assignments[0]["sample_id"] == "001"
    assert result.document["rows"][-2]["cells"] == ["001", "SyntheticProject", "ACGT"]
    assert result.document["rows"][-1]["cells"] == ["", "", "", ""]
    assert result.document["columns"][-1] == ""


def test_unknown_option_keys_retain_outer_space_as_well_as_case():
    result = check(sheet(prefix="[CustomOptions]\nFutureOption,first\n FutureOption ,second\n"))
    assert result.ok and [item["logical_key"] for item in result.custom_options] == ["FutureOption", " FutureOption "]


def test_non_ascii_whitespace_id_is_not_discarded_as_an_empty_row():
    result = check(b"[Data]\nSample_ID,Sample_Project\n" + "\u2003,\n".encode())
    finding = next(item for item in result.findings if item["code"] == "sample.non_ascii_id")
    assert finding["row"] == 3 and finding["details"]["value"] == "\u2003"
