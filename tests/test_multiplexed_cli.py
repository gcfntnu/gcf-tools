import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from openpyxl import load_workbook

from multiplexed_fixture import CUSTOMER, KIT, PROJECT, make_multiplexed


def cli(run, work, *arguments):
    return subprocess.run([str(Path(sys.executable).parent / "configmaker.py"), str(run),
                           "--project-id", PROJECT, *arguments], cwd=work,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("override", [False, True])
def test_multiplexed_columns_survive_config_and_pep(tmp_path, override):
    run, _, work = make_multiplexed(tmp_path, sheet_kit="Synthetic" if override else KIT)
    result = cli(run, work, *(["--libkit", KIT] if override else []))
    assert result.returncode == 0, result.stdout + result.stderr
    config = yaml.safe_load((work / "config.yaml").read_text())
    assert set(config["samples"]) == {"001", "001A", "CTRL"}
    assert set(config["wells"]) == {"001", "1"}
    for sid, concentration in [("001", "11.0"), ("001A", "22.0"), ("CTRL", "33.0")]:
        sample = config["samples"][sid]
        assert sample["Sample_ID"] == sid
        assert sample["Concentration"] == concentration
        assert sample["Submitted_Custom_Metric"] == "0"
        assert sample["Lab_Custom_Score"] == "0"
        assert sample["Submitted_Library_External_Id"].startswith("LIB")
        assert sample["Volume"] == "5.0"
        assert sample["Sample_Buffer"] == "buffer"
        assert sample["Sample_Type"] == "RNA"
        assert sample["Quantification"] == "method"
        assert sample["KIT"] == "synthetic"
        assert "Sample_Group" not in sample and "External_ID" not in sample
    bio = config["wells"]["001"]
    assert bio["Sample_ID"] == "001" and bio["External_ID"] == "007"
    assert bio["Sample_Group"] == "control"
    assert bio["Demux_Sample_Biosource"] == "sourceA"
    assert bio["Demux_Custom_Metric"] == 0
    assert bio["Wells"] == "A1,A2"
    assert config["wells"]["1"]["Wells"] == "B1-B2"
    summary = json.loads((work / "configmaker.analysis-summary.json").read_text())
    assert summary["sample_count"] == summary["planned_sample_count"] == 3
    assert {s["sample_id"] for s in summary["samples"]} == set(config["samples"])
    assert (work / "pep/sample_table.csv").is_file()


@pytest.mark.parametrize("override", [False, True])
def test_pooled_error_is_before_output_mutation(tmp_path, override):
    run, form, work = make_multiplexed(tmp_path, sheet_kit="Synthetic" if override else KIT)
    book = load_workbook(form)
    book[CUSTOMER]["C16"] = "control"
    book.save(form)
    (work / "config.yaml").write_text("keep: true\n")
    (work / "data").mkdir()
    (work / "data/sentinel").write_text("preserve\n")
    def snapshot():
        return {str(p.relative_to(work)): p.read_bytes() if p.is_file() else None for p in work.rglob("*")}
    before, source = snapshot(), form.read_bytes()
    result = cli(run, work, *(["--libkit", KIT] if override else []))
    assert result.returncode == 2
    assert "workbook.pooled_biological_metadata" in result.stderr
    assert "Sample_Group" in result.stderr and "Cell Multiplexing" in result.stderr
    assert snapshot() == before and form.read_bytes() == source
