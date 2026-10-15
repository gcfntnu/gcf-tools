# Compatibility boundary

This document inventories behavior at the [#60 source baseline](verification-60.md).
Preserve intended CLI/API, file and value interfaces in bounded changes. A change
to normalization, defaults, selection, accepted input or failure side effects is
a behavior change even if formats stay identical. [Known defects](known-limitations.md)
are candidates for explicit correction, not permanent requirements.

The authoritative detailed contracts remain [input-validation.md](input-validation.md)
and [libprep-config.md](libprep-config.md). This page connects them to entry points,
generated files and consumers rather than duplicating their schemas/rules.

## Commands and options

`setup.py` installs `configmaker.py` and `create_testdata.py`. Equivalent module
invocations are `python -m configmaker.configmaker` and
`python -m testdata.create_testdata`. `-h`/`--help` is available on both; neither
parser declares a `--version` option. See [verification](verification-60.md) for
executed help checks. An option inventory is not a claim that every branch of
each option is end-to-end covered.

### configmaker.py

Source: `configmaker/configmaker.py:parse_args`, `check_input`, `main`.

| Argument | Current default and meaning |
| --- | --- |
| `runfolders` | One or more existing flowcell directories; paths are made absolute |
| `-p`, `--project-id` | One or more project IDs; omitted means directory discovery. Explicit selection avoids the ambiguity defect below |
| `-P`, `--new-project-id` | No override; otherwise changes generated identity and retains source project identity |
| `-s`, `--sample-sheet` | Discover `SampleSheet.csv` in selected runs; explicit single file replaces that list |
| `-S`, `--sample-submission-form` | Discover `Sample-Submission-Form.xlsx`; explicit single file replaces that list |
| `-o`, `--output` | `config.yaml`; changes YAML destination, not the project working directory |
| `--subsample` | Unset → `filter.subsample_fastq: skip`; positive fraction below 1 stays float, exactly 1 means skip, above 1 is converted to integer. It configures later processing, not local FASTQ sampling |
| `--organism` | Unset; a truthy CLI value wins over SampleSheet `Organism`. See normalization limits below |
| `--libkit` | Unset; overrides SampleSheet `Libprep` when supplied |
| `--libprep-config` | `src/gcf-workflows/libprep.config` relative to cwd; explicit file supplies effective bytes |
| `--libprep-sha256`, `--libprep-entry`, `--expected-read-geometry` | Unset; exact hash/entry/one-or-more integer length assertions, not selection overrides |
| `--machine` | Infer from the instrument field (second underscore-delimited flowcell-name component) and `SEQUENCERS`; unknown code yields an empty string, differing models fail |
| `--PI` | String `NA`; writes existing key `experiment_principal_inverstigator` (spelling retained) |
| `--contributor` | Unset; omitted from config unless supplied |
| `--title` | Unset; defaults to the generated `project_id` value, including its scalar/list type |
| `--summary` | String `NA` |
| `--skip-create-fastq-dir` | False; if true skips link creation and omits `fastq_dir` from the default config |
| `--skip-peppy` | False; if true omits PEP export. Does not currently create a runnable alternative launcher; see defects |
| `--keep-batch` | False; otherwise samples gain `_<Flowcell_ID>` and separate per-batch metadata/projects |
| `--verbose` | False; enables debug console logging |
| `--test` | False; fabricates discovery records without FASTQs. Still needs metadata/geometry/kit inputs and can create outputs/clone workflows; not a general safe dry run |
| `--expected-validation-version` | Unset; exact installed validator version check before input/output work |

Error messages mention obsolete `--samplesheet`/`--submission-form` spellings in
one path; actual supported flags are the spellings above. Do not copy those error
message suggestions into automation.

### create_testdata.py

The existing installed script, module and `BFQoutput` names remain. The bounded
[#64 producer](testdata.md#safe-flat-paired-producer-64) requires positional
`runfolder`, `--output`, explicit `--project-id`/`--samples`, local
`--libprep-config` and the existing `--no-fastq-rename` route. `--seed` is additive
(default 123456). `--n-reads` remains CLI 1000 / Python 10000, interpreted per mate
file in one flat pair. `--n-samples` remains recognizable but automatic selection
is refused. No source downloads or native sampling/compression commands remain.

`BFQoutput(dirname=None, libprep_config=None, project_id=None)` adds project
selection. Its `sample` argument order remains compatible, with additive trailing
`seed`; `overwrite` now defaults false and even explicit true refuses an occupied
destination. Flat names are preserved; historical rename/multi-file routes fail.
Project/sample selection comes from shared metadata validation, not ExperimentName
or generated TSV. Shared geometry-based libprep selection deliberately replaces
legacy SE-first lookup. Every supported pair is validated and sampled together,
then published without replacement; original workbook/Stats bytes retain their
stated provenance. See the guide for exact source, identifier and filesystem
restrictions and the auxiliary manifest; these do not change configmaker formats.

The additive [#83 Parse profile](testdata.md#parse-wt-v4-selected-cell-producer-83)
uses `--parse-cells` or `BFQoutput.sample_parse_cells(output_dir, selection, overwrite=False)`
to retain all explicit WT v4 cell-key matches. It conflicts with explicit read-count,
sample-selection and seed arguments; ordinary reservoir defaults remain unchanged.
Both profiles now preserve optional `RunInfo.xml` bytes/hash, while Stats remains
the geometry authority. The selection schema is auxiliary; configmaker formats
and shared validation rules are unchanged.

## Metadata, selection and configuration authority

- [Input validation](input-validation.md#accepted-input-and-matching-rules) defines
  accepted CSV sections/workbook sheets, exact string IDs (including leading
  zeroes and whitespace), customer/lab inner joins, later-form overrides,
  SampleSheet project authority, custom descriptors and batch scoping. Its
  [API/report](input-validation.md#public-api-version-1) owns schema 1 and finding
  codes. Consumers branch on codes rather than diagnostic wording.
- `check_input` discovers one selected project directory per retained run.
  Supplying several `-p` IDs does not guarantee all matching directories in one
  run are processed. Current first/last directory selection is a known limitation;
  use unambiguous inputs and inspect observed sample counts.
- SampleSheet custom options are merged in input order; later values win with
  `samplesheet.option_override` warnings. `--libkit` and truthy `--organism`
  then override their respective custom options. Metadata preflight requires
  the Parse `Cell Multiplexing` sheet when either SampleSheet `Libprep` or the
  explicit CLI kit override selects Parse. The original SampleSheet requirement
  remains even when overriding away from Parse. The additive validator `libkit`
  keyword carries this selection without mutating SampleSheet custom options.
  Parse selected only by CLI now also emits validated `wells`. See the
  [ASCII/override contract](input-validation.md#ascii-diagnostics-and-kit-overrides).
- `Sample_ID`, `Project_ID` and `Src_Project_ID` bypass descriptor string
  sanitization during configmaker merge. SampleSheet projects replace submission
  projects in generated samples. Other metadata still goes through descriptors.
- Geometry comes from `Stats/Stats.json` in every selected run. Within
  `ReadInfosForLanes[*].ReadInfos`, `IsIndexedRead` must be a boolean and non-index
  `NumCycles` values must be one or two positive integers, consistent across lanes
  and runs. `Number` does not reorder that list. This is geometry validation, not
  a FASTQ content/read-length check. [Libprep policy](libprep-config.md#kit-and-read-geometry-policy)
  defines matching, layout checks and explicit errors.
- Standalone callers choose the local or explicit libprep source; the library has
  no mandatory `/opt`. BFQ uses the fixed authoritative source described in the
  libprep guide and passes
  captured bytes/hash/entry/geometry across the subprocess boundary. Nested kit
  defaults fill missing project settings; explicit project values win. Effective
  bytes are materialized in the analysis workflow tree even for an external
  source. The [libprep contract](libprep-config.md) owns immutable snapshot semantics.

## Discovery and filesystem conventions

Under each selected `<run>/<project>`, `match_fastq` accepts these current forms
for exact sample ID `S` (substitute `R2` or `I1` for `R1`):

| Form | Example pattern |
| --- | --- |
| Renamed flat files | `S_R1.fastq.gz` |
| Flat sample-number files | `S_S<number>_R1_001.fastq.gz` |
| Flat sample/lane files | `S_S<number>_L<3 digits>_R1_001.fastq.gz` |
| Per-sample directory | `S/S*_R1_001.fastq.gz` (existing prefix glob inside the exact directory) |

R1/R2/I1 matches are sorted independently; no content or mate/lane consistency
validation occurs. Discovery acceptance is broader than reliable PEP derivation.
The most straightforward tested default-PEP shape is renamed flat files.
Flowcell ID is the final underscore-delimited run-name component. Ordinary
multi-flowcell samples merge file lists; `--keep-batch` appends that ID to sample
identity and retains `Src_Sample_ID` in real batch discovery.

| Artifact | Placement and current representation |
| --- | --- |
| FASTQ links | `cwd/data/raw/fastq/<run>/<project>/...`; relative source layout retained, targets are source FASTQs. Existing FASTQ root is recursively replaced by default |
| YAML | `--output` or `cwd/config.yaml`; parent must already exist |
| `Snakefile` | Always cwd; references literal `config.yaml`, `pep/pep_config.yaml`, selected workflow include |
| Workflow tree | `cwd/src/gcf-workflows`; absent tree causes an unpinned Git clone. Tests must pre-stage it; API `add_workflow(src_dir=...)` is separate from CLI options |
| PEP | `cwd/pep/pep_config.yaml`, `sample_table.csv`, optionally `subsample_table.csv`; skipped only by `--skip-peppy` |
| Discovery summaries | `configmaker.analysis-summary.json` and `.configmaker.log` beside output YAML; schema/content authority is [input-validation.md](input-validation.md#standalone-configmaker) |
| Optional input checksums | `<run>/md5sum_<project>_fastq.txt`; whitespace-separated checksum/filename records, looked up by basename |

Run from a dedicated project cwd and normally retain the default output filename.
An absolute `--output` path does not relocate the other artifacts. Configmaker
does not calculate or verify input checksums: it copies supplied values into
generated metadata. If no checksum manifests exist, it warns and omits values;
if some exist, missing manifests are silently skipped. Incomplete or
colliding basename mappings have [known failure/ambiguity risks](known-limitations.md).

## Generated values, normalization and PEP

Source: `create_default_config`, `merge_samples_with_submission_form`,
`descriptors/descriptors.py`, `peppy_support/peppy_utils.py`. The YAML has no
independently versioned complete schema; consumers and explicit fixture values
must be reviewed together.

| Value | Current type/meaning to preserve or explicitly review |
| --- | --- |
| `project_id` | Usually list of strings; `--new-project-id` produces a scalar string plus list `src_project_id` (inconsistency tracked in #41) |
| `samples` | Mapping keyed by exact analysis sample ID; per-sample scalar values are stringified, iterable non-string values become lists of strings |
| `R1`, `R2`, optional `I1` | Per-sample comma-separated relative-path strings; empty mates may be empty strings. Workflow consumers split these strings |
| `Project_ID`, `Flowcell_Name`, `Flowcell_ID` | Per-sample strings, comma-separated for merged contributions; repetition can follow R1 file count |
| `R1_md5sum`, `R2_md5sum`, `I1_md5sum` | Optional comma-separated checksum strings, preserving corresponding file ordering |
| `read_geometry` | List of one/two integer lengths |
| `multiple_flowcells` | Boolean inferred from merged Flowcell_ID strings; forced false with `--keep-batch` |
| `quant.batch` | Normally `{method: skip}`; batch mode uses `{name: Flowcell_ID}` |
| `filter.subsample_fastq` | String `skip`, float fraction, or integer count; other nested kit defaults remain present |
| `libprep_selection` | Diagnostics: source/hash/kit/entry/geometry/workflow, as defined in the libprep guide |
| `organism` | Global value from CLI/custom options when present; a nonempty value is not necessarily canonicalized. Descriptor organism conversion is a separate, dependency-sensitive path |
| Missing metadata | Stringification can emit strings such as `<NA>` or `nan`, not necessarily YAML null; descriptor category handling may use empty strings |
| `descriptors` | Metadata for emitted columns; explicit descriptor keys override defaults, with inferred subtype/range/category information added |

Default descriptors load from packaged YAML. Header bracket values are strings
until interpreted; defaults include typed numbers/booleans. Do not replace those
representations indiscriminately. Numeric descriptor inference accepts decimal
commas, downcasts integers, converts ranges to means and strips limit/unit text
in its best-effort path; unsuccessful numerical conversions may become missing
values. Ordinary string conversion strips outer whitespace/punctuation and
transliterates Norwegian letters. `no_conversion` still strips whitespace, but
configmaker's protected identity columns bypass it altogether. Nucleotide
descriptors uppercase values; categorical inference can affect reference levels.
These potentially lossy conversions require dedicated decisions before changes.

Organism matching uses packaged `ens_org.pkl`, with default fuzzy score 80 and
alias minimum length 4; `fuzzmatch_reference` defaults to score 80 against known
control/reference terms. Imports do not fetch a replacement database. A real
lookup with missing packaged data fails explicitly. Do not call the explicit
network refresh helper in routine checks or replace the matching engine as
incidental cleanup.

PEP output declares `pep_version: 2.0.0`, uses CSV column `sample_name`, replaces
read paths in the sample table with `R1`/`R2`/`I1` derivation tokens, and derives
paths relative to the FASTQ root. Multiple input files cause a subsample table
with `subsample_name`; selected project/run fields move there when varying.
Experiment/library fields and descriptors are copied to PEP YAML. The current
templates assume renamed flat files or a particular single-cell directory shape;
do not infer that every discoverable FASTQ layout resolves through PEP correctly.

## Deliberate input tightening (#71)

Sample IDs in sequencing, customer, lab and required multiplexing tables, plus
multiplexing Wells values, must be ASCII. Invalid original cells fail with stable
`sample.non_ascii_id` / `workbook.non_ascii_wells` errors before merge/conversion
or initialization. Descriptive Unicode metadata retains its existing treatment.
Valid ASCII identities (including leading zeros), well syntax, joins, precedence,
lanes and batch behavior remain unchanged. Report/API schema stays at version 1.

## Failure and mutation boundaries

- CLI argument errors, expected-validator mismatch and failed metadata validation
  exit nonzero (normally 2) before initialization. Invalid metadata preserves an
  existing config and leaves a new output directory absent. Imports of the
  validator/configmaker do not install log handlers or create diagnostic files.
- No discovered FASTQs fails before initialization. Partial discovery succeeds
  for available samples with missing IDs reported; planned metadata counts are
  not observed FASTQ counts. CLI success does not validate FASTQ structure.
- After metadata/discovery, links are rebuilt **before** checksum, geometry, kit
  and later output work completes. A libprep assertion fails before Snakefile
  generation but may already have replaced links. Some later Python errors are
  uncaught and may produce tracebacks rather than controlled exit 2.
- Snakefile/config/PEP/summary writes are sequential and non-atomic. Existing
  files may be overwritten and an old optional PEP file can remain when a new
  run no longer emits it. Do not use an occupied project directory for tests.

Failures and overwrite behavior are observable compatibility concerns. The early
validation protections are intentional; incomplete rollback and inconsistent
launchers are defects to fix under separately scoped, tested changes.


## Multiplexed metadata tightening (#68)

[The pooled-library contract](input-validation.md#pooled-library-metadata-parse)
rejects populated biological-only fields before any Parse config/output work,
including lab cells and values otherwise hidden by merges. It also retains the
five historically dropped library metadata columns for Parse only. Header
mapping, descriptor conversion, exact IDs, customer/lab precedence, FASTQ grouping,
PEP identities and the `samples`/`wells` sections retain their established meaning.
No TSV materialization or workflow processing is implemented in tools.
