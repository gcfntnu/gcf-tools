"""Actual .xls/.xlsx readers preserve the shared submission metadata contract."""

import hashlib
import io

import pandas as pd
import pytest
from openpyxl import Workbook

from configmaker.configmaker import sample_submission_form_parser
from configmaker.validation import validate_inputs
from excel_fixture import save_xls
from test_validation import CUSTOMER_HEADERS, LAB_HEADERS, customer_row, sample_sheet

PROJECT = "GCF-2099-001"
SAMPLES = ["001", "NA", "case_A"]


def submission(path, sample_ids=SAMPLES, *, empty_lab=False):
    workbook = Workbook()
    customer = workbook.active
    customer.title = "Sample-Submission-Form"
    customer.cell(1, 1, "Wholly synthetic workbook; no facility source")
    for column, header in enumerate(CUSTOMER_HEADERS + ["Concentration"], 1):
        customer.cell(15, column, header)
    lab = workbook.create_sheet("INFO (GCF-lab only)")
    lab.append(LAB_HEADERS)
    for rownum, sid in enumerate(sample_ids, 16):
        for column, value in enumerate(customer_row(sid, group="synthetic æ", project=PROJECT) + [1.0], 1):
            customer.cell(rownum, column, value)
        if not empty_lab:
            lab.append([sid, 7.5])
    if path.suffix == ".xls":
        save_xls(workbook, path)
    else:
        workbook.save(path)
    return path


@pytest.mark.parametrize("suffix,engine", [(".xls", "xlrd"), (".xlsx", "openpyxl")])
def test_real_workbook_engines_preserve_exact_ids_lab_precedence_and_wrapper(tmp_path, suffix, engine):
    form = submission(tmp_path / ("submission" + suffix))
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [[sid, PROJECT] for sid in SAMPLES])
    original = form.read_bytes()
    with pd.ExcelFile(io.BytesIO(original)) as book:
        assert book.engine == engine
    result = validate_inputs(sheet, form)
    assert result.ok, result.render_text()
    assert list(result.metadata["Sample_ID"]) == SAMPLES
    assert list(result.metadata["Concentration"]) == [7.5] * 3
    assert list(result.metadata["Sample_Group"]) == ["synthetic æ"] * 3
    assert result.summary["planned_sample_count"] == 3
    identity = next(item for item in result.inputs if item["path"] == str(form))
    assert identity["sha256"] == hashlib.sha256(original).hexdigest()
    assert identity["size_bytes"] == len(original)
    frame, descriptors = sample_submission_form_parser(form)
    assert list(frame.index) == SAMPLES and list(frame["Sample_ID"]) == SAMPLES
    assert list(frame["Concentration"]) == [7.5] * 3
    assert descriptors
    assert form.read_bytes() == original


@pytest.mark.parametrize("suffix", [".xls", ".xlsx"])
def test_both_formats_keep_empty_lab_customer_fallback(tmp_path, suffix):
    form = submission(tmp_path / ("submission" + suffix), empty_lab=True)
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [[sid, PROJECT] for sid in SAMPLES])
    result = validate_inputs(sheet, form)
    assert result.ok, result.render_text()
    assert list(result.metadata["Sample_ID"]) == SAMPLES
    assert list(result.metadata["Concentration"]) == [1.0] * 3
    assert "workbook.empty_lab" in {finding["code"] for finding in result.findings}


@pytest.mark.parametrize("suffix", [".xls", ".xlsx"])
def test_both_formats_reject_duplicate_ids_with_worksheet_and_row(tmp_path, suffix):
    form = submission(tmp_path / ("submission" + suffix), sample_ids=["001", "001"])
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [["001", PROJECT]])
    original = form.read_bytes()
    result = validate_inputs(sheet, form)
    assert not result.ok
    findings = [item for item in result.findings if item["code"] == "workbook.duplicate_id"]
    assert {item["worksheet"] for item in findings} == {"Sample-Submission-Form", "INFO (GCF-lab only)"}
    customer = next(item for item in findings if item["worksheet"] == "Sample-Submission-Form")
    assert customer["row"] == 17 and customer["sample_id"] == "001"
    assert customer["details"]["previous_row"] == 16
    assert form.read_bytes() == original


@pytest.mark.parametrize("suffix", [".xls", ".xlsx"])
def test_both_formats_reject_original_non_ascii_workbook_ids(tmp_path, suffix):
    form = submission(tmp_path / ("submission" + suffix), sample_ids=["SAMPLE_Æ"])
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [["SAMPLE_A", PROJECT]])
    result = validate_inputs(sheet, form)
    assert not result.ok
    finding = next(item for item in result.findings if item["code"] == "sample.non_ascii_id")
    assert finding["row"] == 16 and finding["worksheet"] == "Sample-Submission-Form"
    assert finding["details"]["value"] == "SAMPLE_Æ"


@pytest.mark.parametrize("suffix", [".xls", ".xlsx"])
def test_both_formats_keep_whitespace_exact_for_matching(tmp_path, suffix):
    form = submission(tmp_path / ("submission" + suffix), sample_ids=[" 001 "])
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [[" 001 ", PROJECT]])
    result = validate_inputs(sheet, form)
    assert result.ok and list(result.metadata["Sample_ID"]) == [" 001 "], result.render_text()
    sample_sheet(sheet, [["001", PROJECT]])
    mismatch = validate_inputs(sheet, form)
    assert not mismatch.ok and "sample.whitespace_mismatch" in {item["code"] for item in mismatch.findings}
