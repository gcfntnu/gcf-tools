# Independent onboarding verification (#65)

On 2026-10-16, two fresh agent sessions independently followed repository guidance
from `bfq-dev` **`d8011ba6c5857249f0badcee7cf315c4654504e5`**. They had separate
branches/worktrees and uniquely named sibling state directories. They received
the issue, source revision, ownership boundaries and task description, without
the preceding chat history or an existing development environment. No open
overlapping PR was found at the start.

This issue changes documentation only. Runtime code, tests, packaging, dependency
pins, CLI/API, generated formats/values and scientific workflow behavior remain
unchanged. The implementation PR records the final candidate SHA and results of
replaying the updated instructions from that candidate; the initial trials below
identify gaps in the pre-change guide and are not relabeled as final-candidate
checks.

## Independent initial trials

Both participants used host-provisioned Python **3.11.17**, Git **2.53.0**, Linux
x86-64 and zlib **1.3.2**. Python was already available through the host's PATH;
neither agent activated or reused its project packages. Each literal
`python3.11 scripts/dev.py setup` independently downloaded the exact
`requirements-dev.txt` baseline into a new private environment, with no wheelhouse
or requirements override. Baseline SHA-256:
`ca8ed75321db3224458cb58794fa262244c6ee80bc59fe0c2ec84817f15926d6`.
This establishes fresh task environments, not Python installation on a clean host.

| Command from each task checkout | Trial A | Trial B |
| --- | --- | --- |
| `python3.11 scripts/dev.py setup` | Passed, 18.92 s | Passed, 20.26 s |
| `python3.11 scripts/dev.py check fast` | 273 passed, 16.39 s | 273 passed, 17.01 s |
| `python3.11 scripts/dev.py check cli` | 52 passed, 36.84 s | 52 passed, 35.46 s |
| `python3.11 scripts/dev.py check example` | 1 passed, 4.08 s | 1 passed, 3.99 s |
| `python3.11 scripts/dev.py check producer` | 14 passed, 15.76 s | 14 passed, 14.52 s |
| `python3.11 scripts/dev.py check all` | 325 passed in each of editable, wheel and sdist, 173.53 s | 325 passed in each of editable, wheel and sdist, 173.05 s |
| Documented paired-fixture regeneration | All 13 files byte-identical | All 13 files byte-identical |

Times are whole-command wall times. Setup/check activity overlapped between the
two workspaces, including their full gates. Within each workspace commands were
sequential. Each produced its own source copies, workflow trees, generated
configuration, outputs, builds and nested sdist environment. No shared mutable
environment, configuration or output was used. The retained A trial occupied
837 MiB; its full-gate reported peak RSS was 117,092 KiB. Concurrent spawned
processes can use more aggregate memory than that single-command measurement.
Budget disk for retained runs as well as setup; the runner does not auto-delete
earlier evidence. Measurements are host-specific, not guaranteed capacity bounds.

Both agents inspected the installed example's sample identities, counts, checksum
metadata and live paths. They generated supported producer outputs and checked
the documented retained counts. Regeneration was executed using the published
prepared-interpreter snippet, not a global package installation. Routine checks
required no credentials, operational paths, live service, native scientific tool,
container or email. Git-only CLI checks still use private copies of the existing
historical inputs; new example/producer data are wholly synthetic. Source archives
use the documented synthetic SE substitute in place of those historical inputs.

## Representative changes and guidance gaps

Trial A made a disposable README correction for stale producer status and
committed it locally as `0e973c8b80e2b16b86edbb4ebfcb43ddd72435d0`. Its setup,
fast and CLI results above identify the clean base; example, producer and full
gate identify that clean documentation candidate. Trial B's table reports its
clean base. B then added a regression verifying that fixture regeneration refuses
an occupied destination without changing its bytes, committed locally as
`7ac9464138438408653eb3a36985b09a0108befb`. Its subsequent `check cli` passed 53
tests in 36.68 s. Both prepared local mock PR handoffs; no practice branch or PR
was published. These disposable changes remain separate from the implementation.

Neither trial required a setup/check workaround or another developer's private
configuration. Both identified README's obsolete dormant-producer paragraph;
A also found the stale architecture entry and incomplete contributor profile
description. B could inspect producer artifacts only by finding pytest's
truncated test directory names in source. This issue corrects those statements,
adds a runnable artifact locator, connects the existing contracts, and documents
the complete [onboarding sequence](onboarding.md). No new development harness or
parallel contract was introduced. One agent's optional GitHub CLI inspection met
an expired credential; public read access sufficed. GitHub authentication was not
needed for local setup/checks, and the failure was not hidden as a setup dependency.

Detailed command logs, identities, package inventories and mock handoffs remain in
each task's private sibling directory. Public evidence deliberately omits host
paths and historical fixture metadata. Final-candidate replay results and CI
links belong in the implementation PR so its exact tested commit is unambiguous.

## Remaining acceptance

These are **agent trials on one host**, not evidence that both facility developers
completed onboarding. Personal host provisioning, legacy `.xls` compatibility,
broader layouts and scientific/deployed behavior are not established by these
checks. No BFQ data update, workflow execution, container build/deploy, real mail,
merge or production promotion is part of #65.

Initial Parse integration evidence and its coverage exclusions are recorded in
the [testdata guide](testdata.md#operational-evidence-and-exclusions). The
[foundation tracker #66](https://github.com/gcfntnu/gcf-tools/issues/66) remains
open for facility-developer confirmation and the remaining agreed manual
suite/container acceptance. The PR is the reviewable documentation/onboarding
deliverable; it does not declare the foundation accepted on behalf of its users.
