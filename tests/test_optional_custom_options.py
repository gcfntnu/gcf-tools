"""Optional producer fields survive shared and standalone reads without defaults."""
import pytest

from configmaker.configmaker import get_data_from_samplesheet
from configmaker.validation import validate_inputs
from test_validation import customer_row, sample_sheet, submission_form


PROJECT = "GCF-2099-001"
RETIRED = {
    "RemoveHumanReads": "true",
    "SingleCell": "False",
    "TrimAdapter": "False",
    "Rerun": "YES",
    "ReverseComplementIndexP5": "true",
    "ReverseComplementIndexP7": "False",
}
RETIRED_PARSED = dict(RETIRED, RemoveHumanReads=True, ReverseComplementIndexP5=True)
SCHEDULING = {"Priority": "0.5000000000000000000001", "InitialHold": "true"}


@pytest.mark.parametrize("section", ["Data", "BCLConvert_Data"])
@pytest.mark.parametrize("legacy,scheduling", [(False, False), (True, False),
                                               (False, True), (True, True)])
def test_optional_custom_options_are_preserved_not_required_or_synthesized(tmp_path, section,
                                                                         legacy, scheduling):
    options = {"Libprep": "Synthetic kit", "ExtraOption": "retained"}
    expected = dict(options)
    if legacy:
        options.update(RETIRED)
        expected.update(RETIRED_PARSED)
    if scheduling:
        options.update(SCHEDULING)
        expected.update(SCHEDULING, InitialHold=True)
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [("SAMPLE_001", PROJECT)])
    custom = "[CustomOptions]\n" + "".join(f"{key},{value}\n" for key, value in options.items())
    sheet.write_text(sheet.read_text().replace("[Data]", custom + f"[{section}]"))
    original = sheet.read_bytes()
    form = submission_form(tmp_path / "submission.xlsx",
                           [customer_row("SAMPLE_001", project=PROJECT)])

    result = validate_inputs([sheet], [form])
    assert result.ok, result.render_text()
    assert result.custom_options == expected
    with sheet.open("rb") as source:
        data, custom_options, _header = get_data_from_samplesheet(source)
    assert custom_options == expected
    assert data["Sample_ID"].tolist() == ["SAMPLE_001"]
    assert sheet.read_bytes() == original


def test_shared_reader_does_not_apply_bfq_scheduling_policy(tmp_path):
    # BFQ owns semantic validation, defaults and persistent hold/release behavior.
    sheet = sample_sheet(tmp_path / "SampleSheet.csv", [("SAMPLE_001", PROJECT)])
    sheet.write_text(sheet.read_text().replace(
        "[Data]", "[CustomOptions]\nPriority,not-a-number\nInitialHold,operator-note\n[Data]"))
    form = submission_form(tmp_path / "submission.xlsx",
                           [customer_row("SAMPLE_001", project=PROJECT)])
    result = validate_inputs([sheet], [form])
    assert result.ok, result.render_text()
    assert result.custom_options == {"Priority": "not-a-number", "InitialHold": "operator-note"}
