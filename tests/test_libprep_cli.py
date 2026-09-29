import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".tests/configmaker/201109_NB501038_0241_AH2JYJBGXG"
CONTENT = b"Kit SE:\n  workflow: rnaseq\n  filter:\n    trim:\n      fastp:\n        params: '-q 17'\n"


@pytest.mark.parametrize("explicit", [False, True])
def test_standalone_cli_outside_opt(tmp_path, explicit):
    workflow = tmp_path / "src/gcf-workflows"
    workflow.mkdir(parents=True)
    (workflow / "libprep.config").write_bytes(CONTENT)
    command = [
        sys.executable,
        "-m",
        "configmaker.configmaker",
        str(RUN),
        "--libkit",
        "Kit",
        "--skip-peppy",
    ]
    expected = CONTENT
    if explicit:
        expected = CONTENT.replace(b"-q 17", b"-q 23")
        snapshot = tmp_path / "external/config.snapshot"
        snapshot.parent.mkdir()
        snapshot.write_bytes(expected)
        command += [
            "--libprep-config",
            str(snapshot),
            "--libprep-sha256",
            hashlib.sha256(expected).hexdigest(),
            "--libprep-entry",
            "Kit SE",
            "--expected-read-geometry",
            "86",
        ]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert config["workflow"] == "rnaseq"
    assert config["filter"]["trim"]["fastp"]["params"] == (
        "-q 23" if explicit else "-q 17"
    )
    assert config["libprep_selection"]["sha256"] == hashlib.sha256(expected).hexdigest()
    assert (workflow / "libprep.config").read_bytes() == expected
    assert "rnaseq/rnaseq.smk" in (tmp_path / "Snakefile").read_text()


@pytest.mark.parametrize("problem", ["missing", "malformed", "unknown", "hash"])
def test_standalone_cli_actionable_config_error(tmp_path, problem):
    workflow = tmp_path / "src/gcf-workflows"
    workflow.mkdir(parents=True)
    if problem != "missing":
        (workflow / "libprep.config").write_bytes(
            b"broken: [" if problem == "malformed" else CONTENT
        )
    command = [
        sys.executable,
        "-m",
        "configmaker.configmaker",
        str(RUN),
        "--libkit",
        "Kti" if problem == "unknown" else "Kit",
        "--skip-peppy",
    ]
    if problem == "hash":
        command += ["--libprep-sha256", "bad"]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 2
    assert "ERROR" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "Snakefile").exists()
