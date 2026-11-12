"""Test-only BIFF8 writer; all callers supply independently synthetic cell values."""

import xlwt


def save_xls(workbook, path):
    """Serialize synthetic openpyxl cells without importing workbook properties."""
    output = xlwt.Workbook(encoding="utf-8")
    for source in workbook.worksheets:
        target = output.add_sheet(source.title)
        for row in source.iter_rows():
            for cell in row:
                if cell.value is not None:
                    target.write(cell.row - 1, cell.column - 1, cell.value)
    output.save(str(path))
    return path
