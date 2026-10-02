# Reproducible local development

## Setup once, check offline

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
credentials, `/opt`, `/mnt`, container or workflow checkout is needed. Index and
certificate environment settings can be supplied during acquisition. Linux
platforms without wheels for this baseline fail explicitly; the exercised target
is x86-64. Interpreter acquisition itself is ordinary personal provisioning.

All mutable state lives in the sibling **`<checkout-name>-local/`** directory:
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

This optional path copies the selected wheels into the task's own wheelhouse;
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
| `fast` | API tests and offline/email guard checks |
| `cli` | Existing real CLI/file tests, including private copies of historical Git inputs |
| `tests` | Fast plus CLI; no archive build |
| `wheel` | Build sdist and wheel, inspect both, install wheel into a fresh non-editable venv, run all tests against that installation |
| `sdist` | Wheel checks plus unpacked-sdist setup and all tests in another fresh editable environment |
| `all` | Current checkout tests plus wheel and sdist checks; shared local/CI gate |
| `legacy` | Git-only seven-case historical initialization matrix using installed script and local kit stubs |

`tests/test_*_cli.py` belongs to the CLI tier; other `tests/test_*.py` files belong
to the fast tier. #62 can add its paired-end/default-PEP CLI coverage there without
rewiring CI. Existing CLI tests principally use single-end inputs and
`--skip-peppy`. The legacy profile checks initialization, including PEP emission,
not valid paired read content, workflow execution or the #62 contract.

The runner removes ambient `PYTHONPATH`, `PYTHONHOME` and pytest options, disables
plugin autoload and user site packages, and uses invocation-private temp/cache
paths. The test-only `sitecustomize.py` is copied into each private venv, never
into a distribution. With `GCF_DEV_OFFLINE=1` it blocks socket/DNS/SMTP events,
shell execution and external executables, except the checked interpreter,
installed tools and fixed local OS-identity probes needed by pip. Tests verify
SMTP, SMTP_SSL, reloads/custom ports and ordinary Python subprocess inheritance.
This is an accidental-side-effect guard, not a security sandbox for hostile code
or arbitrary non-Python children. Do not remove it or add unreviewed exemptions.
No current check sends mail or runs the testdata producer; only producer help and
imports are exercised. `BFQ_ENV=test` is not a replacement for this protection.

## Distribution boundary and source testing

The wheel contains the four existing packages, both unchanged script filenames,
`descriptors/default_descriptors.yaml`, and `descriptors/ens_org.pkl`. Setuptools
`script-files` preserves the current script/package shadowing protection. The
version comes from `configmaker.__version__`; `setup.py` is a compatibility shim.
`setup_requires` is gone. Runtime dependencies and public API remain unchanged.

The sdist includes runtime source/resources, tests, the safe fixture generator,
helpers, development baselines and documentation. It excludes `.tests/`, CI,
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
producer output or the representative paired-end fixture owned by #62.
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
`dist/contents.json`; pytest emits transcripts and JUnit results. Setup and
build-failure artifacts remain available for diagnosis. Source-distribution
identity is explicitly reported without an invented Git SHA. No index
credentials or shell environment dumps are recorded in these identity files.

Two developers use different issue branches/worktrees and their separate sibling
state directories. The verification record documents simultaneous checks in two
worktrees; this is isolation evidence, not the facility onboarding trial (#65).

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
