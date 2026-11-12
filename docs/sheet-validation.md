# Sheet-only validation and CSV preservation (API 1)

`gcf-tools 0.5.0` adds this boundary for [gcf-tools #104](https://github.com/gcfntnu/gcf-tools/issues/104),
following the [SS Manager contract](https://github.com/gcfntnu/ss_manager/pull/19).
It extends the [input-validation contract](input-validation.md); it does not change
`validate_inputs`, metadata/report API 1, project-pair API 1, or index API 1.
SS Manager #15–#18 own application integration, export authority/review, v2 UI and configuration snapshots.

## Calls and result

The `configmaker.samplesheet` module exposes:

```python
from configmaker.samplesheet import SHEET_API_VERSION, validate_samplesheet_bytes

assert SHEET_API_VERSION == 1
result = validate_samplesheet_bytes(
    uploaded_bytes, source="uploaded.csv", profile="portable-converter",
)
report = result.to_dict()
if not result.ok:
    raise ValueError(result.render_text())
# Use the preserved strings for review/export; assignments are normalized views.
rows = [row["cells"] for row in report["document"]["rows"]]
options = report["custom_options"]
```

`validate_samplesheet(path, *, profile="metadata")` reads one local path once.
`validate_samplesheet_bytes(content, *, source="<memory>", profile="metadata")`
accepts bytes already held by an intake application. Both hash exactly the bytes parsed, including a UTF-8 BOM.
They collect input/parse/validation errors in `SampleSheetResult`; invalid Python
argument types or an unknown profile raise `TypeError`/`ValueError`.
No form, FASTQ, workflow, service or run directory is required.

The result exposes `ok`, `findings`, `inputs`, `summary`, `document`, `assignments`,
`custom_options`, `to_dict()` and `render_text()`. `to_dict()` returns an independent
JSON-serializable snapshot. Failed results are diagnostic only and must never be
used for export or processing. A parse failure may leave a partial document.

The report has the common `schema_version: 1`, `validator` (name, package version,
API version), `status`, `inputs`, `errors`, `warnings`, `info`, and `summary` fields,
and adds `kind: samplesheet`, `sheet_api_version: 1`, `profile`, `document`,
`assignments` and `custom_options`. Consumers check kind, sheet API and status,
branch on finding codes, and tolerate additive unknown fields. `inputs` contains
one `kind: samplesheet` identity with source path, SHA-256 and size; an unreadable
path has null hash/size. In-memory sources are caller labels, not resolved paths.

## Preservation document

`document` contains `encoding: utf-8`, `bom` (boolean), `rows` (ordered CSV rows),
`sections` (ordered section occurrences), `data_section`, and `columns`.
Each row is `{row, end_row, cells}`: physical starting/ending 1-based line numbers
and exact decoded CSV strings. Each section is `{name, row, end_row, cells, rows}`:
original tag name, tag location/cells and its ordered content rows. The top-level
rows include section tags, preamble and blanks so no meaningful cells disappear.
Section names, headers, unknown fields, order, quotes inside cells, Unicode,
commas and embedded newlines survive. CSV syntax/line endings, quoting style and
BOM are not a byte-for-byte generated-file promise; retain the original bytes.

`document.columns` is the exact data header cells, including empty trailing
export columns. `data_section` retains `Data` or `BCLConvert_Data` spelling.
Unknown sections produce a passthrough notice, without semantic approval.
Reusing `csv.writer` on `row['cells']` produces comma CSV with the same cell
values. No writer mutates inputs or applies SS Manager's form/export policy.

`custom_options` is an ordered list of `{key, value, row, end_row, column, logical_key}`.
`row`/`end_row` locate the source record and `column: 2` identifies its value
cell (1-based). `key` and `value` are exact first/second cell text, including
blanks, spaces, false, decimals and case-insensitive true. `logical_key` is the canonical known
option name, or the original unknown key. Further empty export cells remain in
`document`; populated surplus fields in key/value sections fail `samplesheet.option_width`.
The historical typed `validate_inputs(...).custom_options` dictionary is separate
and keeps its true coercion and Organism N/A handling. It is never an export
source for this API: raw true/false/blank/decimal values stay strings here.

## Profiles and ownership

Both profiles enforce UTF-8 with optional BOM and strict comma CSV quoting,
nonambiguous sections/columns/options and existing metadata-library consistency.
No delimiter or encoding guessing occurs. Explicit delimiter conversion belongs
to the intake caller and must retain its original-byte identity separately.
IEM and v2 are accepted; a legacy Reads section is not required for v2.

`metadata` keeps the existing broader exact ASCII sample-ID acceptance and
metadata-only index/lane semantics. This new API's structural ambiguity checks
are stricter than the historical parser; existing metadata callers are unchanged.

`portable-converter` additionally requires nonempty Sample_ID matching exactly
`[A-Za-z0-9_-]+`; it never strips, repairs or transliterates IDs. Literal NA,
leading zeroes and case stay exact. Project IDs must be nonempty; the facility
GCF-YYYY-NNN/counter rule remains in SS Manager. A supplied nonblank Sample_Name
that differs from Sample_ID generates a review warning, without clearing it.

Absent Lane or an empty lane cell means all lanes (`*`). Explicit values must
match `[0-9]+` and be greater than zero; whitespace, signs, fractions and embedded
text fail. Numeric values must be representable by the Python interpreter;
no physical lane bound is imposed. Mixed all-lane and explicit lane scope within
one sheet fails. Leading zeroes are preserved in the document and reported as a representation notice;
normalized assignment lanes are positive integers.

Indexes are normalized in full through `configmaker.indexes`, including literal
N and the packaged GA/TT catalogue. Nothing truncates a malformed suffix. Named
dual indexes require explicit `Index2Orientation` (forward or reverse-complement);
literal sequences are already oriented. Missing both indexes is an unindexed
assignment; index2 without index fails. Logical library consistency follows the
existing parser rules: repeated IDs require the same project/ordinary metadata,
allow distinct lanes and distinct oligos, and reject duplicate/overlapping exact
assignments, including duplicates exposed by normalization. Distinct sample IDs
with the same complete index pair on overlapping lanes fail an exact collision
check. No mismatch allowance, index length, physical lane bounds or run-specific
capability is inferred.

`assignments` is empty for metadata profile. Portable assignments contain
`source_sheet`, `row`, `end_row`, `sample_id`, `project_id`, `lane`, `index`,
`index2`, and `index_provenance` (original cells, oligo ordinal, explicit/catalogue
representation, selected orientation and catalogue identity). Raw cells remain
unchanged. Expansion/case/lane notices describe normalized representations;
they do not authorize changing export cells.

No profile validates workbooks, chooses a kit/backend, schedules processing,
asserts physical geometry or fetches configuration. Use the existing
`LibprepConfig` and project-pair/run-aware validation when that context exists.
Reports explicitly list those deferred checks. Passing this intake profile does
not establish converter or scientific compatibility.

## Diagnostic policy

Cell findings carry `file`, physical starting `row`, `end_row`, named `column`
and `details.value` where applicable; duplicate/conflict findings identify earlier
rows. Failed structural or library checks suppress dependent assignment checks.
CSV errors identify their physical line; byte-decoding errors identify the
byte offset. Existing metadata codes retain their meaning. New codes cover:

| Code | Meaning |
| --- | --- |
| `samplesheet.duplicate_section` | Repeated section name, case-insensitively, including unknown sections |
| `samplesheet.duplicate_columns` | Duplicate nonblank data headers, including case aliases |
| `samplesheet.conflicting_option` | Conflicting exact values for one logical key |
| `samplesheet.duplicate_option` | Identical duplicate logical key retained, with notice |
| `samplesheet.missing_option_key` | Populated option has no key |
| `samplesheet.option_width` | Populated surplus fields make a key/value row ambiguous |
| `samplesheet.option_alias` | Known key uses a noncanonical spelling; original retained |
| `samplesheet.unknown_section` | Cells retained without semantic validation |
| `samplesheet.parse_failed` | Undecodable UTF-8 or malformed CSV quoting |
| `sample.invalid_portable_id` | Sample_ID violates the explicit portable alphabet |
| `sample.name_review` | Nonblank Sample_Name differs from Sample_ID |
| `samplesheet.invalid_lane` | Lane is not a positive whole ASCII decimal value |
| `samplesheet.mixed_lane_scope` | Blank/all-lane and explicit lanes occur together |
| `samplesheet.lane_normalized` | Assignment lane representation differs from source text |
| `samplesheet.index_normalized` | Uppercase or catalogue assignment differs from source cells |
| `samplesheet.index_collision` | Exact normalized index pairs overlap across libraries |
| `index.*` | Shared index-normalizer failures; index2-only uses index.incomplete_pair |

Reserved CustomOptions logical keys are Organism, Libprep, User, SensitiveData,
Priority, InitialHold, Index2Orientation, Demultiplexer, DemultiplexingPass,
Adapter, AdapterRead2, RemoveHumanReads, SingleCell, TrimAdapter, Rerun,
ReverseComplementIndexP5 and ReverseComplementIndexP7. Known keys compare after
outer-space removal and case folding; unknown keys remain case-sensitive exact
text. Exact duplicate values are retained with a notice; differing raw values
fail before form precedence. Header/settings keys also reject conflicting exact
duplicates. Multiple Data/BCLConvert_Data sections are always ambiguous.

## Consumer adoption and compatibility

The sheet-only API uses the existing runtime packages and adds no Python runtime
floor. gcf-tools 0.5.0 updates the xlrd pin to **2.0.2**, matching SS Manager;
`.xls` and `.xlsx` reading remain covered separately by the workbook tests.
The `xlwt` writer is a test-only development extra.
Consumers must pin the reviewed implementation commit (package **0.5.0** or
later) and check `SHEET_API_VERSION == 1`. Package 0.4.0 lacks this module; its
metadata/index/project-pair API versions do not establish sheet-only availability.
Historical `validate_inputs`, installed commands, BFQ imports and generated files
keep their current behavior. No application or companion implementation is bundled.

The synthetic regressions in `tests/test_samplesheet.py` cover all 22 SS Manager
PR #19 contract cases: IEM/v2, exact IDs, malformed indexes/lanes, complete N
sequences, GA/TT expansion,
duplicates/aliases, UTF-8/BOM, quoted comma/quote/newline cells, exact input hashes,
nonmutation, and retained unknown cells. The installed smoke check also imports
this module from the inspected installation and validates exact ID/index values.
Run the repository's fast and full local gates, including installed wheel/sdist
tests with network/SMTP protection. These do not establish facility, converter, server or scientific integration. Consumer
adoption, lab acceptance and deployment remain separate reviewed work.

`summary` contains `data_row_count` (source rows), `sample_count` (distinct logical
IDs), ordered `project_ids`, expanded `assignment_count`, `validation_complete`,
and `deferred_checks`. Counts can be partial on failure. The deferred checks are
`submission_forms`, `physical_run`, `backend`, `scheduling`, `libprep_selection`
and `mismatch_collisions`; they are never implied by `status: passed`.

For SS Manager adoption, pass original upload bytes with a stable source label,
require `kind == "samplesheet"`, `sheet_api_version == 1` and successful status,
and retain the original bytes/hash alongside the report. Inspect warnings such
as `sample.name_review` before committing a generation. Enforce the application's
GCF project policy against actual data project IDs; no project-count heuristic
or form authority is implemented here. Merge/review/export remains SS Manager
#16 work: use preserved cells/raw options, show replacements/removals, and
revalidate generated comma CSV through the same API. Never reconstruct exports
from normalized assignments or the historical typed options dictionary. Those
views intentionally differ from source spelling. Repeated corrections must still
start from the stored original upload.
