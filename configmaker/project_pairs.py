"""Filename-paired, project-scoped metadata and whole-flowcell validation.

This additive contract does not change ``validate_inputs``' intentional merging
of samples from older flowcells. No inputs or operational outputs are written.
Index rows here contain literal nucleotide sequences; symbolic index expansion
belongs to the shared index-normalization producer, not to this module.
"""

import copy
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from configmaker.libprep import LibprepConfig, LibprepConfigError, validate_read_geometry
from configmaker.validation import ValidationResult, _paths, _read, parse_samplesheet, validate_inputs

PROJECT_PAIR_API_VERSION = 1
_PROJECT = re.compile(r"(?<![A-Za-z0-9])GCF-\d{4}-\d{3}(?![A-Za-z0-9])")
PER_SAMPLE_SETTINGS = frozenset({"OverrideCycles", "BarcodeMismatchesIndex1", "BarcodeMismatchesIndex2",
                                 "AdapterRead1", "AdapterRead2", "AdapterBehavior", "AdapterStringency"})


@dataclass(frozen=True)
class ProjectPair:
    project_id: str
    sample_sheet: str
    submission_form: str

    @property
    def samplesheet(self):
        return self.sample_sheet

    def to_dict(self):
        return dict(project_id=self.project_id, sample_sheet=self.sample_sheet,
                    submission_form=self.submission_form)


@dataclass
class ProjectPairResult(ValidationResult):
    pairs: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    mode: str = "project_pairs"
    project_results: dict = field(default_factory=dict)
    assignments: list = field(default_factory=list)
    project_geometry: dict = field(default_factory=dict)
    project_settings: dict = field(default_factory=dict)
    selections: dict = field(default_factory=dict)

    def to_dict(self):
        report = super().to_dict()
        report.update(kind="project_pairs", project_pair_api_version=PROJECT_PAIR_API_VERSION,
                      mode=self.mode, pairs=[pair.to_dict() for pair in self.pairs],
                      duplicates=copy.deepcopy(self.duplicates),
                      assignments=copy.deepcopy(self.assignments),
                      project_geometry=copy.deepcopy(self.project_geometry),
                      project_settings=copy.deepcopy(self.project_settings),
                      libprep_selections=copy.deepcopy(self.selections),
                      project_reports={key: value.to_dict() for key, value in self.project_results.items()})
        return report

    def render_text(self):
        contextual = copy.copy(self)
        contextual.findings = [dict(finding, message="Project {}: {}".format(finding["project_id"], finding["message"]))
                               if finding.get("project_id") else finding for finding in self.findings]
        return ValidationResult.render_text(contextual)


def _filename_key(path, result):
    keys = list(dict.fromkeys(_PROJECT.findall(Path(path).name)))
    if len(keys) > 1:
        result.add("error", "pair.ambiguous_filename", "Filename names multiple GCF projects; use one GCF-YYYY-NNN key.",
                   file=path, details={"project_ids": keys})
    return keys[0] if len(keys) == 1 else None


def resolve_project_pairs(samplesheets, submission_forms):
    """Read/hash and pair filenames deterministically, suppressing exact sheets.

    One effective sheet/form retains legacy selection, including multi-project
    content. Every effective input in multi-pair mode must name one GCF-YYYY-NNN.
    Qualified sheets for different projects are never discarded as duplicates.
    """
    result = ProjectPairResult()
    sheet_items, form_items = [], []
    for kind, paths, items in (("samplesheet", samplesheets, sheet_items),
                               ("submission_form", submission_forms, form_items)):
        for value in sorted({str(Path(p).expanduser().absolute()) for p in _paths(paths)}):
            path, content = _read(value, kind, result)
            if content is not None:
                items.append(dict(path=path, key=_filename_key(path, result),
                                  sha256=hashlib.sha256(content).hexdigest()))
    if not sheet_items:
        result.add("error", "input.missing_samplesheet", "No readable SampleSheet inputs were supplied.")
    if not form_items:
        result.add("error", "input.missing_submission_form", "No readable submission-form inputs were supplied.")
    # Prefer qualified names, then lexical absolute paths. An unqualified copy
    # cannot bridge two explicitly distinct projects with the same bytes.
    effective = []
    for item in sorted(sheet_items, key=lambda item: (item["key"] is None, item["path"])):
        same = [old for old in effective if old["sha256"] == item["sha256"]]
        compatible = [old for old in same if old["key"] == item["key"] or item["key"] is None]
        distinct = [old for old in same if old["key"] and item["key"] and old["key"] != item["key"]]
        if distinct:
            result.add("error", "pair.identical_cross_project_sheets",
                       "Identical SampleSheets explicitly name different projects; correct filenames/content.",
                       file=item["path"], project_id=item["key"], details={"other_files": [old["path"] for old in distinct]})
        if compatible:
            representative = compatible[0]
            result.duplicates.append(dict(path=item["path"], sha256=item["sha256"],
                                          retained=representative["path"]))
            result.add("info", "pair.duplicate_samplesheet", "Byte-identical SampleSheet ignored.",
                       file=item["path"], details={"retained": representative["path"], "sha256": item["sha256"]})
        else:
            effective.append(item)
    if len(effective) == len(form_items) == 1:
        sheet, form = effective[0], form_items[0]
        # A sole historical pair need not have matching naming conventions.
        # Explicitly contradictory project keys are still actionable errors.
        if sheet["key"] is None or form["key"] is None or sheet["key"] == form["key"]:
            result.mode = "legacy"
            result.pairs.append(ProjectPair(None, sheet["path"], form["path"]))
            return result
    if len(effective) != len(form_items):
        result.add("error", "pair.count_mismatch", "After exact-sheet deduplication there must be one sheet and one form per project.",
                   details={"samplesheets": len(effective), "submission_forms": len(form_items)})
    grouped = []
    for kind, items in (("samplesheet", effective), ("submission_form", form_items)):
        by_key = {}
        for item in items:
            if item["key"] is None:
                result.add("error", "pair.missing_filename_key", "Multi-pair input filenames must name exactly one GCF-YYYY-NNN project.", file=item["path"])
                continue
            by_key.setdefault(item["key"], []).append(item["path"])
        for key, paths in by_key.items():
            if len(paths) > 1:
                result.add("error", "pair.duplicate_" + kind,
                           "Project {!r} has multiple {} candidates; retain one authoritative input.".format(key, kind),
                           project_id=key, details={"files": paths})
        grouped.append(by_key)
    sheets_by_key, forms_by_key = grouped
    if set(sheets_by_key) != set(forms_by_key):
        result.add("error", "pair.project_set_mismatch", "SampleSheet and submission-form filename project sets differ.",
                   details={"missing_forms": sorted(set(sheets_by_key) - set(forms_by_key)),
                            "missing_samplesheets": sorted(set(forms_by_key) - set(sheets_by_key))})
    for key in sorted(set(sheets_by_key) | set(forms_by_key)):
        sheets, forms = sheets_by_key.get(key, []), forms_by_key.get(key, [])
        if not sheets or not forms:
            result.add("error", "pair.missing_partner", "Project {!r} is missing its {}.".format(key, "SampleSheet" if not sheets else "submission form"), project_id=key)
        elif len(sheets) == len(forms) == 1:
            result.pairs.append(ProjectPair(key, sheets[0], forms[0]))
    return result


def _parsed_sheet(sheet):
    if isinstance(sheet, dict):
        return sheet
    result = ValidationResult()
    path, content = _read(sheet, "samplesheet", result)
    parsed = parse_samplesheet(content, path, result) if content is not None else None
    if not result.ok:
        raise LibprepConfigError(result.render_text())
    return parsed


def samplesheet_settings(sheet):
    """Return exact demultiplexer settings; reject conflicting section entries."""
    settings = {}
    for section in ("settings", "bclconvert_settings"):
        for cells in sheet.get("sections", {}).get(section, []):
            key, value = cells[0].strip(), cells[1].strip() if len(cells) > 1 else ""
            if key in settings and settings[key] != value:
                raise LibprepConfigError("Conflicting setting {!r} in {}".format(key, sheet["path"]))
            settings[key] = value
    return settings


def _run_geometry(run_info):
    if run_info is None:
        return None, None
    try:
        root = ET.fromstring(run_info) if isinstance(run_info, bytes) else ET.parse(run_info).getroot()
        reads = [(int(node.attrib["NumCycles"]), node.attrib["IsIndexedRead"].upper() == "Y")
                 for node in root.findall(".//Reads/Read")]
        if not reads or any(cycles <= 0 for cycles, indexed in reads):
            raise ValueError("no positive physical read cycles")
        if any(node.attrib["IsIndexedRead"].upper() not in ("Y", "N") for node in root.findall(".//Reads/Read")):
            raise ValueError("IsIndexedRead must be Y or N")
        validate_read_geometry([cycles for cycles, indexed in reads if not indexed])
        layout = root.find(".//FlowcellLayout")
        lanes = int(layout.attrib["LaneCount"]) if layout is not None else None
        return reads, lanes
    except (OSError, ET.ParseError, KeyError, ValueError) as error:
        raise LibprepConfigError("Cannot determine physical run geometry from {}: {}".format(run_info, error)) from error


def _override_geometry(mask, physical, include_indexes=False):
    tokens = str(mask).split(";")
    if physical is not None and len(tokens) != len(physical):
        raise LibprepConfigError("OverrideCycles has {} reads; physical run has {}".format(len(tokens), len(physical)))
    geometry, index_geometry = [], []
    for i, token in enumerate(tokens):
        parts = re.findall(r"([YIUN])([1-9][0-9]*|\*)", token.upper())
        if not parts or "".join(letter + count for letter, count in parts) != token.upper():
            raise LibprepConfigError("Unsupported OverrideCycles token {!r}".format(token))
        if any(count == "*" for letter, count in parts):
            if physical is None or sum(count == "*" for letter, count in parts) > 1:
                raise LibprepConfigError("OverrideCycles '*' requires an unambiguous physical run geometry")
            remaining = physical[i][0] - sum(int(count) for letter, count in parts if count != "*")
            if remaining <= 0:
                raise LibprepConfigError("OverrideCycles exceeds physical read length")
            parts = [(letter, str(remaining) if count == "*" else count) for letter, count in parts]
        total = sum(int(count) for letter, count in parts)
        if physical is not None and total != physical[i][0]:
            raise LibprepConfigError("OverrideCycles consumes {} cycles; physical read {} has {}".format(total, i + 1, physical[i][0]))
        y_cycles = sum(int(count) for letter, count in parts if letter == "Y")
        i_cycles = sum(int(count) for letter, count in parts if letter == "I")
        if physical is not None and physical[i][1]:
            index_geometry.append(i_cycles)
        elif physical is not None and i_cycles:
            raise LibprepConfigError("OverrideCycles assigns index cycles to a physical biological read")
        if y_cycles:
            if physical is not None and physical[i][1]:
                raise LibprepConfigError("OverrideCycles assigns biological cycles to a physical index read")
            geometry.append(y_cycles)
    geometry = list(validate_read_geometry(geometry))
    return (geometry, index_geometry) if include_indexes else geometry


def derive_project_geometry(sheet, run_info=None):
    """Resolve effective biological cycles independently of physical run cycles.

    Row-level OverrideCycles wins over the sheet setting. Uniform [Reads] is a
    fallback without RunInfo; physical RunInfo is authoritative when supplied.
    Heterogeneous output layouts within one project are explicitly unsupported.
    """
    sheet = _parsed_sheet(sheet)
    settings = samplesheet_settings(sheet)
    physical, _lanes = _run_geometry(run_info)
    declared = []
    for row in sheet.get("sections", {}).get("reads", []):
        if not row[0].strip():
            continue
        try:
            declared.append(int(row[0]))
        except ValueError as error:
            raise LibprepConfigError("Invalid [Reads] cycle count in {}".format(sheet["path"])) from error
    fallback = [cycles for cycles, indexed in physical if not indexed] if physical else declared
    layouts = set()
    for row in sheet["records"]:
        mask = row.get("OverrideCycles") or settings.get("OverrideCycles")
        geometry = _override_geometry(mask, physical) if mask else list(validate_read_geometry(fallback))
        layouts.add(tuple(geometry))
    if len(layouts) != 1:
        raise LibprepConfigError("Project has different effective biological read layouts; split the unsupported project definition")
    return list(next(iter(layouts)))


def _allowance(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-2]", str(value)):
        raise LibprepConfigError("Barcode mismatch allowances must be integer 0, 1 or 2")
    return int(value)


def _overlap(left, right):
    return left == "*" or right == "*" or left == right


def _distance(left, right):
    # N is conservatively a wildcard; unequal lengths share a possible prefix
    # assignment and must be resolved rather than assumed collision-free.
    return sum(a != b and a != "N" and b != "N" for a, b in zip(left, right))


def validate_project_pairs(samplesheets, submission_forms, *, run_info=None,
                           libprep_config=None, mismatch_policy=None):
    """Validate each pair independently, then all normalized lane/index outputs.

    ``mismatch_policy`` is an integer for both indexes or an ``index``/``index2``
    mapping; default is one mismatch each. Sheet/row mismatch settings take
    precedence. All pairs are checked, regardless of an eventual BFQ selection.
    ``run_info`` is a physical RunInfo.xml path; ``libprep_config`` is a snapshot
    or path. Missing physical geometry skips geometry checks unless [Reads] or
    OverrideCycles supplies an effective layout. Report inputs bind every file.
    """
    result = resolve_project_pairs(samplesheets, submission_forms)
    physical, lane_count, captured_run_info = None, None, None
    if run_info is not None:
        _path, captured_run_info = _read(run_info, "run_info", result)
        try:
            physical, lane_count = _run_geometry(captured_run_info) if captured_run_info is not None else (None, None)
        except LibprepConfigError as error:
            result.add("error", "demux.run_geometry", str(error), file=str(run_info))
    snapshot = None
    if libprep_config is not None:
        try:
            snapshot = libprep_config if isinstance(libprep_config, LibprepConfig) else LibprepConfig.load(libprep_config)
            result.inputs.append(dict(kind="libprep_config", path=snapshot.source, sha256=snapshot.sha256, size_bytes=len(snapshot.content)))
        except LibprepConfigError as error:
            result.add("error", "libprep.invalid_config", str(error))
    try:
        policy = ({"index": mismatch_policy, "index2": mismatch_policy} if isinstance(mismatch_policy, int)
                  else mismatch_policy or {"index": 1, "index2": 1})
        policy = {key: _allowance(policy.get(key, 1)) for key in ("index", "index2")}
    except (LibprepConfigError, AttributeError) as error:
        result.add("error", "demux.mismatch_policy", str(error))
        policy = {"index": 1, "index2": 1}
    project_summaries = []
    for pair in result.pairs:
        validated = validate_inputs([pair.sample_sheet], [pair.submission_form])
        key = pair.project_id or "legacy"
        result.project_results[key] = validated
        for finding in validated.findings:
            result.findings.append(dict(finding, project_id=pair.project_id) if pair.project_id else copy.deepcopy(finding))
        expected_hashes = {item["path"]: item["sha256"] for item in result.inputs}
        for item in validated.inputs:
            if item["sha256"] != expected_hashes.get(item["path"]):
                result.add("error", "input.changed_during_validation", "Input changed after pairing; retry with fixed input files.", file=item["path"])
        project_summaries.extend(validated.summary.get("projects", []))
        if not validated.sheets:
            continue
        sheet = validated.sheets[0]
        if result.mode == "legacy":
            # Filename-paired restrictions must not redefine historical
            # multi-project or unindexed/manual-analysis acceptance.
            continue
        if pair.project_id:
            for row in sheet["records"]:
                if row["Sample_Project"] != pair.project_id:
                    result.add("error", "pair.sheet_project_conflict", "Filename project differs from Sample_Project; project assignments are not borrowed or rewritten.",
                               project_id=pair.project_id, file=pair.sample_sheet, row=row["_row"], column="Sample_Project", sample_id=row["Sample_ID"], details={"value": row["Sample_Project"]})
            for finding in validated.findings:
                if finding["code"] == "sample.project_precedence":
                    result.add("error", "pair.form_project_conflict", "Submission project contradicts the filename/SampleSheet project; correct the pair.",
                               project_id=pair.project_id, **{k: v for k, v in finding.items() if k not in ("code", "message", "severity")})
        try:
            settings = samplesheet_settings(sheet)
            result.project_settings[key] = settings
            has_geometry = run_info is not None or bool(sheet.get("sections", {}).get("reads")) or settings.get("OverrideCycles") or any(row.get("OverrideCycles") for row in sheet["records"])
            if has_geometry:
                geometry = derive_project_geometry(sheet, run_info=captured_run_info)
                result.project_geometry[key] = geometry
                if snapshot is not None:
                    result.selections[key] = snapshot.select(validated.custom_options.get("Libprep"), geometry).diagnostics()
        except LibprepConfigError as error:
            result.add("error", "demux.project_geometry", str(error), project_id=pair.project_id, file=pair.sample_sheet)
            settings = result.project_settings.get(key, {})
        for row in sheet["records"]:
            pid, sid = row["Sample_Project"], row["Sample_ID"]
            context = dict(project_id=pid, file=pair.sample_sheet, row=row["_row"], sample_id=sid)
            lane = row.get("Lane", "").strip() or "*"
            if lane != "*":
                try:
                    lane = int(lane)
                    if lane <= 0 or (lane_count is not None and lane > lane_count):
                        raise ValueError()
                except ValueError:
                    result.add("error", "demux.invalid_lane", "Lane must be a positive lane number present in the physical run.", column="Lane", **context)
                    continue
            indexes = {}
            for column in ("index", "index2"):
                value = row.get(column, "").upper()
                if value and re.fullmatch("[ACGTN]+", value) is None:
                    result.add("error", "demux.unexpanded_index", "Index must be a normalized nucleotide sequence; expand symbolic index names with the shared index-normalization producer.", column=column, details={"value": row.get(column)}, **context)
                indexes[column] = value
            effective_settings = {name: row.get(name) or settings[name] for name in PER_SAMPLE_SETTINGS if row.get(name) or name in settings}
            try:
                allowances = {column: _allowance(effective_settings.get("BarcodeMismatchesIndex" + str(i), policy[column]))
                              for i, column in enumerate(("index", "index2"), 1)}
            except LibprepConfigError as error:
                result.add("error", "demux.mismatch_policy", str(error), **context)
                allowances = policy.copy()
            if physical is not None:
                physical_indexes = [cycles for cycles, indexed in physical if indexed]
                if effective_settings.get("OverrideCycles"):
                    try:
                        _geometry, physical_indexes = _override_geometry(effective_settings["OverrideCycles"], physical, include_indexes=True)
                    except LibprepConfigError:
                        # The contextual project-geometry finding above reports
                        # the malformed mask without a dependent index cascade.
                        continue
                for i, column in enumerate(("index", "index2")):
                    if indexes[column] and (i >= len(physical_indexes) or len(indexes[column]) != physical_indexes[i]):
                        result.add("error", "demux.index_geometry", "Index sequence length must match the corresponding effective index cycles.", column=column, **context)
            result.assignments.append(dict(source_sheet=pair.sample_sheet, row=row["_row"], project_id=pid,
                                           sample_id=sid, lane=lane, **indexes, mismatches=allowances,
                                           settings=effective_settings, effective_read_geometry=result.project_geometry.get(key)))
    if result.mode == "project_pairs":
        all_global_keys = set().union(*(set(settings) for settings in result.project_settings.values())) - PER_SAMPLE_SETTINGS
        for setting in sorted(all_global_keys):
            values = {key: settings.get(setting) for key, settings in result.project_settings.items()}
            if len(set(values.values())) > 1:
                result.add("error", "demux.incompatible_settings",
                           "Global demultiplexer setting {!r} differs between projects; provide compatible settings before processing.".format(setting),
                           column=setting, details={"project_values": values})
    assignments = result.assignments
    for i, right in enumerate(assignments):
        for left in assignments[:i]:
            context = dict(project_id=right["project_id"], file=right["source_sheet"], row=right["row"], sample_id=right["sample_id"], details={"previous_assignment": left})
            if left["project_id"] != right["project_id"] and left["sample_id"] == right["sample_id"]:
                result.add("error", "demux.cross_project_sample_id", "Repeated Sample_ID across independent projects is unsupported; choose distinct source IDs before processing.", **context)
            if not _overlap(left["lane"], right["lane"]):
                continue
            if all(_distance(left[column], right[column]) <= left["mismatches"][column] + right["mismatches"][column] for column in ("index", "index2")):
                result.add("error", "demux.index_collision", "Lane/index assignments overlap under the selected mismatch allowances.", **context)
    planned = [item for value in result.project_results.values() for item in value.summary.get("planned_samples", [])]
    result.summary = dict(projects=project_summaries, planned_samples=planned, planned_sample_count=len(planned),
                          pair_count=len(result.pairs), assignment_count=len(assignments), matching_complete=result.ok)
    return result
