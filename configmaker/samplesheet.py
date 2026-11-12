"""Non-mutating sheet-only validation and CSV preservation, public API 1.

Existing metadata consumers keep using configmaker.validation unchanged. This
module adds an explicit intake profile; it never selects a processing backend.
"""

import copy
import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from configmaker.indexes import IndexNormalizationError, load_catalogue, normalize_indexes, normalize_rows
from configmaker.validation import ValidationResult, parse_samplesheet

SHEET_API_VERSION = 1
_PROFILES = ("metadata", "portable-converter")
_DATA = ("data", "bclconvert_data")
_KEY_VALUE = ("header", "settings", "bclconvert_settings", "customoptions")
_KNOWN_SECTIONS = _DATA + _KEY_VALUE + ("reads",)
_RESERVED_OPTIONS = {key.casefold(): key for key in (
    "Organism", "Libprep", "User", "SensitiveData", "Priority", "InitialHold",
    "Index2Orientation", "Demultiplexer", "DemultiplexingPass", "Adapter", "AdapterRead2",
    "RemoveHumanReads", "SingleCell", "TrimAdapter", "Rerun",
    "ReverseComplementIndexP5", "ReverseComplementIndexP7",
)}
_DEFERRED = ["submission_forms", "physical_run", "backend", "scheduling",
             "libprep_selection", "mismatch_collisions"]


def _empty_document():
    return dict(encoding="utf-8", bom=False, rows=[], sections=[], data_section=None, columns=[])


@dataclass
class SampleSheetResult:
    profile: str = "metadata"
    findings: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    document: dict = field(default_factory=_empty_document)
    custom_options: list = field(default_factory=list)
    assignments: list = field(default_factory=list)

    @property
    def ok(self):
        return not any(item["severity"] == "error" for item in self.findings)

    def add(self, severity, code, message, **context):
        # Keep the common finding envelope without inheriting dataframe internals.
        ValidationResult.add(self, severity, code, message, **context)

    def to_dict(self):
        report = ValidationResult(findings=self.findings, inputs=self.inputs, summary=self.summary).to_dict()
        report.update(kind="samplesheet", sheet_api_version=SHEET_API_VERSION, profile=self.profile,
                      document=copy.deepcopy(self.document), custom_options=copy.deepcopy(self.custom_options),
                      assignments=copy.deepcopy(self.assignments))
        return report

    def render_text(self):
        text = ValidationResult(findings=self.findings).render_text()
        return text.replace("Metadata preflight", "SampleSheet preflight ({})".format(self.profile), 1)


def _new_result(profile):
    if not isinstance(profile, str):
        raise TypeError("profile must be a string")
    if profile not in _PROFILES:
        raise ValueError("Unknown SampleSheet profile {!r}; choose {}.".format(profile, ", ".join(_PROFILES)))
    return SampleSheetResult(profile=profile)


def _context(source, row, column=None, value=None):
    context = dict(file=source, row=row["row"], end_row=row["end_row"], details={"value": value})
    if column is not None:
        context["column"] = column
    return context


def _check_quotes(text):
    """Reject bare quotes that csv.reader(strict=True) treats as literal text."""
    state, line, position = "start", 1, 0
    while position < len(text):
        char = text[position]
        if char == '"':
            if state == "plain":
                return line
            if state == "quoted":
                if position + 1 < len(text) and text[position + 1] == '"':
                    position += 2
                    continue
                state = "closed"
            elif state == "start":
                state = "quoted"
        elif state != "quoted":
            if char in ",\r\n":
                state = "start"
            elif state == "closed":
                return line
            else:
                state = "plain"
        if char == "\n" or (char == "\r" and (position + 1 == len(text) or text[position + 1] != "\n")):
            line += 1
        position += 1
    return None  # csv.reader diagnoses unterminated quoted fields.


def _read_document(content, source, result):
    result.document["bom"] = content.startswith(b"\xef\xbb\xbf")
    bom_size = 3 if result.document["bom"] else 0
    try:
        text = content[bom_size:].decode("utf-8")
    except UnicodeDecodeError as error:
        result.add("error", "samplesheet.parse_failed", "SampleSheet must be UTF-8 (optional BOM).",
                   file=source, details={"byte_offset": bom_size + error.start})
        return
    bad_line = _check_quotes(text)
    if bad_line is not None:
        result.add("error", "samplesheet.parse_failed", "Malformed CSV quoting.",
                   file=source, row=bad_line, end_row=bad_line)
        return
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    end_row = 0
    try:
        for cells in reader:
            result.document["rows"].append(dict(row=end_row + 1, end_row=reader.line_num, cells=cells))
            end_row = reader.line_num
    except csv.Error as error:
        result.add("error", "samplesheet.parse_failed", "Cannot parse SampleSheet: {}".format(error),
                   file=source, row=end_row + 1, end_row=reader.line_num)


def _sections(source, result):
    section, seen, data_sections = None, {}, []
    for row in result.document["rows"]:
        cells = row["cells"]
        tag = cells[0].strip() if cells else ""
        if tag.startswith("[") and tag.endswith("]") and all(not cell.strip() for cell in cells[1:]):
            name = tag[1:-1]
            key = name.lower()
            section = dict(name=name, row=row["row"], end_row=row["end_row"], cells=list(cells), rows=[])
            result.document["sections"].append(section)
            if key in seen:
                context = _context(source, row, "section", cells[0])
                context["details"]["previous_rows"] = [seen[key]]
                result.add("error", "samplesheet.duplicate_section", "Repeated section {!r} is ambiguous.".format(name), **context)
            seen[key] = row["row"]
            if key in _DATA:
                data_sections.append(section)
                if len(data_sections) > 1:
                    result.add("error", "samplesheet.duplicate_data_section", "Multiple data sections are ambiguous.",
                               **_context(source, row, "section", cells[0]))
            elif key not in _KNOWN_SECTIONS:
                result.add("info", "samplesheet.unknown_section", "Section cells retained without semantic validation.",
                           **_context(source, row, "section", cells[0]))
        elif section is not None:
            section["rows"].append(copy.deepcopy(row))
    return data_sections


def _options(source, result):
    for section in result.document["sections"]:
        name = section["name"].lower()
        if name not in _KEY_VALUE:
            continue
        seen = {}
        for row in section["rows"]:
            cells = row["cells"]
            if not cells or not any(cell.strip() for cell in cells):
                continue
            key, value = cells[0], cells[1] if len(cells) > 1 else ""
            logical = (_RESERVED_OPTIONS.get(key.strip().casefold(), key) if name == "customoptions" else key.strip())
            context = _context(source, row, key, value)
            if not key.strip():
                result.add("error", "samplesheet.missing_option_key", "Populated option has no key.", **context)
            if any(cells[2:]):
                result.add("error", "samplesheet.option_width", "Option rows have one key and one value; quote commas within values.", **context)
            if name == "customoptions":
                result.custom_options.append(dict(key=key, value=value, logical_key=logical,
                                                  row=row["row"], end_row=row["end_row"], column=2))
                if logical != key:
                    result.add("warning", "samplesheet.option_alias", "Known option uses a noncanonical spelling; source text retained.", **context)
            if logical in seen:
                previous = seen[logical]
                context["details"].update(previous_rows=[previous["row"]], previous_value=previous["value"])
                if previous["value"] != value:
                    result.add("error", "samplesheet.conflicting_option", "Conflicting values for logical option {!r}.".format(logical), **context)
                else:
                    result.add("info", "samplesheet.duplicate_option", "Identical duplicate logical option retained.", **context)
            seen[logical] = dict(row=row["row"], value=value)


def _data_rows(section, source, result):
    rows = section["rows"]
    header = next((row for row in rows if any(cell.strip() for cell in row["cells"])), None)
    if header is None:
        return None, []
    columns = header["cells"]
    result.document.update(data_section=section["name"], columns=list(columns))
    seen = {}
    for index, column in enumerate(columns, 1):
        if not column:
            continue
        logical = column.casefold()
        if logical in seen:
            context = _context(source, header, column, column)
            context["details"].update(column_index=index, previous_column=seen[logical])
            result.add("error", "samplesheet.duplicate_columns", "Duplicate or case-aliased data columns are ambiguous.", **context)
        seen[logical] = index
    # Keep non-ASCII whitespace in Sample_ID visible to the shared ASCII check.
    sid = columns.index("Sample_ID") if "Sample_ID" in columns else None
    data = [row for row in rows[rows.index(header) + 1:]
            if any(cell.strip() for cell in row["cells"]) or
            (sid is not None and sid < len(row["cells"]) and not row["cells"][sid].isascii())]
    return header, data


def _metadata(columns, header, rows, source, result):
    """Reuse the historical data/library rules, remapping serialized line numbers."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerows([["[Data]"], columns] + [row["cells"] for row in rows])
    text = stream.getvalue()
    locations = [header, header] + rows
    reader = csv.reader(io.StringIO(text, newline=""))
    line_map = {}
    for cells, location in zip(reader, locations):
        line_map[reader.line_num] = location
    shared = ValidationResult()
    parsed = parse_samplesheet(text, source, shared)
    for finding in shared.findings:
        finding = copy.deepcopy(finding)
        location = line_map.get(finding.get("row"))
        if location:
            finding.update(row=location["row"], end_row=location["end_row"])
            details = finding.setdefault("details", {})
            if "previous_rows" in details:
                details["previous_rows"] = list(dict.fromkeys(line_map[line]["row"] for line in details["previous_rows"]))
            column = finding.get("column")
            if column is None and finding["code"].startswith("sample."):
                column = finding["column"] = "Sample_ID"
            values = dict(zip(columns, location["cells"]))
            details.setdefault("value", values.get(column, location["cells"]))
        result.findings.append(finding)
    if parsed is not None:
        for record in parsed["records"]:
            location = line_map[record["_row"]]
            record.update(_row=location["row"], _end_row=location["end_row"])
    return parsed


def _index_column(error, record):
    if error.code in ("index.incomplete_pair", "index.conflicting_pair"):
        return "index2"
    if error.code == "index.invalid_sequence":
        try:
            normalize_indexes(record.get("index", ""))
        except IndexNormalizationError:
            return "index"
        return "index2"
    return "index"


def _portable(parsed, source, result):
    options = {option["logical_key"]: option for option in result.custom_options}
    orientation = options.get("Index2Orientation")
    selected_orientation = orientation["value"] if orientation else "forward"
    if selected_orientation not in ("forward", "reverse-complement"):
        result.add("error", "index.orientation", "Index2Orientation must be forward or reverse-complement.",
                   **_context(source, orientation, "Index2Orientation", selected_orientation))
        return
    try:
        catalogue = load_catalogue()
    except IndexNormalizationError as error:
        result.add("error", error.code, str(error), file=source)
        return
    scopes = set()
    records = {record["_row"]: record for record in parsed["records"]}
    for record in parsed["records"]:
        location = dict(row=record["_row"], end_row=record["_end_row"])
        sid = record["Sample_ID"]
        if re.fullmatch(r"[A-Za-z0-9_-]+", sid) is None:
            result.add("error", "sample.invalid_portable_id", "Sample_ID must match [A-Za-z0-9_-]+ exactly; identifiers are never repaired.",
                       **_context(source, location, "Sample_ID", sid))
        name = record.get("Sample_Name", "")
        if name.strip() and name != sid:
            result.add("warning", "sample.name_review", "Different nonblank Sample_Name requires intake review; source text retained.",
                       **_context(source, location, "Sample_Name", name))
        raw_lane = record.get("Lane", "")
        if raw_lane:
            if re.fullmatch(r"[0-9]+", raw_lane) is None or not raw_lane.strip("0"):
                result.add("error", "samplesheet.invalid_lane", "Lane must be a positive whole ASCII decimal value.",
                           **_context(source, location, "Lane", raw_lane))
                continue
            try:
                lane = int(raw_lane.lstrip("0"))
            except ValueError:
                result.add("error", "samplesheet.invalid_lane", "Lane cannot be represented as an integer by this interpreter.",
                           **_context(source, location, "Lane", raw_lane))
                continue
            if str(lane) != raw_lane:
                result.add("info", "samplesheet.lane_normalized", "Assignment lane canonicalized; original CSV cell retained.",
                           **_context(source, location, "Lane", raw_lane))
        else:
            lane = "*"
        scopes.add(lane == "*")
        if len(scopes) > 1:
            result.add("error", "samplesheet.mixed_lane_scope", "Do not mix all-lane and explicit lane assignments in one sheet.",
                       **_context(source, location, "Lane", raw_lane))
        if not record.get("index") and record.get("index2"):
            result.add("error", "index.incomplete_pair", "index2 requires a complete index assignment in index.",
                       **_context(source, location, "index2", record["index2"]))
            continue
        try:
            normalized = normalize_rows([record], i5_orientation=selected_orientation, catalogue=catalogue)
        except IndexNormalizationError as error:
            column = _index_column(error, record)
            result.add("error", error.code, str(error), **_context(source, location, column, record.get(column, "")))
            continue
        if normalized[0]["_index_provenance"]["representation"] == "catalogue" and normalized[0]["index2"] and orientation is None:
            result.add("error", "index.orientation", "Named dual indexes require explicit Index2Orientation before intake normalization.",
                       **_context(source, location, "index", record.get("index", "")))
            continue
        if any((item["index"], item["index2"]) != (record.get("index", ""), record.get("index2", "")) for item in normalized):
            result.add("info", "samplesheet.index_normalized", "Normalized assignment representation differs; original CSV cells retained.",
                       **_context(source, location, "index", record.get("index", "")))
        for item in normalized:
            result.assignments.append(dict(source_sheet=source, row=location["row"], end_row=location["end_row"],
                                           sample_id=sid, project_id=record["Sample_Project"], lane=lane,
                                           index=item["index"], index2=item["index2"], index_provenance=item["_index_provenance"]))
    if not result.ok:
        return
    # Check normalized lane/index duplicates through the same library rules.
    columns = list(parsed["columns"])
    for column in ("Lane", "index", "index2"):
        if column not in columns:
            columns.append(column)
    canonical = []
    for assignment in result.assignments:
        record = dict(records[assignment["row"]])
        record.update(Lane="" if assignment["lane"] == "*" else str(assignment["lane"]),
                      index=assignment["index"], index2=assignment["index2"])
        canonical.append(dict(row=assignment["row"], end_row=assignment["end_row"],
                              cells=[record.get(column, "") for column in columns]))
    _metadata(columns, dict(row=1, end_row=1), canonical, source, result)
    for index, right in enumerate(result.assignments):
        for left in result.assignments[:index]:
            if left["sample_id"] == right["sample_id"]:
                continue  # Library consistency/duplicates were checked above.
            if left["lane"] != "*" and right["lane"] != "*" and left["lane"] != right["lane"]:
                continue
            if (left["index"], left["index2"]) == (right["index"], right["index2"]):
                context = _context(source, right, "index", records[right["row"]].get("index", ""))
                context["details"]["previous_assignment"] = copy.deepcopy(left)
                result.add("error", "samplesheet.index_collision", "Exact normalized index pairs overlap between different libraries.", **context)


def _validate(content, source, result):
    result.inputs.append(dict(kind="samplesheet", path=source, sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)))
    _read_document(content, source, result)
    parsed, rows = None, []
    if result.ok:
        sections = _sections(source, result)
        _options(source, result)
        if not sections:
            result.add("error", "samplesheet.missing_data", "SampleSheet requires [Data] or [BCLConvert_Data].", file=source)
        elif len(sections) == 1:
            header, rows = _data_rows(sections[0], source, result)
            if header is None:
                result.add("error", "samplesheet.missing_data", "SampleSheet data section requires its column header.", file=source)
            elif result.ok:
                parsed = _metadata(header["cells"], header, rows, source, result)
                if parsed is not None and result.profile == "portable-converter":
                    _portable(parsed, source, result)
    records = parsed["records"] if parsed is not None else []
    result.summary = dict(data_row_count=len(rows), sample_count=len({row["Sample_ID"] for row in records}),
                          project_ids=list(dict.fromkeys(row["Sample_Project"] for row in records)),
                          assignment_count=len(result.assignments), validation_complete=result.ok,
                          deferred_checks=list(_DEFERRED))
    return result


def validate_samplesheet_bytes(content, *, source="<memory>", profile="metadata"):
    """Validate uploaded UTF-8 CSV bytes without writing or requiring a workbook."""
    result = _new_result(profile)
    if not isinstance(content, bytes) or not isinstance(source, str):
        raise TypeError("content must be bytes and source must be a string label")
    return _validate(content, source, result)


def validate_samplesheet(path, *, profile="metadata"):
    """Read one local SampleSheet once and report the identity of those exact bytes."""
    result = _new_result(profile)
    path = Path(path).expanduser().absolute()
    try:
        content = path.read_bytes()
    except (OSError, ValueError) as error:
        result.inputs.append(dict(kind="samplesheet", path=str(path), sha256=None, size_bytes=None))
        result.add("error", "input.unreadable", "Cannot read SampleSheet: {}".format(error), file=str(path))
        result.summary = dict(data_row_count=0, sample_count=0, project_ids=[], assignment_count=0,
                              validation_complete=False, deferred_checks=list(_DEFERRED))
        return result
    return _validate(content, str(path), result)
