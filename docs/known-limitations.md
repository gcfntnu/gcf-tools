# Known limitations and evidence gaps

These are source-verified observations at
`059d7d94b818be79dca53a48bdf9d4b905d02ea2`, not behavior to enshrine. Do not silently
fix them in packaging, documentation or fixture refactoring. Schedule a bounded
correction with input/output evidence and affected consumers; the
[foundation tracker](https://github.com/gcfntnu/gcf-tools/issues/66) records
sequencing and ownership. [Verification](verification-60.md) distinguishes
executed probes from source inspection.

## Configmaker and descriptors

| Finding | Concrete evidence and consequence | Follow-up |
| --- | --- | --- |
| Project prefix truncation | `configmaker.py:is_valid_gcf_id` matches `GCF-\d{4}-\d{3}` without an end anchor: `GCF-2026-1000` → `GCF-2026-100`. Descriptor `gcf_number` conversion has the same prefix regex. CLI selection/paths can change; protected merge identity fields do not repair the CLI parser | Dedicated correctness issue; bring forward if four-digit project IDs are imminent |
| Scalar/list project override | `create_default_config` uses a list normally, a scalar with `--new-project-id`; default experiment title inherits this type | Existing [#41](https://github.com/gcfntnu/gcf-tools/issues/41); preserve its owner/scope |
| Directory-order project choice | `_match_project_dir` logs multiple automatic matches but returns the last; with several explicit IDs it returns the first matching directory per run. `os.listdir` order is not a selection policy | Explicit selection/acceptance decision; fixtures should avoid ambiguity |
| Independently matched mates | `match_fastq` sorts R1/R2 independently, without matching lanes or counts. A sample can initialize with unmatched mates; per-sample-directory prefix glob is also broader than flat-file matching | Add coverage under #62 as scoped, then separate acceptance/correction work |
| PEP derivation narrower than discovery | `peppy_utils.py:peppy_project_dict` derives renamed flat paths for non-single-cell data even when discovery accepted flat lane-style filenames. Batch IDs and single-cell layouts also need dedicated path coverage | Default fixture uses renamed flat files; future lane/batch profiles must assert resolved paths |
| Launcher ignores output/PEP choices | `SNAKEFILE_TEMPLATE` always loads `config.yaml` and `pep/pep_config.yaml`; `main` neither changes those names for `--output` nor sets workflow `skip_peppy` for `--skip-peppy` | CLI success alone cannot establish downstream usability; dedicated launcher compatibility task |
| Late failures and overwrites | `main` calls `create_fastq_dir` before geometry/kit checks; `create_fastq_dir` recursively replaces the existing link root. Later errors can leave links, snapshots, Snakefile, YAML or PEP partly updated | Separate transactional/output decision, using private output directories meanwhile |
| Incomplete checksum mapping | `find_fastq_md5sums` keys by basename (collisions across runs overwrite); `create_default_config` joins lookup results directly. A missing checksum returns `None`, causing an uncaught `TypeError` after link creation when another checksum file exists | Dedicated checksum failure/identity coverage and behavior decision |
| Lossy annotations | `_infer_dtype_string` strips punctuation; `_tryhard_numeric` turns `10-20` into 15 and removes limit/unit information from e.g. `<5`. Later coercion/stringification changes types and missing values | Explicit normalization/migration decision; protected IDs do not imply all annotation text is lossless |
| Organism assignment depends on pandas indexing | `infer_by_descriptor` assigns `col[i]` with integer positions while sample index labels are strings. Under pandas 3.0.6 the probe retains `Human` at sample `001` instead of the canonical match | Capture deployed dependency behavior before upgrade/correction; no matcher replacement under #60 |
| Categorical enum conversion can raise | `_infer_dtype_categorical` asserts membership but never assigns `out` on the valid `subtype='enum', enum=[...]` branch; `Sample_Type` default uses this branch. Valid `DNA` can raise `UnboundLocalError` before links are made | Newly confirmed defect; focused regression/correction needed, not a new restriction on valid sample types |
| Nested duplicate YAML keys | `LibprepConfig._parse` rejects duplicate top-level kit names, but nested duplicate parameter names are accepted by `safe_load` with last value winning | Do not describe selection validation as complete workflow-parameter validation; define stricter acceptance separately |

## Fixed workflow comparator gaps

At [gcf-workflows `42d37e3`](https://github.com/gcfntnu/gcf-workflows/tree/42d37e302a2ff6c868844e6d33147460e0ec7ba3):

- [`utils.py`](https://github.com/gcfntnu/gcf-workflows/blob/42d37e302a2ff6c868844e6d33147460e0ec7ba3/utils.py)
  reselects `libprepkit + ' SE/PE'` case-sensitively. gcf-tools accepts normalized
  case/outer whitespace and unsuffixed entries. Not every successfully selected
  tools kit is therefore demonstrated runnable downstream.
- [`schemas/config.yaml`](https://github.com/gcfntnu/gcf-workflows/blob/42d37e302a2ff6c868844e6d33147460e0ec7ba3/schemas/config.yaml)
  describes `samples` as a string, while `utils.py:get_raw_fastq` consumes a
  mapping. Do not treat that schema as the authoritative generated format.

These are source comparisons, not an executed workflow/DAG test. Coordinate
reconciliation when the colleague's workflow work settles, comparing the same
tools candidate and inputs against this fixed revision and their explicit SHA.
No workflow changes belong in this PR.

## Testdata producer

Installed help works; production execution is not endorsed. Source
`testdata/create_testdata.py:BFQoutput._inspect`, `sample`, `sample_samplesheet`
shows why [#63](https://github.com/gcfntnu/gcf-tools/issues/63) must establish an
offline harness before [#64](https://github.com/gcfntnu/gcf-tools/issues/64) restores
safe generation:

- Inspection can run `wget` on moving workflow `main`, write `.libprep.config` in
  cwd, then reference `yaml` without importing it. Ordinary construction is not
  a read-only/offline inspection API.
- It infers project identity from `ExperimentName`, expects a project sample TSV,
  and copies obsolete `bcl.done` plus Stats/InterOp/workbook content. Current BFQ
  state is not represented by that marker.
- Sampling defaults to recursively deleting an existing destination. No overlap
  guard protects source/ancestor destinations. Commands use shell interpolation
  and some exit statuses are ignored.
- Sample selection uses unseeded `random.choices` (with replacement). Each file
  uses `seqkit sample -s 123456`, which by itself does not prove paired-read
  identity. Prefix globbing, filename-based R1/R2 inference and renaming multiple
  files to the same destination create identity/overwrite risks.
- The SampleSheet subsetter splits literal commas and only recognizes `[Data]`;
  it does not reuse the current quoted CSV / `[BCLConvert_Data]` parser.

The older `.tests/configmaker` data exercise input interpretation; they are not
validated output of a safe producer. The assessment found two malformed FASTQs,
so fixture presence must not be treated as content validation. The new #62
synthetic paired fixture must be independent of the producer being repaired.
The historical RNA workbook's note at customer J48 is deliberately invalid under
current rules; `tests/prepare_cli_fixtures.py` and the legacy CLI fixture repair
only private copies. Do not weaken the validator or edit the source workbook.

## Missing evidence and later work

No unresolved facility decision blocks these documentation changes. Before
behavior/dependency changes or foundation completion, obtain:

- Installed Python/dependency versions, source/image IDs and local workflow/kit
  edits; the hosted verification environment is not the production environment.
- Active standalone/custom Python callers, descriptor usage, legacy `.xls` and
  Python requirements, and priority real FASTQ layouts. The parser supports
  workbook reading, but this PR did not verify legacy `.xls` operation.
- Reusable paired/default-PEP/path/checksum profiles (#62), offline producer
  evidence (#63/#64), and independent developer onboarding (#65).
- Deliberate facility suite/container integration with copied inputs and manual
  output/scientific review; no real services, mail, or deployment ran under #60.

BFQ baseline README's claim of import-time `.configmaker.debug` logging is stale;
current imports are passive and `.configmaker.log` is written on successful
discovery summary. Its historical libprep deployment notes also predate the
current validator requirement. Use the present source/contracts here; BFQ
[PR #141](https://github.com/gcfntnu/gcf-bfq/pull/141) is the related, unmerged
guidance update, not a dependency of this documentation PR.
