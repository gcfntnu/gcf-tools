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
- Published implementation checkpoints: `ca400cd1decbc1189a946163ab121aa1923d114c`
  and `4fdc825bfa5a5736ee854eda9237cc145f82f392` (tree
  `e1d2179336a870feaf778e89d701c57ff40acd99`). Final evidence-only edits follow.
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
| `check fast` | 72 passed (67 existing API + 5 guard cases) |
| `check cli` | 15 passed, including the legacy wrapper regression |
| `check tests` | 87 passed |
| `check wheel` | Fresh-wheel install and 87 tests passed |
| `check sdist` | 87 wheel tests and 87 unpacked-source tests passed |
| `check legacy` | All 7 historical initialization cases passed; local kit stubs, no clone |
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

The local host had no external DNS/Git access, so its setup used the explicit
wheelhouse option. Ordinary default acquisition was exercised in GitHub CI:
[run 37002822638](https://github.com/gcfntnu/gcf-tools/actions/runs/37002822638)
on `4fdc825` passed both jobs, including:

- Python 3.11.16 `setup` from package-index access, then `check all`, the complete
  editable/wheel/sdist assertions and evidence artifact upload.
- Python 3.8.18 installation from the historical exact comparator, `pip check`,
  both installed script/module help pairs and all seven legacy initialization
  scenarios, with local kit stubs and offline guard.

The first checkpoint's code checks also passed, but its artifact upload rejected
relative `..` patterns. Absolute task paths fixed that CI-only defect. No failed
run is reported as a wholly passing CI run.

The ordinary source archive inspected at the second checkpoint contained **50
files**, and the wheel **20 files**. All runtime Python/resources matched source;
only the three tracked bytecode removals differ under runtime package directories.
The wheel SHA-256 for the local second-checkpoint rehearsal was
`0421f9f470b2907c06abbc5e4a9e7c39edf10f4e0d8f0dacde0e6aa7b69f67c2`; its sdist was
`a01096118fc358f043d00db7d189dbc42ebccad5efbbf79dd4bd4c20e831689d`.
Archive bytes can differ with build timestamps; content completeness and runnable
installation are verified, not bit-for-bit reproducible build timestamps.

## Independent worktrees and failure checks

Two worktrees used the same source tree `e1d2179`:

- Primary `gcf-tools-61` at published `4fdc825`; state in `gcf-tools-61-local`.
- `gcf-tools-61-rehearsal` at local checkpoint `e8db5f1` (identical tree before API
  publication); state in `gcf-tools-61-rehearsal-local`.

Each ran fresh setup from its own acquired copy of the wheel set. Primary
`check wheel` (27.51 s) and rehearsal `check sdist` (54.22 s) overlapped and passed.
They had separate venvs, cache/tmp/build/test paths, outputs and identities; both
Git worktrees remained clean. This does not claim two facility developers have
completed onboarding.

An overlapping check on the occupied rehearsal worktree failed immediately with
an actionable lock message. A fresh setup using an empty offline wheelhouse failed
without changing `current.json`; the prior setup then passed `check fast` (72).
A deliberately incomplete baseline omitting `idna` was rejected even though its
compatible installed version satisfied runtime dependency checks. The sdist
setup also exercised explicit `--requirements` with the full prepared baseline.

A read-only specialist checked Python support evidence, fixture safety,
script-shadowing and installed-source isolation. Its baseline-completeness and
CI-diagnostic findings were corrected and verified. Documentation links/anchors
and `git diff --check` were checked before handoff.

## Rechecked limitations

One-off probes in the exact development environment (not permanent regression
requirements) observed:

- `GCF-2026-1000` still becomes `GCF-2026-100`.
- String-indexed `Organism: Human` still remains `Human` with pandas 3.0.6.
- Source still fixes launcher config/PEP paths; the existing PEP-path limitations
  were reviewed without modifying their implementation.
- A synthetic one-sample input with an incomplete checksum manifest exits 1 with
  `TypeError`, after creating one FASTQ link and before writing config.yaml.

The probe used the independent SE fixture, a private local kit stub, installed
modules and the same offline/SMTP guard. No workflow or production inputs ran.

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
