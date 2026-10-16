# Rehearse an independent change

Start with [README](../README.md), [CONTRIBUTING](../CONTRIBUTING.md), your issue
and the relevant [compatibility boundary](compatibility.md). The sequence below
is the ordinary local path; [development.md](development.md) owns environment,
profile and distribution details. No BFQ installation or live service is needed.

## Give the task its own checkout

From an existing clone, inspect its branch/status before fetching. Review open
PRs in GitHub and record any overlapping files/interfaces in the issue or PR.
For this example, `../gcf-tools-onboarding-a` and its sibling
`../gcf-tools-onboarding-a-local` must both be unused. Substitute your real issue
branch and unique paths; do not reset or clean someone else's checkout.

```bash
git status --short --branch
git fetch origin bfq-dev
git rev-parse origin/bfq-dev
git worktree add -b rehearsal/onboarding-a ../gcf-tools-onboarding-a origin/bfq-dev
cd ../gcf-tools-onboarding-a
git rev-parse HEAD
git status --short --branch
```

Record that base SHA before editing. For a concurrent trial, participant B follows
the same steps with `onboarding-b` in both branch and path. Each owns its checkout
and entire sibling `-local` directory, including environments, wheels, caches,
builds, copied fixtures, generated workflow/config trees and outputs. They may
share Git object storage, but never an editable installation or mutable analysis
directory. Only one setup/check command runs at a time **within** each checkout;
commands in the two separate workspaces may overlap.

## Acquire once, exercise offline

With a host-provisioned Linux Python 3.11 and Git, run these in each new checkout:

```bash
python3.11 scripts/dev.py setup
python3.11 scripts/dev.py check fast
python3.11 scripts/dev.py check cli
python3.11 scripts/dev.py check example
python3.11 scripts/dev.py check producer
```

Setup independently acquires the pinned dependencies. No activation, prepared
wheel directory or private shell configuration is a prerequisite. Routine checks
reuse that environment, verify its versions and run offline with network/SMTP
protection inherited by Python subprocesses. Both installed command and module
help forms are checked from outside the source tree on every invocation.

Follow [the example inspection instructions](testdata.md#run-and-inspect-the-example)
to inspect generated config, PEP, discovery summary, checksums and live FASTQ links.
Then use [producer inspection](testdata.md#generate-and-verify-the-supported-profiles)
to find both supported profiles' outputs and provenance. The assertions verify
records and metadata independently of successful command exit. Use the
[regeneration command](testdata.md#provenance-and-regeneration) to produce a new
paired fixture candidate; `check cli` includes the byte-for-byte regeneration
comparison. Scientific processing is outside these initialization checks.

Keep the printed artifact directory from every command. Its `identity.json`
records the source revision/dirty state and file hashes; `packages.txt` records
installed versions. The setup's `state.json` records acquired wheel hashes and
is mirrored in the sibling directory's `current.json` after successful setup.
Report failures and any extra step you needed. Failed setup retains evidence and
does not replace the last successful environment. The runner already places
temporary files and caches in task-owned storage; check free space there before
starting. [Measured rehearsal costs](verification-65.md) are observations on one
host, not a runtime or disk quota promise.

## Make a bounded change and prepare the handoff

Choose a small issue-relevant documentation or regression-test improvement on the
disposable branch. State its intended behavior and file ownership first. Keep
the test independent of the implementation it checks. Run the smallest relevant
profile after editing, inspect the diff and then run the full gate:

```bash
python3.11 scripts/dev.py check all
git diff --check
git diff --stat
git status --short --branch
```

The full gate tests the source checkout, a fresh non-editable wheel installation
and an unpacked source distribution with its own setup. A source-only pass does
not establish packaging correctness. Record the tested source hash and dirty diff
if tests preceded the commit; after committing, record the commit too. Stage only
the intended files and use a meaningful commit message. A rehearsal requires a
local mock PR description, not a public practice PR. Keep that handoff in the
task's sibling state directory.

Use the [PR evidence checklist](../CONTRIBUTING.md#pr-handoff). A useful mock
handoff identifies the issue/base/candidate, change and affected interfaces,
commands/results, pinned dependency identity, synthetic inputs and workflow stub,
resource costs, problems/interventions, and unperformed integration. Real feature
PRs target `bfq-dev`; merge and production promotion remain deliberate actions.

## Optional companions and human acceptance

[Intentional companion checkouts](development.md#intentional-companion-checkouts)
explains local overrides, fixed workflow comparators and immutable candidate
identities. Those procedures and [facility integration](../CONTRIBUTING.md#optional-suitecontainer-integration)
are separate from this executable local rehearsal. Do not run an initialization
stub as a scientific workflow or silently replace a pinned baseline.

For each facility developer's eventual trial, record the date, base/candidate,
personal interpreter provisioning, exact commands/outcomes, independent paths,
representative change/mock handoff and any undocumented assistance. Report these
separately from [agent rehearsal evidence](verification-65.md). Keep the
[foundation tracker](https://github.com/gcfntnu/gcf-tools/issues/66) open until its
agreed developer acceptance and remaining manual suite/container evidence exist.
