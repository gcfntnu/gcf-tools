# Issue #61 verification record — 2 October 2026

This dated record distinguishes performed checks from remaining facility work.
Current commands and package boundaries live in [development.md](development.md).

## Source and decisions

- Starting `bfq-dev`: **a6a54f03648155091306cde0ef3dae31b93ec2f8**, including merged
  #67. Separate checkout/branch: `gcf-tools-61`, `issue-61-reproducible-packaging`.
- Issue #61 and comments, tracker #66, repository guidance, branch inventory and
  open PRs were read before edits. No open gcf-tools PR overlapped. Ownership of
  packaging, CI and shared check helpers was recorded in #61.
- BFQ #141 is merged. Current BFQ development tooling was inspected at
  **f00fe06bab88eb443043bec24a91e13ce52271c7**; no BFQ or workflow changes were made.
- Existing runtime code/resources, runtime requirements, command options, package
  version 0.3.0 and validation API 1 remain unchanged. Setuptools `script-files`
  retains the legacy script/package shadowing fix; no layout rewrite.
- No `Requires-Python` restriction added. Historical [Python 3.8 CI evidence](https://github.com/gcfntnu/gcf-tools/actions/runs/36572498127)
  was rechecked: Python 3.8.18 passed the legacy initialization job at `059d7d9`.
  Its exact dependencies are separately recorded in `requirements-python38.txt`.
- Historical fixture inspection found facility-origin metadata and workbook
  properties. `.tests/` is intentionally excluded from both distributions; the
  documented generated SE substitute preserves existing source-test assertions.

Direct shell Git/network access was unavailable in the hosted task. A separate
local clone reused existing Git objects; the connector supplied the current
signed merge commit, reconstructed and verified to its exact SHA and tree.
Publication uses GitHub Git-data APIs with non-forced refs and tree comparison.
This transport limitation is not a new contributor setup requirement.

## Performed local checks

Linux x86-64, CPython **3.11.16**, pip **24.0**, setuptools **79.0.1**.
`requirements-dev.txt` records the complete exact dependency baseline; every pin
is verified after setup and before checks. Runtime pins retain the #60 observed
development versions, including pandas 3.0.6; they are not production evidence.

| Command/check | Result |
| --- | --- |
| `setup --wheelhouse /absolute/task-local/wheels` | Fresh isolated editable installation; exact baseline and pip check pass |
| `check all` | 87 tests passed in editable, wheel and sdist environments (82 original + 5 offline/mail guard cases) |
| Installed commands and module forms | Both `--help` pairs exit 0 outside checkout; no source-tree PYTHONPATH |
| Imports/resources | Version/API and public imports pass; wheel module paths are in the new venv; YAML/pickle bytes match source |
| Wheel and sdist | Both built; wheel built from sdist; required member lists/resources verified; no historical fixtures/bytecode/private environments |
| Unpacked sdist | Its own `setup --wheelhouse ... --requirements ...` and `check tests` pass in another fresh environment |

Each task-local setup/check directory retains source and fixture digests, commit
and dirty state, dependency list, requirements/wheel hashes, test transcript and
JUnit results. Archive digests/member lists are retained in `dist/contents.json`.
Eight existing invalid-escape deprecation warnings remain on editable source
execution. Build metadata warns about the historical BSD license declaration;
no license-policy change is bundled here.

Standalone profiles, parallel-worktree evidence, hosted acquisition/CI and final
review results will be recorded before PR handoff. The first local run used the
explicit offline wheelhouse option, not internet acquisition.

## Compatibility limits and manual gate

No descriptor/ID normalization, project truncation, PEP/launcher paths, checksum
failure behavior, matching libraries or testdata producer behavior was repaired.
The [known limitations](known-limitations.md) remain separate correction work.
Package success and the current tests do not establish scientific compatibility.

No real `.xls` processing, facility runtime/container integration, biological
analysis, SMTP delivery, production data access, deployment, merge or promotion
was performed. Facility Python/dependency/source/image identities and legacy
consumer requirements still need evidence before changing support policy.
#62 retains paired-end/default-PEP coverage; #63/#64 own producer restoration;
#65 owns the independent developer onboarding trial.
