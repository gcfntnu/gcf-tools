# Synthetic paired example and testdata boundaries

The committed `tests/fixtures/paired/` fixture is independent of the
`create_testdata.py` producer. Everything in this directory, including workbook
properties and identifiers, is invented for testing and may be distributed with
the source archive. No facility records, reads or infrastructure were copied.
The producer has a separate supported flat-paired profile described below.
The committed example remains independently generated; the separate Parse
selected-cell profile is documented below, with scientific integration remaining
an explicit operational gate.

## Run and inspect the example

After `python3.11 scripts/dev.py setup`, run this single offline command from the
checkout or unpacked source archive:

```bash
python3.11 scripts/dev.py check example
```

The command uses the prepared installed `configmaker.py`, normal PEP enabled,
from a fresh analysis working directory outside the checkout. The harness blocks
network and SMTP, including subprocesses. The printed artifact directory contains
`pytest-tmp/test_paired_example_installed_0/`, with:

- `input/`: a private copy of the synthetic inputs and local workflow stub;
- `analysis/`: config.yaml, Snakefile, PEP, discovery JSON/log, workflow copy and
  live FASTQ symlinks;
- `cli-transcript.txt`: stdout/stderr from the installed command.

The command inside the example is equivalent to the following, executed from
that private `analysis/` directory after staging `src/gcf-workflows`:

```bash
configmaker.py ../input/990101_SYNTHETIC_0001_ASYNTHETIC --project-id GCF-2099-001
```

Use the example harness to provision those paths; do not invoke configmaker in
an occupied analysis directory. It normally replaces FASTQ links and outputs.

## Fixture and independent expectations

The invented project `GCF-2099-001` has samples `001`, `001A`, and `CTRL`, each with
24 distinct pairs. Simple BFQ filenames are `<sample>_R1.fastq.gz` and
`<sample>_R2.fastq.gz`. Read lengths are 75 and 150 bases, matching the minimal
`Stats/Stats.json` geometry. No instrument metrics or InterOp files are fabricated.

| Sample | External ID | Group | Customer concentration | Lab concentration | Emitted concentration |
| --- | --- | --- | --- | --- | --- |
| `001` | `007` | control | 10 | 11 | string `11.0` |
| `001A` | `008` | treated | 20 | 22 | string `22.0` |
| `CTRL` | `009` | control | 30 | 33 | string `33.0` |

The concentration descriptor is numeric; configmaker converts to float and then
serializes sample values as strings. Lab values win under the existing workbook
contract. IDs remain strings, including leading zeros. Expected global values
include list-valued project/title, integer read geometry `[75, 150]`, workflow
`rnaseq`, library layout `paired`, kit `Synthetic`, and default subsampling `skip`.
These are explicit assertions, not golden output regenerated through configmaker.

The independent oracle reads complete four-line FASTQ records, checks sequence
and quality lengths, exact sample/mate/ordinal IDs, 24 pairs in order and distinct
sequences. Corruption checks demonstrate rejection of wrong mate identity,
missing records and truncated qualities. It recalculates MD5 from compressed
bytes and checks filename associations and propagation into config/PEP. Configmaker
itself only propagates supplied MD5 values; it does not validate FASTQ content.

The example verifies default PEP CSV tokens and expands the exported source
patterns using the CSV rows, checking the resulting paths against config paths
and live symlink targets. It does not run the peppy library or Snakemake. This
single-flowcell profile correctly has no subsample table. JSON summary schema,
planned/discovered identities and counts are asserted. Source bytes are checked
before and after initialization. Invalid-metadata checks cover the early no-write
boundary; empty discovery fails and partial discovery retains only available
samples, reporting the missing sample explicitly.

## Provenance and regeneration

`tests/paired_fixture.py` generates this fixture without importing configmaker or
the production testdata creator. It refuses an existing destination. It uses
SHAKE-256 of synthetic sample/ordinal/mate strings to construct varied bases,
fixed quality `I`, and IDs `synthetic:<sample>:<ordinal>/<mate>`. There is no random
sampling seed or source dataset. Gzip uses level 9, timestamp zero and no stored
filename. XLSX core dates and ZIP member times are fixed to 2000-01-01.

`provenance.json` records every input's SHA-256, including exact libprep and stub
bytes. The run's MD5 manifest maps all six compressed FASTQs. Regeneration is
compared byte-for-byte in the CLI checks under `requirements-dev.txt`; Python/zlib
or dependency changes require deliberate review of any compressed-byte changes.

To generate a separate candidate for inspection with the prepared interpreter:

```bash
python3.11 - <<'PY'
import json
from pathlib import Path
import subprocess
state = json.loads((Path.cwd().parent / (Path.cwd().name + '-local') / 'current.json').read_text())
subprocess.run([state['python'], 'tests/paired_fixture.py',
                str(Path.cwd().parent / (Path.cwd().name + '-local') / 'paired-regenerated')], check=True)
PY
```

The destination must be new. Inspect before replacing the reviewed fixture;
never update expected values simply to accommodate changed behavior. The local
stub lives at `workflow/libprep.config` and `workflow/rnaseq/rnaseq.smk`. It is
independently authored, not copied from a workflow revision. Its Snakefile raises
an explicit error if executed: it provides no scientific processing.

## Generate and verify the supported profiles

After setup, this command creates fresh tiny sources, runs the installed producer,
and consumes its output through installed configmaker with normal PEP enabled:

```bash
python3.11 scripts/dev.py check producer
```

| Profile | Synthetic input and expected output | Contract |
| --- | --- | --- |
| Flat paired reservoir | Three samples with 24 pairs each; select `001,CTRL`, retain 8 pairs each with seed 123456 | [Selection, pairing and publication](#safe-flat-paired-producer-64) |
| Parse WT v4 selected cells | Two libraries with 24 pairs each; retain 18 pairs each, representing two biological samples and explicit barcode aliases | [Selection schema and all-match retention](#parse-wt-v4-selected-cell-producer-83) |

These checks invoke the real installed commands. The paired source comes from the
independent fixture generator; the Parse source is separately constructed by
`tests/parse_fixture.py`. Both use invented metadata and sequences. They assert
retained identities/order/counts, original source bytes, complete MD5 propagation,
config values and PEP-derived paths that resolve to the produced files. Script
and module coverage also checks equivalent results. The copied workflow trees
are initialization-only stubs; no scientific workflow is executed.

To locate the retained producer outputs after a successful run, execute this from
the same checkout. It selects the latest successful `producer` check, not a
different worktree's output or a failed run:

```bash
python3.11 - <<'PY'
import json
from pathlib import Path
runs = Path.cwd().parent / (Path.cwd().name + '-local') / 'runs'
checks = [p for p in runs.glob('*/identity.json')
          if (r := json.loads(p.read_text())).get('profile') == 'producer'
          and r.get('result') == 'passed']
if not checks:
    raise SystemExit('Run python3.11 scripts/dev.py check producer first')
work = max(checks, key=lambda p: p.stat().st_mtime_ns).parent
print('Check evidence:', work)
for pattern in ('**/testdata.provenance.json', '**/analysis/config.yaml',
                '**/analysis/pep/sample_table.csv', '**/*transcript.txt'):
    for path in sorted((work / 'pytest-tmp').glob(pattern)):
        print(path.relative_to(work))
PY
```

The successful paired case is under `test_real_installed_producer_an*/` and the
Parse case under `test_parse_installed_workers_t*/`. Their `analysis/` directories
contain config, PEP and live FASTQ links. Alongside the paired output are producer
and configmaker transcripts. Parse has separate `script/` and `module/` outputs
with byte-identical manifests and FASTQs; its stdout/stderr are checked by the
test rather than retained as separate transcript files. The producer provenance
records source/output hashes, selection and counts; it is distinct from the
independent committed fixture's `provenance.json`. The check's `identity.json`,
`packages.txt`, `tests.log` and `tests.xml` identify the environment and assertions.

For a different source, adapt the command templates in the profile contracts
below, providing your own validated metadata, local configuration and new output
path. Those templates do not provision their placeholder paths. Keep real source
data and provenance private. The installed check above is the self-contained
generation and verification procedure for onboarding.

## Verification tiers and historical limits

`check fast` exercises shared API and isolation checks. `check example` runs the
single installed paired example; `check cli` additionally runs regeneration,
negative metadata, empty/partial discovery and oracle corruption checks alongside
the existing CLI tests. `check all` includes all of these tests in editable,
clean-wheel and unpacked-sdist environments. Existing CI runs `check all`; no
additional CI job or dependency is required. The fixture ships in sdist, not the
runtime wheel; wheel checks use a separate test bundle.

Later profiles should be added by need: lanes/chunks; repeated runs and
`--keep-batch`; multiple projects; SE; nested single-cell and index reads; source
directory layouts. Producer API tests already cover FASTQ file symlinks and
malformed/reordered pairs. The separate Parse profile covers its declared
biological/well relationships, not every Parse kit. This ordinary paired fixture
alone does not prove Parse support, real subsampling, scientific correctness or
deployed compatibility.

Historical `.tests/configmaker/` inputs exercise older initialization paths,
principally single-end and `--skip-peppy`; their filenames or successful CLI exit
do not establish valid paired contents or normal PEP path resolution. They are
Git-only inputs, excluded from source archives. The sdist's synthetic SE substitute
preserves specific legacy assertions, while the independently generated paired
fixture and supported producer checks provide the current content/PEP evidence.
Do not publish historical metadata as new examples or regenerate expected output
through the implementation being tested. See [distribution boundaries](development.md#distribution-boundary-and-source-testing).

Optional real-workflow comparison starts with immutable gcf-workflows revision
`42d37e302a2ff6c868844e6d33147460e0ec7ba3`. Pre-stage a private tree at that revision
and use its actual kit configuration; the synthetic kit is not a production kit.
Record the selected real kit, effective libprep hash and all intentional fixture
adaptations. Compare later candidates using that same fixture/environment and an
explicit candidate SHA, inspecting config, PEP paths, DAG inputs and relevant
outputs before deliberately updating the reference. Scientific/container and BFQ
server integration remain separate manual facility checks with isolated outputs
and email protection; none is implied by successful CLI initialization.

## Safe flat-paired producer (#64)

The producer accepts a **metadata-plus-FASTQ source** with one explicitly selected
project: `SampleSheet.csv`, `Sample-Submission-Form.xlsx`, `Stats/Stats.json` and
`<project>/<sample>_R1.fastq.gz` / `<sample>_R2.fastq.gz`. This may be a finalized
BFQ output or a privately assembled restored-FASTQ source. Its eligibility does
not assert manager completion: no generated project TSV, `bcl.done`, state JSON
or analysis output is required or copied. BFQ owns operational state initialization.

```bash
create_testdata.py /private/source/SYNTHETIC_RUN \
  --project-id GCF-2099-001 --samples 001,CTRL \
  --libprep-config /private/config/libprep.config \
  --n-reads 1000 --seed 123456 --no-fastq-rename \
  --output /private/fixtures/990101_SYNTHETIC_0001_ASYNTHETIC
```

The destination parent must already exist. Choose a valid flowcell-style basename
when the result will be consumed by configmaker/BFQ; the producer does not rename
runs or rewrite instrument identity. The installed script and
`python -m testdata.create_testdata` are equivalent. The Python surface remains
`BFQoutput(dirname=None, libprep_config=None, project_id=None)` and
`sample(output_dir, overwrite=False, n_reads=10000, n_samples=3, samples=None,
no_fastq_rename=False, seed=123456)`. CLI `--n-reads` still defaults to 1000.

### Explicit selection and configuration

Project, sample IDs, local libprep configuration and `--no-fastq-rename` are
required for this first profile. SampleSheet/workbook validation supplies project
and sample authority. IDs are exact strings: `001`, `1` and `001A` are distinct;
comma-separated CLI selection is not stripped or normalized. Duplicate/unknown
IDs fail. For unambiguous paths and the existing whitespace-separated MD5 format,
this producer profile rejects empty IDs, `.`/`..`, separators, commas, whitespace
and non-printable/non-ASCII characters in project/sample path components. This is
a producer restriction, not a new shared metadata rule.

The existing `--n-samples` option remains recognizable but automatic selection is
unsupported; explicit `--samples` takes precedence. The selected project must use
known flat R1/R2 FASTQ names without nested directories, lanes, chunks or index
reads. Extra unselected flat pairs are permitted. Preserve flat names with
`--no-fastq-rename`; historical renaming is refused because it can disagree with
normal PEP paths. No naming guess or multi-file merge is performed.

Local libprep bytes are loaded using the shared `LibprepConfig` selector and
paired geometry from `Stats/Stats.json`. This **deliberately replaces** historical
SE-before-PE selection and unknown-kit fallback: geometry chooses the applicable
entry, and unsupported/inconsistent kits fail. Missing local configuration never
causes a download. All scientific kit parameters remain owned by gcf-workflows.

### Paired selection and reproducibility

Python reads both complete gzip streams and validates **every** record, including
records not retained. Four-line records require a nonempty ASCII `@` header,
nonempty IUPAC DNA sequence, `+` separator, equal sequence/quality lengths and
printable Phred quality bytes. A populated separator must repeat its header.
Mates must have matching IDs and order, with equal record counts. Accepted IDs
use identical first tokens, `/1` and `/2` suffixes, or Illumina `1:N:...` /
`2:N:...` (also `Y`) comments. Any explicit label must agree with its mate file;
contradictory labels fail. Gzip truncation/checksum failures and empty pairs fail.
This is format/pair validation, not biological or sequencing-metric validation.

Algorithm `paired-reservoir-v1` uses a fresh `random.Random(seed)` per sample.
For zero-based pair index `i`, retain the first N pairs; thereafter draw
`randrange(i + 1)` and replace that reservoir slot when it is below N. Retained
pairs are emitted in original source order. The count remains **per mate file**
for this one-pair-per-sample layout. Fewer than N available pairs yields all
available pairs; zero or negative N fails. Explicit sample ordering does not
change the chosen records. Memory is bounded by the selected pairs, not source
FASTQ size; all source FASTQs are still scanned to EOF.

Output gzip uses compression level 9, `mtime=0`, no embedded filename and LF
record lines. Repeated generation from the same source/seed produces identical
gzip bytes in the recorded Python/zlib environment. Cross-version byte identity
is not promised. `testdata.provenance.json` records algorithm, versions, seed,
requested/available/selected counts, source compressed-file and metadata SHA-256,
libprep selection/hash and output FASTQ SHA-256. A complete fresh
`md5sum_<project>_fastq.txt` contains the actual emitted gzip checksums; source
checksum manifests are not copied.

### Source protection and publication

Every existing destination is refused, including files, directories and dangling
symlinks, even when an older Python caller passes `overwrite=True`. The destructive
overwrite option is retired. Source/destination ancestor, descendant and resolved
alias relationships fail before staging. Directory symlinks and nested project
layouts are not traversed. Readable FASTQ file symlinks are accepted, including
external targets, and outputs are self-contained regular files. Other metadata
file symlinks and duplicate selected FASTQ target identities are refused.

Input files, link targets, local configuration and source directories are checked
for identity changes before reading and before publication. Metadata snapshots are
checked against the shared validator's hashes; streamed compressed FASTQs are
hashed during reading. Observed source changes abort generation. This detects
ordinary concurrent modifications; it is not a filesystem snapshot against an
actively adversarial writer.

After successful input validation, an invocation-owned sibling directory receives
the outputs. Linux `renameat2(RENAME_NOREPLACE)` publishes the directory atomically.
Unsupported kernels/filesystems fail closed; a concurrently created destination
is never replaced, even if empty. Failures remove only this invocation's staging
directory and return a nonzero CLI diagnostic. The caller chooses a fresh path
for retries. No runtime shell, seqkit, gzip executable, network or SMTP is used.

### Metadata and source statistics

SampleSheet data rows are filtered by exact project/sample identity using CSV
parsing, retaining other sections, quoted values and `[BCLConvert_Data]` support.
The full workbook is preserved byte-for-byte; extra metadata rows remain valid
under the shared validator. Stats and optional InterOp files are copied unchanged.
Their counts describe the original run, **not** the reduced FASTQs; the auxiliary
provenance file states this explicitly. No instrument metrics are fabricated.

### Checks and remaining scope

```bash
python3.11 scripts/dev.py setup
python3.11 scripts/dev.py check fast
python3.11 scripts/dev.py check producer
python3.11 scripts/dev.py check all
```

The producer has no external executable dependencies. Setup needs only the pinned
Python baseline; the historical #63 seqkit/gzip acquisition and offline-guard
exceptions have been removed. `check producer` runs installed real generation,
normal configmaker/PEP consumption, subprocess failure cases and concurrent
invocations on wholly synthetic input. API tests add corruption, unchanged-source,
symlink, destination-alias, input-change, injected-write and publication races.
The six former #63 expected failures are replaced by passing regression coverage.
Wheel and unpacked-sdist checks exercise the same implementation offline.

The normal PEP test uses the committed initialization-only workflow stub, checks
exact sample IDs/counts/checksums and resolves PEP-derived links to generated
files. No scientific workflow, container, facility data or email is exercised.
The additive Parse cell-selection profile is documented below;
full lane/chunk/index/automatic-selection profiles remain unsupported. A small
format-valid random subset does not guarantee enough cells, genes or coverage for
a scientific workflow. Manual representative BFQ/workflow integration remains a
separate gate before treating a generated fixture as scientifically usable.

## Parse WT v4 selected-cell producer (#83)

`--parse-cells selection.json` adds a separate profile for **WT v4 gene expression,
Split-Pipe, R1=64/R2=58**, with flat paired filenames. It retains every read pair
whose native R2 barcode key occurs in the supplied selection. It does not call
cells, correct barcodes, infer wells, subsample selected cells, or run a workflow.
Other kits/chemistries, STARsolo execution, TCR, lanes and index reads are outside
this profile. Ordinary paired reservoir sampling keeps its existing defaults.

```bash
create_testdata.py /private/source/990101_SYNTHETIC_0001_ASYNTHETIC \
  --project-id GCF-2099-001 --libprep-config /private/config/libprep.config \
  --parse-cells /private/selections/selection.json \
  --output /private/fixtures/990101_SYNTHETIC_0001_ASYNTHETIC
```

The Python equivalent is `BFQoutput(...).sample_parse_cells(output_dir, selection)`;
`selection` is a local JSON file path. Put this call under an
`if __name__ == "__main__":` guard in Python scripts because workers use spawn.
Existing destinations are refused even with
`overwrite=True`. Flat names are always preserved; `--no-fastq-rename` is optional
in this mode. Explicit `--n-reads`, `--samples`, `--n-samples` and `--seed` conflict
with `--parse-cells` and fail. The manifest supplies exact library/cell selection;
there is no implicit read limit or sampling seed.

### Selection schema 1

This deliberately tiny example has invented sequences, not vendor barcode data:

```json
{
  "schema_version": 1,
  "profile": "parse-wt-v4-cells",
  "read_lengths": [64, 58],
  "minimum_signal_pairs": 2000,
  "biological_samples": {"sample_a": {"wells": "A1-A2"}},
  "sublibraries": {
    "library1": {
      "cells": [
        {
          "cell_id": "cell001",
          "biological_sample": "sample_a",
          "role": "signal",
          "r2_keys": ["AAAAAAAAAAAAAAAAAAAAAAAA", "CCCCCCCCCCCCCCCCCCCCCCCC"]
        },
        {
          "cell_id": "background001",
          "biological_sample": "sample_a",
          "role": "background",
          "r2_keys": ["ACGTACGTACGTACGTACGTACGT"]
        }
      ]
    }
  }
}
```

All shown fields are required; unknown fields and duplicate JSON keys fail.
Mappings/lists must be nonempty. IDs use the producer's exact printable ASCII
component restriction. `minimum_signal_pairs` is a positive integer. Each library
must contain signal cells for every declared biological sample. Cell IDs and raw
keys must be unique within a library; the same keys may occur in a different
library because those are distinct cells. Each key contains exactly 24 uppercase
ACGT bases. Multiple keys for a cell combine its R/T primer aliases into one
minimum-count check. Background barcodes may have zero matching reads.

The manifest biological sample set and exact Wells text must match the prepared
`Cell Multiplexing` sheet; missing or blank wells fail. Selected libraries must
exist in shared validated SampleSheet/workbook metadata. The producer preserves
workbook bytes and performs no metadata repair. Prepare a separately documented
copy when restricting biological samples or removing prohibited biological-only
annotations from pooled library rows. Materialize cached spreadsheet formula
values before saving a prepared copy if recalculation is unavailable, then run
shared validation and inspect all retained values.

Build real keys from reviewed vendor tables and selected-cell evidence privately.
For this geometry, concatenate zero-based R2 slices `[10:18] + [30:38] + [50:58]`
(round 3, round 2, round 1). Keep both round-1 R/T primer aliases when retaining a
biological cell. The producer checks declared metadata consistency; it cannot
prove arbitrary supplied sequences encode the declared wells. Record the vendor
version/table hash and selection procedure alongside the private manifest.

### Execution and evidence

The shared paired parser validates both complete streams, including discarded
records. Every input pair must have exact 64/58 geometry. Matching records retain
original identity, sequence, quality and source order; output lines are normalized
to LF as in the ordinary profile. Each signal cell must meet its declared retained
pair minimum before publication. A small low-count background selection can
preserve a cell-calling tail without uniformly thinning all cells.

At most two spawned processes scan separate libraries and own separate gzip
files. Workers signal failure through a shared cancellation event; another scan
checks it every 10,000 pairs. The parent collects outcomes, rechecks input
identities and publishes only after every library succeeds. Progress reports
scanned/retained totals every five million pairs and at completion, without read
identifiers. Runtime and memory depend chiefly on source scanning and selected
output size, rather than storing source reads in memory.

The same source protection, private staging and no-replace publication used by
#64 apply. Optional `RunInfo.xml` is copied byte-for-byte and hashed in **both**
profiles; it is never a geometry fallback. `Stats/Stats.json` remains required.
Fresh compressed FASTQ checksums are calculated with bounded-memory reads.
Provenance includes profile/algorithm, selection SHA-256, declared biological
relationships and cell keys, per-cell/per-key/per-library counts, source hashes
and output hashes. Treat that provenance and all real selections/outputs as
private; do not attach them to public issues, PRs or test fixtures.

`check producer` now exercises installed script and module generation with two
workers, exact all-record retention, both primer aliases, backgrounds, source
preservation, failure cleanup and normal configmaker/PEP path resolution. Fast
checks cover schema/profile errors, missing/blank wells, cancellation polling,
full-stream corruption, minimum counts and source changes. All sequences and
metadata in these tests are invented; the workflow configuration is an
initialization-only stub. Wheel and sdist checks run the same coverage.

## Operational evidence and exclusions

The first facility Parse gene-expression fixture and integration were completed
under [#83](https://github.com/gcfntnu/gcf-tools/issues/83), with workflow corrections
in [gcf-workflows #205](https://github.com/gcfntnu/gcf-workflows/pull/205). This is
separate evidence from the synthetic local checks; operational manifests, inputs,
outputs and detailed measurements remain private. Successful producer/configmaker
execution alone does not establish scientific viability.

For future fixture changes, measure the recurring workflow against the **15–30
minute target**, separately from one-time extraction, image builds and deployment.
Real integration must inspect expression,
metadata, QC/preprocessing, reports, archives, finalization and checksums; successful
generation is only the first step. Fixture-only
configuration may narrow preprocessing grids through the established setup script.
Record every adaptation and coverage exclusion. The initial integration scope
excludes TCR, [velocity](https://github.com/gcfntnu/gcf-workflows/issues/203) and
[pseudobulk](https://github.com/gcfntnu/gcf-workflows/issues/206). A fresh run of the
complete BFQ fixture suite against one final candidate image remains a separate
release gate; do not combine earlier runs at different workflow revisions into
that claim. #65 does not regenerate or deploy facility fixtures.
