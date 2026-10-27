# gcf-tools

gcf-tools interprets sequencing metadata and prepares project configuration for
the NTNU Genomics Core Facility workflows. `configmaker.py` can be used on its
own with local demultiplexed FASTQs, a SampleSheet and submission workbook. It
does **not** require BFQ, a web application, instrument access or a database.
BFQ also imports the shared metadata validator and library-preparation selector,
then runs configmaker to initialize analyses. gcf-tools does not demultiplex or
execute the scientific workflows itself.

## Start here

| Need | Authoritative guide |
| --- | --- |
| Prepare an isolated environment; run available checks | [Contributing](CONTRIBUTING.md) |
| Rehearse a complete task from a fresh checkout | [Onboarding walkthrough](docs/onboarding.md) |
| Understand components, callers and public imports | [Architecture](docs/architecture.md) |
| Find CLI options, generated values, paths and compatibility boundaries | [Compatibility](docs/compatibility.md) |
| Interpret SampleSheets, workbooks, IDs and validation reports | [Input validation](docs/input-validation.md) |
| Select library kits, read geometry and configuration snapshots | [Library-preparation configuration](docs/libprep-config.md) |
| See commands actually exercised, source revisions and limits | [Onboarding verification](docs/verification-65.md), [packaging evidence](docs/verification-61.md) |
| Run the synthetic paired example and inspect its limits | [Testdata guide](docs/testdata.md) |
| Find defects and missing evidence before changing behavior | [Known limitations](docs/known-limitations.md) |
| Start an agent task | [AGENTS.md](AGENTS.md), then the issue and contributor guide |

## Development quick start

From a fresh Linux checkout with Python 3.11 and venv support:

```bash
python3.11 scripts/dev.py setup
python3.11 scripts/dev.py check all
```

Setup acquires the exact development dependencies once. Checks then run offline,
including editable installation, fresh-wheel validation and source-distribution
testing. Mutable state stays in the sibling `<checkout-name>-local/` directory.
See the [development guide](docs/development.md) for fast/CLI tiers, package
boundaries, dependency overrides and evidence. Production requirements remain
separate from the development baseline.

## Entry points and use

The installed commands are **`configmaker.py`** and **`create_testdata.py`** (the
`.py` suffix is part of their names). Their module equivalents are
`python -m configmaker.configmaker` and `python -m testdata.create_testdata`.
There is no package-level `python -m configmaker` entry point. Both commands'
help and both module forms are exercised in the contributor checks.

For standalone initialization, work in a dedicated project directory. Supply
one or more flowcell directories with `SampleSheet.csv`,
`Sample-Submission-Form.xlsx`, `Stats/Stats.json` and a project FASTQ subdirectory;
select the project explicitly with `--project-id` when possible. Place a known
workflow tree at `src/gcf-workflows` in that working directory before running.
The [compatibility guide](docs/compatibility.md) explains input layouts and why
`--output` alone does not relocate a project. The
[existing CLI checks](CONTRIBUTING.md#available-checks) are the currently
repeatable, offline examples; their local workflow configuration stubs do not
execute scientific analysis.

`create_testdata.py` supports explicit flat paired-read sampling and selected-cell
Parse WT v4 gene-expression fixtures. It validates complete paired streams and
publishes only to a new destination. Follow the [supported profiles and executable
producer checks](docs/testdata.md#generate-and-verify-the-supported-profiles);
other layouts and scientific adequacy require separate evidence.

## Development status

Feature branches start from current `bfq-dev`; PRs target `bfq-dev`. Production
promotion is separate. Keep standalone behavior and BFQ/workflow interfaces
compatible, and describe observable changes even when correcting a defect.

[Foundation tracker #66](https://github.com/gcfntnu/gcf-tools/issues/66) aims to let
either developer start from a clean checkout, run a representative example and
submit a bounded change with an agent without an undocumented setup handover.
The contract, isolated packaging/checks, independent paired example and safe
producer profiles are implemented. The [onboarding walkthrough](docs/onboarding.md)
and [verification record](docs/verification-65.md) distinguish independent agent
rehearsals from facility-developer confirmation. The tracker remains open until
its agreed human acceptance is recorded. Routine local development needs no
facility setup or running service.

The [offline 10x index normalization contract](docs/tenx-indexes.md) covers versioned
GA/TT mappings, logical-library repeated rows and coordinated converter validation.
