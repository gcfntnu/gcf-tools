# Contributing

Start at [README](README.md) for the contract map. A bounded change must remain
usable both through BFQ and through standalone configmaker. Read the issue and
current source; an earlier assessment or a passing test is evidence, not a
substitute for the compatibility review.

## Task ownership and isolation

Fetch current `bfq-dev`, inspect repository instructions, branches and relevant
open PRs, then record the exact starting commit. Create an issue-specific branch
in a separate checkout or worktree. Feature PRs target `bfq-dev`; this does not
change production branch selection or promotion policy.

For example, the #60 task used `git worktree add -b
issue-60-contributor-contract ../gcf-tools-issue-60 origin/bfq-dev` after fetching
the remote, and recorded `git rev-parse origin/bfq-dev`. Substitute your own issue
and an unused directory. Git authentication is personal provisioning, never
committed configuration. Do not clean up other branches as part of a task.

| Concurrent task | Exclusive mutable ownership |
| --- | --- |
| Developer/agent A, issue 60 | Its branch/worktree, sibling `gcf-tools-issue-60-local`, environment, temporary inputs, outputs and logs |
| Developer/agent B, another issue | A different branch/worktree and differently named sibling directory; no shared editable installation or output tree |

Record task ownership and planned files/interfaces in the issue or PR. When
work overlaps, explicitly agree who edits the shared files and how the other
task will consume that commit; do not have agents edit one checkout concurrently.
In the foundation milestone, assign one owner for packaging/CI wiring and
coordinate shared test helpers; sequence the two producer issues. Read-only
source revisions or prepared dependency wheels may be copied between tasks.
Mutable fixture copies, workflow trees (configmaker writes into them), build
products and caches remain private. Decisions and handoffs belong in issues/PRs
so another developer can resume without chat history.

## Current setup

Use a full Git checkout: current tests need tracked `.tests/configmaker` fixtures
that are not a complete installed-source distribution. Linux, Git, a Python
interpreter with `venv`, and local symlink support are needed. Python 3.11 is the
current full-test CI baseline; this PR rehearsed 3.11.16. The earlier assessment
also exercised 3.12.14. Neither declares the deployed stack or removes legacy
support: CI still has a Python 3.8 script/build job, and `setup.py` does not declare
`python_requires`. Packaging/support clarification belongs to #61.

Initial provisioning is distinct from routine checks. Dependencies are declared
in [setup.py](setup.py); there is no lock, dev extra or unified check runner yet.
The recipe below assumes a **prepared, compatible local wheel directory** for
those dependencies plus `pytest`, `setuptools`, `wheel` and their dependencies.
Acquire that once using your ordinary dependency access, or copy an existing
wheel set into your task directory. #61 owns a repeatable acquisition recipe.
Do not silently fall back to network installation if the offline install fails.

From your worktree root, choose an unused sibling directory and set
`GCF_WHEELHOUSE` to the absolute path of those prepared wheels. The following
recipe was exercised with that provisioning condition:

```bash
GCF_REPO="$PWD"
GCF_DEV="${GCF_REPO}-local"
mkdir -p "$GCF_DEV"
python3.11 -m venv "$GCF_DEV/venv"
export PATH="$GCF_DEV/venv/bin:$PATH"
export PIP_NO_INDEX=1
export PIP_FIND_LINKS="$GCF_WHEELHOUSE"
export PIP_CACHE_DIR="$GCF_DEV/pip-cache"
python -m pip install setuptools wheel pytest
python -m pip install --no-build-isolation -e "$GCF_REPO"
python -m pip check
mkdir -p "$GCF_DEV/tmp"
export TMPDIR="$GCF_DEV/tmp"
export PYTHONDONTWRITEBYTECODE=1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
```

Do not reuse this directory while another process owns it. The editable install
refers to this worktree only. Keep the shell environment task-local; do not edit
shell startup files or activate a global environment. `pip check` checks declared
dependencies, not generated-value compatibility with a particular pandas version.

## Available checks

These commands run from the worktree root after setup. Use the relevant tier;
`tests` is the union of the first two commands, not an additional acceptance gate.

| Tier | Command | What it establishes |
| --- | --- | --- |
| Fast API checks | `python -m pytest -q -p no:cacheprovider tests/test_validation.py tests/test_libprep.py tests/test_workflow_config.py` | Metadata joins/diagnostics, immutable kit selection and geometry, local workflow configuration assembly |
| gcf-tools CLI/file checks | `python -m pytest -q -p no:cacheprovider tests/test_validation_cli.py tests/test_libprep_cli.py` | Real module subprocesses, file/symlink output, version guards and early failure behavior, using private inputs/local kit stubs |
| Both | `python -m pytest -q -p no:cacheprovider tests` | Current suite; this is not full BFQ or scientific integration |

The CLI tests create their own local projects. Existing success cases use
`--skip-peppy` and principally single-end inputs. They do **not** yet supply the
representative paired-end/default-PEP contract coverage planned in #62. The
[verification record](docs/verification-60.md) separates an additional one-off
default-PEP probe from reusable test coverage.

Check all supported invocation forms outside the source directory:

```bash
mkdir -p "$GCF_DEV/smoke"
cd "$GCF_DEV/smoke"
configmaker.py --help
create_testdata.py --help
python -m configmaker.configmaker --help
python -m testdata.create_testdata --help
cd "$GCF_REPO"
```

This verifies script/module invocation in an editable environment, not wheel
completeness or successful testdata production. No build command or unified
`scripts/dev.py` is advertised here before #61 provides it.

Current local checks pre-stage local workflow configuration and use packaged
organism data. They have no email path and require no services/downloads. Do not
copy the older CI initialization matrix into the routine loop: an absent workflow
tree triggers a live, unpinned clone. Do not execute testdata production as a
smoke test. If extending tests into BFQ/email, install an explicit SMTP prohibition
that also reaches subprocesses; mock delivery. `BFQ_ENV=test` alone is insufficient.

## Optional suite/container integration

Keep this separate from the routine loop and record exactly what ran. Use copied
representative facility inputs and isolated state/output/scratch roots, with the
gcf-tools candidate installed in both BFQ's interpreter and the configmaker
subprocess environment. Record Python/dependencies, source/image identities,
workflow SHA, effective libprep bytes/hash and any local edits. Check standalone
and BFQ initialization, generated config/PEP and resolved FASTQ paths, workflow
selection, and relevant downstream outputs. Real demultiplexing, container/DAG
execution and scientific verification require the relevant facility gate.

The inspected consumer baselines are in [architecture.md](docs/architecture.md).
Use a fixed baseline and an explicit candidate SHA for workflow comparisons;
never change golden output simply to follow a moving branch. Keep email mocked
in development; actual delivery checks belong to deliberately run facility
integration. See the existing [metadata](docs/input-validation.md#coordinated-deployment-and-integration-tests)
and [libprep](docs/libprep-config.md#coordinated-bfq-deployment) integration notes.

BFQ #138/#139 are related, independent work. At the #60 review,
[BFQ PR #141](https://github.com/gcfntnu/gcf-bfq/pull/141) proposed matching
worktree/environment/ownership and PR conventions. Its BFQ-specific setup runner
is not a gcf-tools command and its completion is not a prerequisite here.

## PR handoff

Keep the handoff short and concrete:

- **Scope and baseline:** closing issue reference, exact starting `bfq-dev` SHA,
  candidate commit, affected files/interfaces and any overlapping task agreement.
- **Observable outcome:** what a standalone user, BFQ caller or workflow sees;
  name defects separately from intended compatibility.
- **Compatibility:** changes (or none) to formats, IDs, filenames/directories,
  CLI/API, precedence, generated values/types, normalization, defaults,
  selection, acceptance, failures and side effects.
- **Verification:** exact commands, environment/dependency/workflow identity,
  results and fixture provenance; distinguish assertions from source inspection.
- **Remaining gate:** unperformed manual integration, unresolved policy/evidence
  and follow-up issues. Passing local checks is not permission to deploy.

Commit and push at logical checkpoints. Open the PR against `bfq-dev` with
`Closes #<issue>` and verify eventual issue closure rather than assuming it.
Leave merge, production promotion and the manual facility integration gate to
maintainers unless those actions were separately authorized.
