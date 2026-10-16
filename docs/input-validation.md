# Shared SampleSheet and submission-form validation

This page owns metadata matching and validator/discovery report contracts.
See [CONTRIBUTING.md](../CONTRIBUTING.md) for setup/checks and
[compatibility.md](compatibility.md) for generated paths, values and later failure
side effects.

`gcf-tools 0.3.0` provides the metadata-only validator used by configmaker and
BFQ/flowcell-manager. It requires no FASTQs, analysis directory, generated
configuration, BFQ installation or network access. Importing it does not create
files or configure logging. Input files are never modified.

## Public API (version 1)

API illustration (substitute private local files; no run output or BFQ is needed):

```python
import json
from configmaker.validation import (
    VALIDATION_API_VERSION, VALIDATOR_VERSION, validate_inputs,
)

result = validate_inputs(
    samplesheets=["/runs/flowcell/SampleSheet.csv"],
    submission_forms=["/runs/flowcell/Sample-Submission-Form.xlsx"],
    project_ids=None,  # None: all projects; otherwise an iterable of project IDs
    keep_batch=False,
    libkit=None,  # Optional standalone kit override; Parse requires multiplexing validation
)
print(result.render_text())
report = result.to_dict()       # ordinary JSON-serializable dictionary
print(json.dumps(report, indent=2))
if not result.ok:
    raise SystemExit(2)
```

The samplesheets/submission_forms arguments accept a path or iterable of paths. Input/read/parse errors
are collected in the result; unexpected programming errors propagate. A result
with `ok == False` must not be used to initialize an analysis. No success cache is
maintained: each call reads and hashes the exact bytes it parses.

The structured report has:

| Field | Meaning |
| --- | --- |
| `schema_version` | `1`; report/API compatibility boundary |
| `validator` | `name`, package `version`, and `api_version` |
| `status` | `passed` or `failed` |
| `inputs` | Ordered `kind`, absolute `path`, `sha256`, `size_bytes`; unreadable inputs have null hash/size |
| `errors`, `warnings`, `info` | Findings with stable `code`, `severity`, `message` and available context |
| `summary` | Planned samples/projects, effective submission sample counts, extra samples and groups |

Finding context uses optional top-level `file`, `worksheet`, `row` (1-based),
`column`, `sample_id` and `details` fields. Consumers should branch on `code`, not
message wording, and ignore unknown fields. The initial code families are
`input.*`, `samplesheet.*`, `workbook.*`, `sample.*` and `metadata.*`.
Important failures include `sample.missing_id`, `sample.missing_metadata`,
`sample.merge_loss`, `sample.whitespace_mismatch`, `sample.conflicting_projects`,
`sample.duplicate_definition`, `workbook.duplicate_id`,
`workbook.duplicate_columns`, `workbook.missing_columns`, and
`workbook.missing_worksheet`, `sample.non_ascii_id`, and
`workbook.non_ascii_wells`. Successful informational results include
`metadata.extra_samples`, `workbook.empty_lab`, and `workbook.merge_excluded`.
Warnings include `sample.project_precedence`, `sample.id_whitespace`,
`samplesheet.option_override`, and `metadata.cross_form_override`.

`summary.planned_samples` holds `sample_id`, `project_ids` and `sample_group` for
each planned analysis sample. `summary.projects` holds each project's sample
count, IDs and groups. `summary.sample_groups` summarizes all effective
submission metadata (`values`, `missing_count`, `sample_count`), including valid
extra submission samples. `matching_complete == False` means a prerequisite
failed; any partial counts must not be interpreted as a successful comparison.

The in-process result also contains `samples` (a dataframe with raw `Sample_ID`
and a list of `Project_ID` values), `metadata` (merged effective dataframe),
`descriptors`, `custom_options`, `header`, and parsed `sheets`/`forms`. Configmaker
uses these objects directly. These dataframe/parser internals are not the JSON
compatibility contract; external consumers should use `to_dict()`.

## Accepted input and matching rules

- UTF-8/BOM CSV SampleSheets support `[Data]` and `[BCLConvert_Data]`, with
  `Sample_ID` and `Sample_Project` columns and at least one sample row. Empty CSV
  export columns and missing trailing optional empty fields are harmless.
- Submission workbooks use `Sample-Submission-Form` (header row 15) and
  `INFO (GCF-lab only)` (header row 1). Existing descriptive headers and bracketed
  column descriptors are supported. The customer sample-ID header is
  `Unique Sample ID`; lab sample IDs use `Sample_ID`. Both worksheets must exist.
  A genuinely empty lab worksheet remains valid and uses customer metadata.
- Nonempty lab data keeps the established **inner join**, with nonempty lab
  columns taking precedence. Customer/lab IDs excluded by this join are listed.
  A SampleSheet sample excluded by it is an error naming the missing worksheet.
- The rule is asymmetric: every selected SampleSheet ID must occur in effective
  metadata. Extra submission samples are informational, never a reason to fail.
- Missing IDs in populated rows and duplicate IDs within a worksheet are errors.
  Fully empty template rows are ignored. Duplicate headers are detected before
  pandas can rename them, including collisions after column mapping.
- Sample IDs must contain only ASCII characters in SampleSheet `Sample_ID`,
  customer `Unique Sample ID`, lab `Sample_ID`, and required Cell Multiplexing
  `Unique Sample ID` cells. Populated multiplexing `Wells` specifications must
  also be ASCII. Reject original values before blank handling, merges,
  descriptor conversion or ordinary-space removal can hide invalid content.
  This is a deliberate tightening of accepted inputs (#71), not a renaming rule.
  It does not restrict comments/descriptive metadata or introduce new ASCII
  punctuation, whitespace or plate-layout rules.
- Identifiers use exact string comparison: text `001` is different from `1`.
  Whitespace is reported and never silently stripped. Store zero-prefixed Excel
  IDs as text; numeric cell display formatting is not an identifier value.
- Distinct explicit lanes may repeat an ID with consistent sample identity and
  project. Lane-specific index/index2/index-name fields may differ; this API
  does not validate sequencing indexes. Same-lane or unscoped duplicates fail.
- Repeated IDs across separate flowcells/forms intentionally merge. Later forms
  override differing ordinary metadata with warnings; project/flowcell values
  accumulate. Different project assignments across separate flowcells remain
  supported. Within a SampleSheet, conflicting projects fail. Submission-versus-
  SampleSheet project differences warn; SampleSheet assignments take precedence.
- `keep_batch=True` gives each planned sample its flowcell suffix. A form beside
  its flowcell is scoped to that batch; an explicitly supplied form located
  elsewhere applies to all requested batches. Discovery uses the same planned
  IDs and per-batch project assignments.
- Parse Biosciences forms additionally require a parseable `Cell Multiplexing`
  worksheet when that library kit is declared in SampleSheet custom options.

Input-format failures suppress dependent sample-matching errors. Independently
readable files/worksheets still get checked in the same call.

### Pooled-library metadata (Parse)

The existing Parse selection condition (SampleSheet or explicit kit override,
including an override away from a Parse SampleSheet) now also rejects populated
biological-only fields on customer and lab library rows: `Sample_Group`,
`Sample_Biosource`, and `External_ID`. Put these annotations on biological rows
in Cell Multiplexing. Other single-cell kits, including ordinary 10x, and unused
multiplexing worksheets do not activate this rule.

Recognition uses the established customer header aliases (`Sample Group`,
`Sample biosource`, `External ID` and their existing prefix mappings), or exact
canonical field names, after bracket descriptors are removed. These same known
biological headers are checked on the lab worksheet even where its ordinary
output mapper would prefix the name with `Lab_`. This validation lookup does not
rename emitted columns or classify arbitrary custom names. For example,
`Library External ID` is permitted and retains the existing custom-column mapping.

Empty/whitespace-only cells, spreadsheet missing values and the exact string
`NA` are missing under the existing non-ID convention. Numeric zero, false and
other populated values are not empty. Checks examine original cells before
identifier conversion, customer/lab joins, descriptor conversion and later-form
overrides. `workbook.pooled_biological_metadata` identifies file, worksheet, row,
canonical column, library `sample_id`, and `details.value`; `details.mapped_column`
records the ordinary worksheet mapping. Inputs are never cleared or repaired.
This deliberately tightens accepted Parse inputs: older workbooks with biological
annotations on library rows need operator correction before processing.

For this multiplexed path only, populated customer `Sample_Type`, `Sample_Buffer`,
`Volume`, `Quantification`, and lab `KIT` columns are retained instead of dropped.
All allowed custom columns continue through the normal mappings, precedence,
descriptors and sample string serialization into `config.samples`. Distinct
library concentrations and zero-valued custom metrics are valid. Existing descriptor
constraints still apply (for example the default `Sample_Type` enum is DNA/RNA);
this retention change does not make arbitrary values valid for constrained fields. Non-multiplexed
column dropping is unchanged. Cell Multiplexing columns remain in `config.wells`
with existing mappings and types (for example `Sample biosource` maps to
`Demux_Sample_Biosource`); well-space normalization is unchanged. No schema rename,
biological relationship inference or general normalization rewrite is introduced.

Tools owns this validation/config propagation. Companion workflows #200 owns
sample/library TSVs, barcode-based AnnData joins and `bfq/metadata/` delivery.
The input section determines metadata ownership, not equality across libraries.

### ASCII diagnostics and kit overrides

`sample.non_ascii_id` and `workbook.non_ascii_wells` are error-level findings.
Each includes file, worksheet when applicable, 1-based row and canonical column.
`details.value` preserves the original string; `details.characters` lists distinct
non-ASCII characters in encounter order as `{character, code_point}` entries
(e.g. `Å`, `U+00C5`, or an invisible nonbreaking space, `U+00A0`). Text diagnostics
also show code points and request input correction. JSON report schema/API remains
1; the optional keyword-only `libkit` argument is additive. No transliteration,
stripping or automatic replacement is offered: `ÅTEST`, `ATEST` and `TEST` are
distinct identities. All independent invalid cells in parsed worksheets are
reported, including rows that would otherwise be discarded by a join or superseded
by a later form. Whitespace-only non-ASCII machine cells are rejected too.

Without `libkit`, the existing SampleSheet selection applies. When `libkit`
selects Parse Biosciences, preflight also requires and validates Cell Multiplexing
before discovery or output creation. The original SampleSheet Parse requirement
is retained even if an override selects a different kit, preserving earlier
validation behavior. `custom_options` remains the original merged SampleSheet
options; the override is not written into it. Non-Parse inputs do not start
validating an unused multiplexing worksheet.

Standalone configmaker passes `--libkit` into this shared preflight and emits
validated `wells` for Parse selected through either route. Previously a Parse
CLI override alone could bypass multiplexing preflight and omit `wells`.
Existing ASCII well-list/range strings and removal of ordinary ASCII spaces
are unchanged. BFQ callers without an override use the same validation entry
point and gain the new rejection rules without a call-signature change.

## Standalone configmaker

Run configmaker as before. It prints metadata diagnostics **before** FASTQ
search, directory/symlink creation, workflow cloning or opening the output config.
Metadata failure exits `2`, preserving an existing config and leaving a new
output path absent. Log messages go to the console; importing configmaker no
longer creates `.configmaker.debug`.

After metadata passes, FASTQ discovery is separate. No matched samples produces
an explicit nonzero error. A partly discovered project retains the existing
behavior of initializing the available samples, with warnings for absent FASTQs.
A successful initialization writes, beside the output config:

- `configmaker.analysis-summary.json`: `schema_version: 1`,
  `kind: fastq_discovery`, `samples` (`sample_id`, `flowcells`), `sample_count`,
  `planned_sample_count`, and `missing_sample_ids`.
- `.configmaker.log`: a readable discovery summary for local inspection.

BFQ copies the JSON summary into flowcell output and uses it separately from
preflight metadata in email reporting. Metadata summaries must not be described
as observed FASTQ counts.

Compatibility parser functions in `configmaker.configmaker` delegate to the
shared parsers. Normal execution reuses its validation result instead of reading
and matching the same metadata again. Identity columns bypass descriptor string
sanitization, preserving IDs and intentional multi-project lists.

## Coordinated deployment and integration tests

The shared validation work in BFQ #121 / gcf-tools #56 is implemented. At the
[inspected BFQ baseline](architecture.md), BFQ requires API 1 / package >= 0.3.0.
Its configmaker call passes its imported `VALIDATOR_VERSION` through
`--expected-validation-version` (0.3.0 at this baseline); a different subprocess
validator version fails before output initialization. Install compatible tools
in both interpreters and rebuild the BFQ image as part of a deliberate deployment.
Do not infer installed versions from this source inspection.

For changes affecting these interfaces, the facility integration gate uses a
copied representative run with isolated state/output paths:

1. Install both branches and run the BFQ manual validation command on a valid
   sheet/form subset with extra submission samples. Confirm passed metadata,
   informational extra IDs, correct Sample_Group summary and input hashes.
2. Use a fresh flowcell. Remove a required sample from customer metadata, then
   from a nonempty lab sheet. Confirm failed preflight names the ID/worksheet and
   BCL conversion never starts. Restore the input and retry normally.
3. Exercise a blank ID on a populated row, duplicate header, same-lane duplicate,
   whitespace mismatch, and truly empty lab worksheet. Invalid cases should fail
   promptly; the empty lab worksheet should pass when customer coverage is valid.
4. Run standalone configmaker on copied historical multi-flowcell fixtures, both
   merged and `--keep-batch`. Check sample IDs, per-batch projects, FASTQ links,
   workflow/kit selection, generated PEP sample metadata and discovery summaries.
5. Use real representative RNA, single-cell and Parse Biosciences workbooks where
   applicable, including custom column descriptors. Confirm existing downstream
   gcf-workflows consume the generated configuration/PEP normally.
6. Test a failed validation with an existing config and a nonexistent output
   parent; both should show input diagnostics without truncating/creating output.

Automated checks and their limits are listed in
[CONTRIBUTING.md](../CONTRIBUTING.md#available-checks). The older CI fixture matrix
also initializes legacy and multi-flowcell/keep-batch projects, but can clone a
moving workflow tree; it is not the offline local acceptance recipe. Real
sequencer conversion, scientific workflow execution and deliberate email delivery
checks remain facility integration. Routine development must mock/block email.

## Issues found during implementation

- A historical RNA test workbook has a free-text note in customer cell J48 with
  no sample ID. This was previously silently lost in the inner join and now
  correctly fails. Put free-text notes above the header or on a separate sheet.
  Tests sanitize only private copies of this known note; source fixtures stay
  intact and the validation rule remains strict.
- Existing keep-batch discovery derived suffixes from the whole parent path and
  inherited all flowcell projects on each batch. It now uses the flowcell name
  and the validator's per-batch plan.
- Descriptor inference stripped identity whitespace and truncated multi-project
  assignments after validation. Identity fields now bypass that conversion.
- FASTQ name regexes treated sample IDs as regex patterns. Exact escaping now
  prevents punctuation in an accepted ID from matching another sample.
- The descriptor helper configured logger state and could fetch/write an
  organism cache at import if package data was missing. Import is now passive;
  an actual organism lookup reports a missing packaged database explicitly.
