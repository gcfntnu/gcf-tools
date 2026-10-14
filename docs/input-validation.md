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
)
print(result.render_text())
report = result.to_dict()       # ordinary JSON-serializable dictionary
print(json.dumps(report, indent=2))
if not result.ok:
    raise SystemExit(2)
```

Each input argument accepts a path or iterable of paths. Input/read/parse errors
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
`workbook.missing_worksheet`. Successful informational results include
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
