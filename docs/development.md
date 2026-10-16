# Reproducible local development

## Setup once, check offline

For the complete task sequence and two-workspace rehearsal, start with
[onboarding](onboarding.md). This page owns environment and check semantics.

Use Linux, Git, Python **3.11** with `venv`/`ensurepip`, and symlink support.
From a fresh checkout (or an unpacked source distribution):

```bash
python3.11 scripts/dev.py setup
python3.11 scripts/dev.py check fast
python3.11 scripts/dev.py check all
```

`setup` uses ordinary one-time package-index access to download wheels for the
exact [development baseline](../requirements-dev.txt), installs an isolated venv
and this checkout editable, and verifies every pinned version plus `pip check`.
No prepared wheel directory, activated environment, global installation, BFQ,
credentials, `/opt`, `/mnt`, container or workflow checkout is needed. The paired
producer uses Python gzip and requires no external-tool downloads. Index and
certificate environment settings can be supplied during acquisition. Linux
platforms without wheels for this baseline fail explicitly; the exercised target
is x86-64. Interpreter acquisition itself is ordinary personal provisioning.

Environments, caches, build snapshots and check output live in the sibling **`<checkout-name>-local/`** directory:
`setups/` contains independently acquired wheels, caches and environments;
`runs/` retains check logs, temporary inputs, outputs, builds and fresh wheel
venvs. Thus even installed-command cwd is outside the checkout. Do not share or
rename these directories between worktrees. A nonblocking task lock rejects
simultaneous setup/check commands for the same checkout. Successful setup
atomically updates `current.json`; failed acquisition leaves the previous setup
usable. A moved checkout or changed project/baseline requires setup again.

A deliberately disconnected setup can reuse an existing wheel directory:

```bash
python3.11 scripts/dev.py setup --wheelhouse /absolute/path/to/prepared/wheels
```

This optional path copies the selected wheels into the task's own workspace;
it is not the default prerequisite. An intentional dependency experiment uses
`setup --requirements /absolute/path/to/exact-requirements.txt`. The file must
contain exact `name==version` lines including all runtime, development and build
dependencies. Its contents, origin and hash are recorded. Neither option changes
runtime dependency declarations or constitutes production approval. Do not
silently fall back to a different environment when a pin is unavailable.

## Check profiles

All commands below start with `python3.11 scripts/dev.py check`. They reuse the
last successful setup and enforce offline dependency installation. Every profile
checks pinned versions, `pip check`, installed imports/resources, and help for
both script and module forms from an isolated cwd.

| Profile | Scope |
| --- | --- |
| `example` | One installed default-PEP [paired example](testdata.md), with retained inputs and outputs |
| `producer` | Installed paired and Parse cell producers, normal configmaker/PEP consumption, failures and concurrency |
| `fast` | API tests and offline/email guard checks |
| `cli` | Existing real CLI/file tests, including private copies of historical Git inputs |
| `tests` | Fast plus CLI; no archive build |
| `wheel` | Build sdist and wheel, inspect both, install wheel into a fresh non-editable venv, run all tests against that installation |
| `sdist` | Wheel checks plus unpacked-sdist setup and all tests in another fresh editable environment |
| `all` | Current checkout tests plus wheel and sdist checks; shared local/CI gate |
| `legacy` | Git-only seven-case historical initialization matrix using installed script and local kit stubs |

`tests/test_*_cli.py` belongs to the CLI tier; other `tests/test_*.py` files belong
to the fast tier. `test_paired_cli.py` adds paired content and default-PEP coverage
without rewiring CI. Earlier CLI tests principally use single-end inputs and
`--skip-peppy`. The legacy profile checks initialization, including PEP emission,
not valid paired read content, workflow execution or the #62 contract.

The runner removes ambient `PYTHONPATH`, `PYTHONHOME` and pytest options, disables
plugin autoload and user site packages, and uses invocation-private temp/cache
paths. The test-only `sitecustomize.py` is copied into each private venv, never
into a distribution. With `GCF_DEV_OFFLINE=1` it blocks socket/DNS/SMTP events,
shell execution and external executables, except the checked interpreter,
installed commands and fixed local OS-identity probes needed by pip. Native
seqkit/gzip commands are no longer allowed. Tests verify
SMTP, SMTP_SSL, reloads/custom ports and ordinary Python subprocess inheritance.
This is an accidental-side-effect guard, not a security sandbox for hostile code
or arbitrary non-Python children. Do not remove it or add unreviewed exemptions.
No current check sends mail. The producer executes only on tiny synthetic copies
under the [supported producer harness](testdata.md#generate-and-verify-the-supported-profiles).
`BFQ_ENV=test` is not a replacement for this protection.

## Distribution boundary and source testing

The wheel contains the four existing packages, both unchanged script filenames,
`descriptors/default_descriptors.yaml`, and `descriptors/ens_org.pkl`. Setuptools
`script-files` preserves the current script/package shadowing protection. The
version comes from `configmaker.__version__`; `setup.py` is a compatibility shim.
`setup_requires` is gone. Runtime dependencies and public API remain unchanged.

The sdist includes runtime source/resources, tests, the safe fixture generator,
helpers, the reviewed wholly synthetic `tests/fixtures/paired/` data, development
baselines and documentation. It excludes `.tests/`, CI,
environments, caches, bytecode and build products. Historical `.tests` files
include facility-origin workbooks/metadata and are deliberately Git-only.
No historical records, workbook properties or sequencing snippets are copied
into the synthetic fixture in `tests/sdist_fixture.py`.

For the existing libprep CLI assertions, a Git checkout uses the original
historical RNA fixture, repairing only J48 in a private copy. A source archive
(or the wheel test bundle) uses an independently generated one-sample SE workbook,
SampleSheet, 86-cycle Stats and 86-base FASTQ. It deliberately has the same
invalid-note precondition, so the existing repair assertion is retained. This
substitute establishes packaging/test portability; it is **not** restored
producer output or a substitute for the [representative paired fixture](testdata.md).
`tests/prepare_cli_fixtures.py` remains shipped for documented Git-only legacy
work; the historical matrix is unavailable from sdist by design.

The supported sdist workflow is the same three setup/fast/all commands above,
run in the unpacked directory. Setup may use ordinary dependency access or the
explicit offline wheelhouse option. `check sdist` actually builds the archive,
checks its member list, extracts it, runs its own setup with the prepared wheels,
and runs its `check tests`. The normal build frontend also builds the checked
wheel **from that sdist**. This verifies source rebuild and source testing without
requiring Git history or source-tree path injection. A recursive `check all`
inside the sdist is unnecessary; the same shared profiles are available.

Archive inspection verifies every runtime source/resource byte, installed script
filenames, required source-test files and the exclusion boundary. Wheel tests
copy only tests into a separate directory; all runtime module paths must resolve
inside the fresh wheel venv. Legacy egg-wrapper execution remains a separate
regression test. The known generated-value/path defects are not repaired or
encoded as permanent expected results by these packaging checks.

## Evidence, concurrency and compatibility

Each setup/check retains `identity.json`, exact `packages.txt`, source/fixture
hashes and commit/dirty state (when Git exists). Setup records requirements and
wheel SHA-256 values. Checks reject changed wheels, changed pins and installed
version drift. Archives have SHA-256 values and complete member lists in
`dist/contents.json`; pytest emits transcripts and JUnit results. Editable installation may create ignored `gcf_tools.egg-info` in its own
checkout; the separate Python 3.8 CI job uses its private `.dev/legacy`. Setup and
build-failure artifacts remain available for diagnosis. Source-distribution
identity is explicitly reported without an invented Git SHA. No index
credentials or shell environment dumps are recorded in these identity files.

Two developers use different issue branches/worktrees and their separate sibling
state directories. [Onboarding verification](verification-65.md) records independent
agent rehearsals, overlapping checks and outstanding facility-developer sign-off.
An agent rehearsal does not establish that either facility developer completed it.

Python 3.11 is a **development reference**, not a new runtime floor. There is no
new `Requires-Python` restriction. Historical Python 3.8.18 CI passed the legacy
matrix at runtime baseline `059d7d9`; the retained 3.8 CI job uses the separately
recorded [historical comparator](../requirements-python38.txt). Its acquisition
is separated from offline installed-command/legacy checks. This does not prove
all public APIs work on every interpreter or establish deployed versions.

The primary development pins retain the runtime versions exercised under #60;
they are not inferred production requirements. In particular pandas 3.0.6 has
known organism-assignment differences. Pinning it makes existing evidence
repeatable, not scientifically authoritative. `xlrd==1.2.0`, fuzzy libraries,
`.xls` acceptance code, version 0.3.0 and validation API 1 remain unchanged.
Actual `.xls` behavior and facility dependency identities still need independent
evidence; dropping Python 3.8 or `.xls` requires a separate explicit decision.

Optional BFQ/container/scientific integration remains manual, using fixed source
revisions, copied inputs and private output roots as described in
[CONTRIBUTING](../CONTRIBUTING.md#optional-suitecontainer-integration).

## Intentional companion checkouts

Routine gcf-tools checks use the committed initialization-only workflow stub.
They do not install BFQ or gcf-workflows. `requirements-dev.txt` pins Python
dependencies; it is not a moving companion checkout. The optional workflow
comparator is an immutable revision recorded in [architecture.md](architecture.md)
and fixture provenance. Keep that default unchanged during an experiment.

To inspect a local gcf-workflows candidate, create a separate disposable analysis
directory and copy that candidate's complete tree to its `src/gcf-workflows`
before running configmaker. Record the workflow commit, dirty diff (if any),
effective `libprep.config` SHA-256 and chosen kit. Use the same copied inputs,
gcf-tools candidate and dependency environment in a second independent analysis
directory for the fixed comparator. Configmaker writes workflow configuration;
never point both analyses at one mutable workflow tree. Its `--libprep-config`
selects configuration bytes, not a different Snakefile include location. A
different config filename via `--output` is not a second analysis directory.
The synthetic `Synthetic PE` kit is a stub, not a kit to inject into real workflows.

For the reverse direction—testing this tools checkout as a BFQ dependency—use
BFQ's documented `scripts/dev.py setup --gcf-tools <tools-checkout>` in a separate
BFQ task checkout. BFQ copies/builds that explicit source snapshot; later tools
edits require BFQ setup again. Omit the override on a subsequent setup to return
to BFQ's immutable requirements baseline. That command belongs to BFQ, not this
repository's runner. Read the selected BFQ revision's development guide first.

These are optional comparison procedures, not part of local onboarding. They
require suitable reviewed inputs and named companion revisions; no scientific,
container or server result follows from initialization alone. Record differences
before proposing a deliberate baseline update, and keep facility data/evidence
private. Neither procedure changes production branch selection.
