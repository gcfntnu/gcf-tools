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

Use Linux/Python 3.11 with Git and venv support. From this task's fresh checkout:

```bash
python3.11 scripts/dev.py setup
python3.11 scripts/dev.py check fast
python3.11 scripts/dev.py check all
```

Setup acquires the exact development dependencies once using ordinary package
access; subsequent checks are offline. Environments, caches, builds and outputs
live in this checkout's uniquely named sibling `<checkout-name>-local/`.
No activation, global configuration, production paths or prepared-wheel handoff
is required. The [development guide](docs/development.md) owns acquisition,
disconnected setup, explicit overrides, failure identities and sdist testing.

## Available checks

| Tier | Shared command | Evidence |
| --- | --- | --- |
| Fast API | `python3.11 scripts/dev.py check fast` | Validator/libprep/workflow assembly and offline/email guard |
| Real CLI/files | `python3.11 scripts/dev.py check cli` | Existing assertions with installed subprocesses and private file inputs |
| Both | `python3.11 scripts/dev.py check tests` | All current tests in the prepared editable environment |
| Distribution | `python3.11 scripts/dev.py check wheel` or `check sdist` | Fresh non-editable wheel imports/scripts/resources/tests; sdist adds its own setup/tests |
| Full local gate | `python3.11 scripts/dev.py check all` | Editable plus wheel plus sdist; same command as CI |
| Historical initialization | `python3.11 scripts/dev.py check legacy` | Git-only seven-case legacy matrix, with local workflow configuration stubs |

Both installed help commands and both module forms run outside the checkout in
each profile. Tests never inject the source tree via PYTHONPATH. Historical
inputs remain Git-only; the source archive includes a documented synthetic SE
substitute retaining the existing libprep assertions. #62 owns representative
paired-end/default-PEP coverage; it can add `tests/test_*_cli.py` without CI edits.

See [#61 verification](docs/verification-61.md) for actual results and limitations;
[#60 verification](docs/verification-60.md) remains historical evidence. No local
check executes scientific workflows or the dormant testdata producer. Routine
Python/subprocess checks block network and SMTP; never use BFQ_ENV as a substitute
for mail isolation. No passing test establishes scientific compatibility.

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

The merged [BFQ PR #141](https://github.com/gcfntnu/gcf-bfq/pull/141) supplied useful
setup/check, worktree-isolation and evidence conventions. Each repository remains
independently usable; gcf-tools does not require BFQ or its development environment.

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
