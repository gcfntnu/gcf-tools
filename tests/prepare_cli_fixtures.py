"""Copy legacy integration fixtures and remove an intentionally invalid note row.

The historical RNA workbook put a free-text note in customer J48, below the
sample rows. Preflight now correctly rejects populated rows without IDs. Keep
that original fixture intact (it is useful invalid-input coverage), and sanitize
only private copies used to exercise otherwise valid legacy CLI workflows.
"""

import shutil
import sys
from pathlib import Path

from openpyxl import load_workbook


def prepare(source, destination):
    shutil.copytree(source, destination)
    directory = Path(destination) / "201109_NB501038_0241_AH2JYJBGXG"
    for filename in ("Sample-Submission-Form.xlsx", "test_descriptor_headers.xlsx"):
        path = directory / filename
        workbook = load_workbook(path)
        sheet = workbook["Sample-Submission-Form"]
        assert sheet["A48"].value is None, "Expected an unassigned note, never a sample"
        assert all(cell.value is None for cell in sheet[48] if cell.coordinate != "J48"), "Unexpected data in historical note row"
        sheet["J48"] = None
        workbook.save(path)


if __name__ == "__main__":
    prepare(*sys.argv[1:])
