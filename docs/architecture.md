# Architecture and interface ownership

This map was checked against gcf-tools
`059d7d94b818be79dca53a48bdf9d4b905d02ea2`, the starting `bfq-dev` for #60.
Consumer references use [BFQ `e1042837`](https://github.com/gcfntnu/gcf-bfq/tree/e1042837a2cb5270ffa49fcf03675287569914c1)
and [gcf-workflows `42d37e3`](https://github.com/gcfntnu/gcf-workflows/tree/42d37e302a2ff6c868844e6d33147460e0ec7ba3).
These identify inspected source, not the installed facility environment. Do not
substitute current workflow `main` for that comparator without recording a new SHA.

## Components

| Component | Responsibility and next source to read |
| --- | --- |
| `configmaker/configmaker.py` | CLI parsing, project/FASTQ discovery, metadata orchestration, links, config/Snakefile/PEP initialization and discovery summaries; start with `main()` |
| `configmaker/validation.py`, `columns.py` | Metadata-only validation, exact identifiers, worksheet joins and structured findings; [input contract](input-validation.md) |
| `configmaker/libprep.py` | Immutable source bytes, kit/read-layout selection and Stats.json geometry; [libprep contract](libprep-config.md) |
| `descriptors/` | Header descriptors, defaults, metadata conversion and fuzzy organism/reference matching; packaged `default_descriptors.yaml` and `ens_org.pkl` influence generated values |
| `peppy_support/peppy_utils.py` | Translates config into PEP 2.0.0 YAML, sample and optional subsample CSVs; it writes PEP without requiring the `peppy` package |
| `testdata/create_testdata.py` | Historical BFQ-output subset producer, separately installed; [not yet restored](known-limitations.md#testdata-producer) |
| `tests/`, `.tests/configmaker/` | API/subprocess tests and older fixture inputs; not interchangeable with the testdata producer or proof of valid paired read content |

Standalone flow is: enforce the expected validator version, resolve local
project/metadata paths, validate metadata, discover FASTQs, merge/convert descriptors,
rebuild links, read optional checksums, assemble defaults and geometry, select
the local libprep snapshot, write the Snakefile/config, export PEP, then write
discovery summaries. Early validation is read-only; the later sequence is not transactional.
See [failure boundaries](compatibility.md#failure-and-mutation-boundaries).

BFQ owns instrument discovery, persistent manager state, demultiplexing,
orchestration, snapshots, reporting and delivery. It imports shared validation
and kit selection rather than maintaining independent parsing rules. It copies
workflow working-tree files into the analysis directory, materializes captured
libprep bytes there, and invokes configmaker with explicit agreement checks.
gcf-tools does not require BFQ to perform those operations for standalone use.

The generated Snakefile hands configuration to gcf-workflows. That repository
owns scientific rules, reference resources, containers and downstream parameter
interpretation. A generated config does not prove that the selected workflow can
execute; a small test kit stub intentionally has no scientific rules.

## Public interfaces versus implementation details

Preserve installed command names/options and these existing import surfaces.
"Exported" does not mean every internal dataframe layout is a versioned schema.

| Interface | Consumer/contract |
| --- | --- |
| `configmaker.configmaker.SEQUENCERS` | BFQ `afterFastq.py` imports instrument-code → model-name mapping |
| `configmaker.validation.validate_inputs`, `VALIDATOR_VERSION`, `VALIDATION_API_VERSION` | BFQ `preflight.py`/`misc.py` call validation and consume `ok`, `render_text()`, `to_dict()`; `afterFastq.py` passes `VALIDATOR_VERSION` to the subprocess. API/report schema is 1. The API constant is public; not every constant is directly imported by BFQ |
| `configmaker.libprep.LibprepConfig`, `LibprepSelection`, `LibprepConfigError`, `find_read_geometry` | BFQ `workflow_config.py` uses loading/selection/diagnostics/materialization; `config.py` has type-only snapshot/selection imports. Preserve fields and methods described in [libprep-config.md](libprep-config.md) |
| `configmaker.configmaker.add_workflow(...)` | Existing portable Python configuration API, including `src_dir` and keyword snapshot/assertion arguments |
| Compatibility parsing helpers in `configmaker.configmaker` | `get_data_from_samplesheet`, `get_project_samples_from_samplesheet`, `read_customer_sheet`, `read_lab_sheet`, `read_demux_sheet`, `sample_submission_form_parser` delegate to validated parsing. Keep legacy imports callable; their pandas/descriptor objects are not the validator JSON contract |
| `descriptors` package exports | `fuzzmatch_organism`, `fuzzmatch_reference`, `findall_header_descriptors`, `add_default_descriptors`, `order_columns_by_descriptors`, `infer_by_descriptor`; defaults and packaged organism data must remain available |
| `peppy_support` package exports | Reexports `peppy_utils`, notably `create_peppy`, `config_info`, `conifg2sampletable` (existing spelling), `config2subsampletable`, `config2experimentinfo`, `peppy_project_dict`; inspect existing callers before changing names/values |

`ValidationResult.samples`, `metadata`, parsed sheets/forms, descriptor dictionaries
and parser mechanics are shared in-process implementation structures. External
report consumers should use `to_dict()` rather than depend on pandas dtypes or
private column mapper names. Preserve behavior while refactoring; do not infer a
public guarantee for every importable helper (for example unused `uniq_list` or
`check_organism_and_reference_db`). External custom callers remain a facility
inventory gap.

## BFQ subprocess and file boundary

BFQ source filenames in this guide are relative to
[`bcl2fastq_pipeline/bcl2fastq_pipeline/`](https://github.com/gcfntnu/gcf-bfq/tree/e1042837a2cb5270ffa49fcf03675287569914c1/bcl2fastq_pipeline/bcl2fastq_pipeline)
at the fixed baseline.

At the fixed BFQ revision, `afterFastq.py` launches `/opt/conda/bin/configmaker.py`
with a flowcell output path, `-p`, `--libkit`, `--machine`,
`--expected-validation-version`, `--libprep-config`, `--libprep-sha256`,
`--libprep-entry`, `--expected-read-geometry`, and conditionally
`--skip-create-fastq-dir`. Its cwd is the analysis workdir. `/opt` is a BFQ
deployment convention, not a gcf-tools library requirement.

BFQ copies `configmaker.analysis-summary.json` to
`configmaker-analysis-<project>.json`. `analysis_qc.py` checks schema 1,
`kind: fastq_discovery`, a nonnegative integer `sample_count` and a list of
string `missing_sample_ids`. Missing/invalid reports mean unavailable evidence,
not zero samples. Planned validation counts and observed FASTQ counts remain
separate. Version agreement requires compatible installations in both interpreters.

## Workflow consumers at the fixed revision

There are no direct gcf-tools package imports in the inspected workflow Python
or Snakemake files. The main boundaries are generated files and values:

- The Snakefile loads `config.yaml` and `pep/pep_config.yaml`, then includes
  `src/gcf-workflows/<workflow>/<workflow>.smk`.
- `utils.py:get_raw_fastq` reads the `samples` mapping and splits comma-separated
  `R1`/`R2` strings before joining them to the FASTQ root. YAML lists are not an
  interchangeable representation. `read_geometry` is a list of integer lengths;
  rules use its length for SE/PE and its values in calculations.
- `common.smk:sample_info` chooses PEP unless config `skip_peppy` is true.
  `scripts/create_sampleinfo.py` reads `pep_config.yaml` or `config.yaml`, maps
  PEP `sample_name` back to `Sample_ID` and emits the sample TSV consumed by BFQ.
- RNA-seq consumers interpret `read_orientation` values `unstranded`, `forward`
  and `reverse`. Workflow utilities fill defaults from `main.config`, optional
  `GCF_SECRET`, libprep and `docker.config`, retaining existing project values.
  That is downstream behavior; the secret file is not required by local tools tests.

Known differences between the generator and these consumers, including kit
reselection and launcher paths, are [explicit limitations](known-limitations.md).
The workflow schema file alone is not sufficient evidence of the consumed format.
