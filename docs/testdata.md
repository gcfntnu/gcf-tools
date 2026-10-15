# Synthetic paired example and testdata boundaries

The committed `tests/fixtures/paired/` fixture is independent of the dormant
`create_testdata.py` producer. Everything in this directory, including workbook
properties and identifiers, is invented for testing and may be distributed with
the source archive. No facility records, reads or infrastructure were copied.
Producer inspection/restoration remains #63/#64; this example does not restore it.

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

## Verification tiers and later profiles

`check fast` exercises shared API and isolation checks. `check example` runs the
single installed paired example; `check cli` additionally runs regeneration,
negative metadata, empty/partial discovery and oracle corruption checks alongside
the existing CLI tests. `check all` includes all of these tests in editable,
clean-wheel and unpacked-sdist environments. Existing CI runs `check all`; no
additional CI job or dependency is required. The fixture ships in sdist, not the
runtime wheel; wheel checks use a separate test bundle.

Later profiles should be added by need: lanes/chunks; repeated runs and
`--keep-batch`; multiple projects; SE; nested single-cell and index reads; source
symlinks; and malformed/reordered input pairs. Parse kits and biological/well
relationships need their own profile. This ordinary paired fixture does not prove
Parse support, real subsampling, scientific correctness or deployed compatibility.

Optional real-workflow comparison starts with immutable gcf-workflows revision
`42d37e302a2ff6c868844e6d33147460e0ec7ba3`. Pre-stage a private tree at that revision
and use its actual kit configuration; the synthetic kit is not a production kit.
Record the selected real kit, effective libprep hash and all intentional fixture
adaptations. Compare later candidates using that same fixture/environment and an
explicit candidate SHA, inspecting config, PEP paths, DAG inputs and relevant
outputs before deliberately updating the reference. Scientific/container and BFQ
server integration remain separate manual facility checks with isolated outputs
and email protection; none is implied by successful CLI initialization.
