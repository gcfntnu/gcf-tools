# Safe paired producer verification (#64)

Implementation started from `bfq-dev`
`f79d96a60324df250c453672210171ebcb9f924b` after #63 / PR #84 merged. The
candidate commit is recorded in the implementation PR. Work used an isolated
issue checkout/environment; the #63 implementation owner independently reviewed
this change read-only. No companion-repository code or operational input was
modified for these checks.

## Behavior and compatibility decisions

The [supported profile](testdata.md#safe-flat-paired-producer-64) requires exact
project/sample selection, local libprep configuration, flat paired FASTQs and the
existing no-rename option. Shared SampleSheet/workbook validation is authoritative;
generated TSVs and legacy completion/state files are neither required nor copied.
Shared Stats-geometry kit selection replaces historical SE-first precedence.

All records in both streams are validated before publication. Paired reservoir
selection preserves order and uses the documented seed; gzip headers are fixed.
Existing destinations are always refused, including the legacy API's explicit
`overwrite=True`. Source files/link targets/configuration are checked for observed
identity changes, output is staged privately and Linux no-replace rename publishes
atomically. Workbook and source Stats/InterOp bytes retain their provenance;
output checksum manifests are newly calculated and complete. The six #63 expected
failures are now passing regressions.

Installed command/module/class names and existing argument order remain; project
and seed are additive. Unsupported automatic selection, renaming and broad layouts
fail explicitly. Configmaker, shared validation/libprep APIs, package version and
scientific workflow files are unchanged. Native sampling/compression dependencies
and their development-only acquisition/guard exemptions are removed.

## Executed checks

Linux/Python **3.11.17**, using the unchanged exact `requirements-dev.txt` baseline
(SHA-256 `ca8ed75321db3224458cb58794fa262244c6ee80bc59fe0c2ec84817f15926d6`).
Setup privately copied previously acquired baseline wheels using the supported
`--wheelhouse` option; no dependency override was used.

| Command | Result |
| --- | --- |
| `python3.11 scripts/dev.py setup --wheelhouse <prepared-wheels>` | Passed; exact baseline and `pip check` verified |
| `python3.11 scripts/dev.py check fast` | 239 passed; two subsequent metadata regressions were covered by the full gate |
| `python3.11 scripts/dev.py check producer` | 7 passed, including real installed generation, normal PEP and concurrent invocations |
| `python3.11 scripts/dev.py check all` | Editable 286 passed; fresh non-editable wheel 286 passed; unpacked-sdist setup/check 286 passed |
| `git diff --check` | Passed |

Full gate elapsed 120 seconds. Existing invalid-escape deprecation warnings did
not fail checks. Imports/resources, both installed commands and module help,
distribution boundaries, offline/SMTP protection and exact dependency identities
were checked by the shared runner. Only wholly synthetic fixture data was used.

Independent assertions cover exact IDs and project choice, paired counts/content/
order, malformed records beyond selection, gzip truncation, mate conventions,
unsupported layouts, file links, spaces, invalid destinations, changed input
identities, injected disk/publication errors and concurrent empty-destination
creation. The PEP test independently formats emitted templates, resolves every
link to produced FASTQs and verifies matching MD5 metadata. Its workflow tree is
the committed initialization-only synthetic stub, not an executable workflow.

Initial development setup hit a temporary-filesystem quota and retained its
failure evidence before moving this owned checkout/environment to available disk.
The first installed-help check exposed script-directory package shadowing after
adding shared imports; existing wrapper-path protection was applied and all later
installed/wheel/sdist checks passed. These were development issues, not scientific
integration attempts.

## Remaining gate

No BFQ daemon, scientific workflow, container, deployment, production data or real
email was exercised. A format-valid random subset is not evidence of sufficient
cells/genes/coverage. The dedicated Parse gene-expression fixture and facility
integration belong to #83; broad lane/chunk/index/automatic-selection profiles
remain unsupported. Python 3.8 runtime syntax is preserved; its existing CI
historical command/initialization gate remains separate from these Python 3.11
producer results.
