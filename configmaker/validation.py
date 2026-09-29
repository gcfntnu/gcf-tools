"""Shared metadata-only input validation (public API version 1).

No logging is configured and no files are written. Bytes are read once: the
recorded SHA-256 identifies exactly the input parsed, including failed parses.
"""

import copy
import csv
import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from configmaker import __version__
from configmaker.columns import _customer_column_mapper, _lab_column_mapper, _demux_column_mapper
from descriptors import descriptors as descriptor_tools

VALIDATION_API_VERSION = 1
VALIDATOR_VERSION = __version__
CUSTOMER_SHEET = "Sample-Submission-Form"
LAB_SHEET = "INFO (GCF-lab only)"


def _blank(value):
    return value is None or pd.isna(value) or (isinstance(value, str) and not value.strip())


def _identifier(value):
    # Strings are intentionally not stripped or numerically inferred.
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _plain(value):
    if _blank(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@dataclass
class ValidationResult:
    findings: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    samples: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["Sample_ID", "Project_ID"]))
    metadata: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["Sample_ID"]))
    descriptors: dict = field(default_factory=dict)
    custom_options: dict = field(default_factory=dict)
    header: dict = field(default_factory=dict)
    sheets: list = field(default_factory=list)
    forms: list = field(default_factory=list)

    @property
    def ok(self):
        return not any(f["severity"] == "error" for f in self.findings)

    def add(self, severity, code, message, **context):
        finding = {"severity": severity, "code": code, "message": message}
        finding.update({k: v for k, v in context.items() if v is not None})
        self.findings.append(finding)

    def to_dict(self):
        return copy.deepcopy({
            "schema_version": VALIDATION_API_VERSION,
            "validator": {"name": "gcf-tools", "version": __version__, "api_version": VALIDATION_API_VERSION},
            "status": "passed" if self.ok else "failed",
            "inputs": self.inputs,
            "errors": [f for f in self.findings if f["severity"] == "error"],
            "warnings": [f for f in self.findings if f["severity"] == "warning"],
            "info": [f for f in self.findings if f["severity"] == "info"],
            "summary": self.summary,
        })

    def render_text(self):
        state = "PASSED" if self.ok else "FAILED"
        lines = ["Metadata preflight {} (gcf-tools {}, API {})".format(state, __version__, VALIDATION_API_VERSION)]
        for finding in self.findings:
            location = [str(finding[k]) for k in ("file", "worksheet") if k in finding]
            location.extend("{} {}".format(k, finding[k]) for k in ("row", "column") if k in finding)
            prefix = "{} [{}]".format(finding["severity"].upper(), finding["code"])
            lines.append("{} {}{}".format(prefix, finding["message"], " ({})".format(": ".join(location)) if location else ""))
        if self.summary:
            lines.append("Planned: {} sample(s), {} project(s); {} extra effective submission sample(s).".format(
                self.summary.get("planned_sample_count", 0), len(self.summary.get("projects", [])),
                self.summary.get("extra_submission_sample_count", 0)))
        return "\n".join(lines)


class InputValidationError(ValueError):
    def __init__(self, result):
        self.result = result
        super().__init__(result.render_text())


def _paths(values):
    if values is None:
        return []
    if isinstance(values, (str, Path)):
        return [values]
    return list(values)


def _read(path, kind, result):
    path = Path(path).expanduser().absolute()
    record = {"kind": kind, "path": str(path), "sha256": None, "size_bytes": None}
    result.inputs.append(record)
    try:
        content = path.read_bytes()
    except (OSError, ValueError) as error:
        result.add("error", "input.unreadable", "Cannot read {}: {}".format(kind, error), file=str(path))
        return str(path), None
    record.update(sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
    return str(path), content


def _duplicates(columns):
    return sorted({name for name in columns if columns.count(name) > 1})


def parse_samplesheet(content, path, result):
    """Parse IEM [Data] / BCL Convert [BCLConvert_Data] without dtype inference."""
    initial_errors = sum(f["severity"] == "error" for f in result.findings)
    records, headers, options, header, section = [], None, {}, {}, None
    seen_sections = set()
    try:
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        for cells in reader:
            rownum = reader.line_num
            if not cells or all(not cell.strip() for cell in cells):
                continue
            tag = cells[0].strip()
            if tag.startswith("[") and tag.endswith("]") and all(not c.strip() for c in cells[1:]):
                section = tag[1:-1].lower()
                if section in ("data", "bclconvert_data"):
                    if "data" in seen_sections:
                        result.add("error", "samplesheet.duplicate_data_section", "Multiple data sections make sample definitions ambiguous.", file=path, row=rownum)
                    seen_sections.add("data")
                continue
            if section in ("data", "bclconvert_data"):
                if headers is None:
                    headers = cells
                    duplicates = _duplicates([h for h in headers if h])
                    if duplicates:
                        result.add("error", "samplesheet.duplicate_columns", "Duplicate SampleSheet columns: {}".format(", ".join(duplicates)), file=path, row=rownum, details={"columns": duplicates})
                    missing = sorted({"Sample_ID", "Sample_Project"} - set(headers))
                    if missing:
                        result.add("error", "samplesheet.missing_columns", "Required SampleSheet columns missing: {}".format(", ".join(missing)), file=path, row=rownum, details={"columns": missing})
                    continue
                if len(cells) > len(headers) and any(cells[len(headers):]):
                    result.add("error", "samplesheet.row_width", "Sample row has {} fields; header has {}.".format(len(cells), len(headers)), file=path, row=rownum)
                    continue
                cells = cells[:len(headers)] + [""] * max(0, len(headers) - len(cells))
                if any(value for key, value in zip(headers, cells) if not key):
                    result.add("error", "samplesheet.missing_column_header", "Populated SampleSheet column has no header.", file=path, row=rownum)
                    continue
                record = {key: value for key, value in zip(headers, cells) if key}
                record.update(_file=path, _row=rownum)
                if "Sample_ID" in record and not record["Sample_ID"].strip():
                    result.add("error", "sample.missing_id", "Populated sample row has no Sample_ID.", file=path, row=rownum, column="Sample_ID")
                    continue
                if "Sample_Project" in record and not record["Sample_Project"].strip():
                    result.add("error", "sample.missing_project", "Sample {!r} has no Sample_Project.".format(record.get("Sample_ID")), file=path, row=rownum, column="Sample_Project", sample_id=record.get("Sample_ID"))
                records.append(record)
            elif section in ("header", "customoptions"):
                key, value = cells[0].strip(), cells[1].strip() if len(cells) > 1 else ""
                value = True if value.lower() == "true" else value
                if key == "Organism" and value == "N/A":
                    value = None
                target = options if section == "customoptions" else header
                if key in target and target[key] != value:
                    result.add("error", "samplesheet.conflicting_option", "Conflicting values for {!r} in [{}].".format(key, section), file=path, row=rownum, column=key)
                target[key] = value
    except (UnicodeError, csv.Error) as error:
        result.add("error", "samplesheet.parse_failed", "Cannot parse SampleSheet: {}".format(error), file=path)
        return None
    if headers is None:
        result.add("error", "samplesheet.missing_data", "SampleSheet requires a [Data] or [BCLConvert_Data] section and its column header.", file=path)
    elif not records:
        result.add("error", "samplesheet.empty", "SampleSheet contains no sample rows.", file=path)
    if headers and "Sample_ID" in headers and "Sample_Project" in headers:
        grouped = {}
        for record in records:
            sid = record["Sample_ID"]
            if sid != sid.strip():
                result.add("warning", "sample.id_whitespace", "Sample_ID {!r} contains surrounding whitespace; exact spelling is retained.".format(sid), file=path, row=record["_row"], column="Sample_ID", sample_id=sid)
            previous = grouped.setdefault(sid, [])
            if previous:
                if any(p["Sample_Project"] != record["Sample_Project"] for p in previous):
                    code, message = "sample.conflicting_projects", "Conflicting project assignments for Sample_ID {!r} within one SampleSheet."
                elif not record.get("Lane") or any(p.get("Lane") == record["Lane"] or not p.get("Lane") for p in previous):
                    code, message = "sample.duplicate_definition", "Duplicate Sample_ID {!r} without distinct explicit lanes."
                elif any(any(p[k] != record[k] for k in headers if k and k not in ("Lane", "index", "index2", "I7_Index_ID", "I5_Index_ID", "Index_Plate_Well")) for p in previous):
                    code, message = "sample.conflicting_definition", "Conflicting metadata for repeated Sample_ID {!r} across lanes."
                else:
                    code = None
                if code:
                    result.add("error", code, message.format(sid), file=path, row=record["_row"], sample_id=sid, details={"previous_rows": [p["_row"] for p in previous]})
            previous.append(record)
    if sum(f["severity"] == "error" for f in result.findings) > initial_errors:
        return None
    return {"path": path, "records": records, "columns": [h for h in headers if h], "options": options, "header": header}


def _worksheet(book, path, name, header_row, mapper, result, optional_empty=False):
    context = {"file": path, "worksheet": name}
    if name not in book.sheet_names:
        result.add("error", "workbook.missing_worksheet", "Required worksheet {!r} is missing.".format(name), **context)
        return None
    raw = pd.read_excel(book, sheet_name=name, header=None, dtype=object, keep_default_na=False)
    if raw.shape[0] < header_row:
        if optional_empty and raw.empty:
            return {"data": pd.DataFrame(columns=["Sample_ID"]), "descriptors": {}, "rows": {}}
        result.add("error", "workbook.missing_header", "Expected header at worksheet row {}.".format(header_row), row=header_row, **context)
        return None
    raw_headers = raw.iloc[header_row - 1].tolist()
    data_rows = list(raw.iloc[header_row:].itertuples(index=False, name=None))
    active = [i for i, value in enumerate(raw_headers) if not _blank(value)]
    unnamed_populated = [i for i in range(len(raw_headers)) if i not in active and any(not _blank(row[i]) for row in data_rows)]
    if unnamed_populated:
        result.add("error", "workbook.missing_column_header", "Populated column(s) have no header: {}.".format(", ".join(str(i + 1) for i in unnamed_populated)), row=header_row, **context)
        return None
    headers = [str(raw_headers[i]) for i in active]
    frame = pd.DataFrame([[row[i] for i in active] for row in data_rows], columns=headers)
    try:
        desc = descriptor_tools.findall_header_descriptors(frame, mapper=mapper)
    except (ValueError, TypeError) as error:
        result.add("error", "workbook.invalid_descriptor", "Cannot parse column descriptors: {}".format(error), row=header_row, **context)
        return None
    mapped = [mapper(name) for name in frame.columns]
    duplicates = _duplicates(mapped)
    if duplicates:
        result.add("error", "workbook.duplicate_columns", "Duplicate columns after header mapping: {}.".format(", ".join(duplicates)), row=header_row, details={"columns": duplicates}, **context)
        return None
    frame.columns = mapped
    populated = [i for i, row in enumerate(data_rows) if any(not _blank(value) for value in row)]
    if optional_empty and not populated:
        return {"data": pd.DataFrame(columns=["Sample_ID"]), "descriptors": desc, "rows": {}}
    if "Sample_ID" not in frame.columns:
        expected = "Unique Sample ID" if name != LAB_SHEET else "Sample_ID"
        result.add("error", "workbook.missing_columns", "Required Sample_ID header ({} at row {}) is missing.".format(expected, header_row), row=header_row, column="Sample_ID", **context)
        return None
    valid_rows, source_rows, broken = [], {}, False
    for i in populated:
        row = frame.iloc[i].copy()
        rownum = header_row + i + 1
        if _blank(row["Sample_ID"]):
            result.add("error", "sample.missing_id", "Populated sample row has no Sample_ID.", row=rownum, column="Sample_ID", **context)
            broken = True
            continue
        sid = _identifier(row["Sample_ID"])
        row["Sample_ID"] = sid
        if "External_ID" in row and not _blank(row["External_ID"]):
            row["External_ID"] = _identifier(row["External_ID"])
        if sid != sid.strip():
            result.add("warning", "sample.id_whitespace", "Sample_ID {!r} contains surrounding whitespace; exact spelling is retained.".format(sid), row=rownum, column="Sample_ID", sample_id=sid, **context)
        if sid in source_rows:
            result.add("error", "workbook.duplicate_id", "Duplicate Sample_ID {!r} makes this worksheet's mapping ambiguous.".format(sid), row=rownum, sample_id=sid, details={"previous_row": source_rows[sid]}, **context)
            broken = True
        source_rows[sid] = rownum
        valid_rows.append(row)
    if broken:
        return None
    if not valid_rows:
        result.add("error", "workbook.empty_customer", "Submission worksheet has no sample rows.", **context)
        return None
    frame = pd.DataFrame(valid_rows, columns=mapped).reset_index(drop=True)
    # IDs remain exact, including the literal string 'NA'. Existing non-ID
    # metadata treats NA/empty cells as missing; empty lab columns do not win.
    for col in frame.columns:
        if col != "Sample_ID":
            frame[col] = frame[col].map(lambda value: pd.NA if _blank(value) or (isinstance(value, str) and value == "NA") else value)
    frame = frame.dropna(axis=1, how="all")
    if name == CUSTOMER_SHEET:
        frame = frame.drop(columns=["Sample_Type", "Sample_Buffer", "Volume", "Quantification"], errors="ignore")
    elif name == LAB_SHEET:
        frame = frame.drop(columns=["KIT"], errors="ignore")
    return {"data": frame, "descriptors": desc, "rows": source_rows}


def parse_submission_form(content, path, result, require_demux=False):
    """Read both worksheets and reproduce configmaker's lab-precedence join."""
    try:
        with pd.ExcelFile(io.BytesIO(content)) as book:
            customer = _worksheet(book, path, CUSTOMER_SHEET, 15, _customer_column_mapper, result)
            lab = _worksheet(book, path, LAB_SHEET, 1, _lab_column_mapper, result, optional_empty=True)
            demux = _worksheet(book, path, "Cell Multiplexing", 1, _demux_column_mapper, result) if require_demux else None
    except (OSError, ValueError, KeyError, TypeError, ImportError, EOFError) as error:
        result.add("error", "workbook.parse_failed", "Cannot parse submission workbook: {}".format(error), file=path)
        return None
    # Bad zip/XML are raised by spreadsheet engines rather than pandas itself.
    except Exception as error:
        if error.__class__.__module__ in ("zipfile", "xml.etree.ElementTree", "lxml.etree", "openpyxl.utils.exceptions"):
            result.add("error", "workbook.parse_failed", "Cannot parse submission workbook: {}".format(error), file=path)
            return None
        raise
    if customer is None or lab is None or (require_demux and demux is None):
        return None
    c, l = customer["data"], lab["data"]
    shared = sorted((set(c.columns) & set(l.columns)) - {"Sample_ID"})
    desc = copy.deepcopy(customer["descriptors"])
    for column, value in lab["descriptors"].items():
        if value and (column in shared or not desc.get(column)):
            desc[column] = value
    if not l.empty:
        for sid in sorted(set(c.Sample_ID) - set(l.Sample_ID)):
            result.add("info", "workbook.merge_excluded", "Customer Sample_ID {!r} is absent from the lab worksheet and excluded by the inner join.".format(sid), file=path, worksheet=LAB_SHEET, sample_id=sid)
        for sid in sorted(set(l.Sample_ID) - set(c.Sample_ID)):
            result.add("info", "workbook.merge_excluded", "Lab Sample_ID {!r} is absent from the customer worksheet and excluded by the inner join.".format(sid), file=path, worksheet=CUSTOMER_SHEET, sample_id=sid)
        merged = c.drop(columns=shared).merge(l, on="Sample_ID", how="inner", validate="one_to_one")
    else:
        merged = c.copy()
        result.add("info", "workbook.empty_lab", "Empty lab worksheet: customer metadata is used directly.", file=path, worksheet=LAB_SHEET)
    desc = descriptor_tools.add_default_descriptors(merged, desc)
    return {"path": path, "customer": customer, "lab": lab, "data": merged, "descriptors": desc, "demux": demux}


def _batch(path):
    return Path(path).parent.name.split("_")[-1]


def validate_inputs(samplesheets, submission_forms, project_ids=None, keep_batch=False):
    """Validate input paths, returning all independent metadata findings.

    Cross-file repeated IDs intentionally merge; later forms override metadata
    with a warning. Repeats within a worksheet, or a lane, are ambiguous errors.
    Malformed inputs are reported rather than raised. Unexpected coding errors
    propagate. Only an ``ok`` result is suitable for project initialization.
    """
    result = ValidationResult()
    samplesheets, submission_forms = _paths(samplesheets), _paths(submission_forms)
    selected = set(_paths(project_ids)) if project_ids is not None else None
    if not samplesheets:
        result.add("error", "input.missing_samplesheet", "No SampleSheet inputs were supplied.")
    if not submission_forms:
        result.add("error", "input.missing_submission_form", "No submission-form inputs were supplied.")
    for path in samplesheets:
        path, content = _read(path, "samplesheet", result)
        if content is not None:
            sheet = parse_samplesheet(content, path, result)
            if sheet is not None:
                result.sheets.append(sheet)
                for key in set(result.custom_options) & set(sheet["options"]):
                    if result.custom_options[key] != sheet["options"][key]:
                        result.add("warning", "samplesheet.option_override", "Custom option {!r} differs between SampleSheets; the last sheet takes precedence.".format(key), file=path, column=key)
                result.custom_options.update(sheet["options"])
                result.header = sheet["header"]
    require_demux = str(result.custom_options.get("Libprep", "")).startswith("Parse Biosciences")
    for path in submission_forms:
        path, content = _read(path, "submission_form", result)
        if content is not None:
            form = parse_submission_form(content, path, result, require_demux=require_demux)
            if form is not None:
                result.forms.append(form)

    selected_rows = [r for sheet in result.sheets for r in sheet["records"] if selected is None or r["Sample_Project"] in selected]
    if result.sheets and not selected_rows:
        result.add("error", "sample.no_selected_samples", "No SampleSheet samples match the requested project selection.", details={"project_ids": sorted(selected) if selected is not None else []})
    sample_projects, planned = {}, {}
    for row in selected_rows:
        sid, pid = row["Sample_ID"], row["Sample_Project"]
        if pid not in sample_projects.setdefault(sid, []):
            sample_projects[sid].append(pid)
        effective_id = sid + "_" + _batch(row["_file"]) if keep_batch else sid
        item = planned.setdefault(effective_id, {"sample_id": effective_id, "project_ids": [], "sample_group": None})
        if pid not in item["project_ids"]:
            item["project_ids"].append(pid)
    result.samples = pd.DataFrame([{"Sample_ID": sid, "Project_ID": projects} for sid, projects in sample_projects.items()], columns=["Sample_ID", "Project_ID"])

    metadata, metadata_sources, metadata_projects = {}, {}, {}
    sheet_batches = sorted({_batch(sheet["path"]) for sheet in result.sheets})
    for form in result.forms:
        for key, value in form["descriptors"].items():
            if key not in result.descriptors or result.descriptors[key] == descriptor_tools.DEFAULT_DESCRIPTORS.get(key):
                result.descriptors[key] = copy.deepcopy(value)
        # A separately located explicit form can describe all requested batches.
        batches = [_batch(form["path"])] if _batch(form["path"]) in sheet_batches else sheet_batches
        for raw in form["data"].to_dict(orient="records"):
            for batch in (batches if keep_batch else [None]):
                record = copy.deepcopy(raw)
                sid = record["Sample_ID"] + "_" + batch if batch is not None else record["Sample_ID"]
                record["Sample_ID"] = sid
                project = record.get("Project_ID")
                if not _blank(project):
                    metadata_projects.setdefault(sid, set()).update(str(project).split(","))
                if sid in metadata:
                    previous = metadata[sid]
                    for column, value in record.items():
                        if column in ("Flowcell_Name", "Flowcell_ID", "Project_ID"):
                            values = [str(v) for v in (previous.get(column), value) if not _blank(v)]
                            record[column] = ",".join(dict.fromkeys(values)) if values else pd.NA
                        elif column in previous and _plain(previous[column]) != _plain(value):
                            result.add("warning", "metadata.cross_form_override", "Sample_ID {!r}: {} differs between forms; the later form takes precedence.".format(sid, column), file=form["path"], column=column, sample_id=sid, details={"previous_file": metadata_sources[sid], "previous_value": _plain(previous[column]), "value": _plain(value)})
                    previous.update(record)
                else:
                    metadata[sid] = record
                metadata_sources[sid] = form["path"]
    result.metadata = pd.DataFrame(list(metadata.values())) if metadata else pd.DataFrame(columns=["Sample_ID"])
    result.metadata.index = result.metadata.Sample_ID

    # Compare only if every prerequisite parsed successfully; unrelated parse
    # failures must not cause misleading 'missing sample' cascades.
    can_match = len(result.sheets) == len(samplesheets) and len(result.forms) == len(submission_forms) and bool(samplesheets) and bool(submission_forms)
    if can_match:
        for sid in sorted(set(planned) - set(metadata)):
            normalized = sid.strip()
            near = sorted(key for key in metadata if key.strip() == normalized)
            merge_losses = []
            for form in result.forms:
                raw_id = sid.rsplit("_", 1)[0] if keep_batch else sid
                c, l = set(form["customer"]["data"].Sample_ID), set(form["lab"]["data"].Sample_ID)
                if l and ((raw_id in c) != (raw_id in l)):
                    missing_sheet = LAB_SHEET if raw_id in c else CUSTOMER_SHEET
                    merge_losses.append({"file": form["path"], "worksheet": missing_sheet})
                for candidate in c | l:
                    if candidate.strip() == raw_id.strip() and candidate != raw_id:
                        near.append(candidate)
            if near:
                result.add("error", "sample.whitespace_mismatch", "Sample_ID {!r} has only whitespace-differing metadata matches: {}. Correct the inputs; IDs are not rewritten.".format(sid, ", ".join(repr(value) for value in sorted(set(near)))), sample_id=sid, details={"candidates": sorted(set(near))})
            elif merge_losses:
                for loss in merge_losses:
                    result.add("error", "sample.merge_loss", "SampleSheet Sample_ID {!r} is lost during the customer/lab inner join; it is missing from worksheet {!r}.".format(sid, loss["worksheet"]), sample_id=sid, **loss)
            else:
                result.add("error", "sample.missing_metadata", "SampleSheet Sample_ID {!r} is absent from effective submission metadata.".format(sid), sample_id=sid)
        for sid, item in planned.items():
            project_set = metadata_projects.get(sid, set())
            if project_set and project_set != set(item["project_ids"]):
                result.add("warning", "sample.project_precedence", "Sample_ID {!r}: submission projects {} differ from SampleSheet projects {}; SampleSheet takes precedence.".format(sid, sorted(project_set), item["project_ids"]), sample_id=sid, column="Project_ID")
    extras = sorted(set(metadata) - set(planned))
    if extras and can_match:
        result.add("info", "metadata.extra_samples", "{} extra submission sample(s) are valid and omitted from the planned analysis: {}.".format(len(extras), ", ".join(extras)), details={"sample_ids": extras, "count": len(extras)})
    for sid, item in planned.items():
        item["sample_group"] = _plain(metadata.get(sid, {}).get("Sample_Group"))
    projects = {}
    for item in planned.values():
        for pid in item["project_ids"]:
            entry = projects.setdefault(pid, {"project_id": pid, "sample_count": 0, "sample_ids": [], "sample_groups": []})
            entry["sample_ids"].append(item["sample_id"])
            entry["sample_count"] += 1
            if item["sample_group"] is not None and item["sample_group"] not in entry["sample_groups"]:
                entry["sample_groups"].append(item["sample_group"])
    group_values = [_plain(item.get("Sample_Group")) for item in metadata.values()]
    result.summary = {
        "samplesheet_rows": len(selected_rows), "planned_sample_count": len(planned),
        "submission_sample_count": len(metadata), "extra_submission_sample_count": len(extras),
        "planned_samples": list(planned.values()), "projects": list(projects.values()),
        "sample_groups": {"values": sorted({str(value) for value in group_values if value is not None}), "missing_count": sum(value is None for value in group_values), "sample_count": len(metadata)},
        "matching_complete": can_match,
    }
    return result
