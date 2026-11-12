"""Installed manual initialization accepts real synthetic .xls and .xlsx inputs."""

from pathlib import Path
import subprocess
import sys

from openpyxl import load_workbook
import pytest

from excel_fixture import save_xls
from test_paired_cli import PROJECT, RUN, assert_outputs, contents, example


@pytest.mark.parametrize("suffix", [".xls", ".xlsx"])
@pytest.mark.parametrize("selection", ["discovery", "explicit"])
def test_installed_configmaker_initializes_each_workbook_format(example, suffix, selection):
    source, work = example
    original = source / RUN / "Sample-Submission-Form.xlsx"
    form = original.with_suffix(suffix)
    if suffix == ".xls":
        workbook = load_workbook(original)
        save_xls(workbook, form)
        workbook.close()
        original.unlink()  # Only this invocation's copy of the synthetic input.
    before = contents(source)
    command = [str(Path(sys.executable).parent / "configmaker.py"), str(source / RUN), "--project-id", PROJECT]
    if selection == "explicit":
        command += ["--sample-submission-form", str(form)]
    result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert_outputs(source, work, submission_form=form.name)
    assert contents(source) == before
