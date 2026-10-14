# Issue #60 verification record — 2 October 2026

This is a dated evidence record, not an additional setup contract or a promise
about the production environment. Current instructions live in
[CONTRIBUTING.md](../CONTRIBUTING.md). This PR changes documentation only.

## Source and ownership

| Item | Identity / observation |
| --- | --- |
| Starting gcf-tools `bfq-dev` | `059d7d94b818be79dca53a48bdf9d4b905d02ea2`; still matches the assessment |
| Issue branch/worktree | `issue-60-contributor-contract`, separate `gcf-tools-issue-60` working directory |
| Documentation checkpoint | `32dfbd87f954cba2102282b977a55a9b16b9ce40`; final evidence/corrections follow it without runtime changes |
| Task-local state | Sibling `gcf-tools-issue-60-local`: its own venv, copied wheels, tmp, smoke/probe projects and logs |
| BFQ consumer baseline | `e1042837a2cb5270ffa49fcf03675287569914c1` |
| Workflow consumer/probe baseline | `42d37e302a2ff6c868844e6d33147460e0ec7ba3`; exported from an already available local Git object, not current checkout HEAD |
| Concurrent work checked | No open gcf-tools PR before editing; BFQ #138/#139 implemented in open [PR #141](https://github.com/gcfntnu/gcf-bfq/pull/141), head `b77d149c5f44d787e88ddb677f5115e7d890a78d`; proposal, not merged baseline |

Issue #60 records ownership of these docs. #61/#62 retain setup and fixture
ownership; no setup runner, tests, runtime, packaging or workflows were changed.
A read-only specialist review cross-checked consumer imports and doc claims.
The contributor guide specifies independent ownership for a second task; this
PR does not claim two facility developers completed the #65 onboarding trial.

The task created its worktree with the Git command in CONTRIBUTING and recorded
the exact remote base. Shell `git push` failed because no Git credential helper
was configured. Checkpoints were published using the connected GitHub Git-data
API, fetched locally and checked for identical trees; no force update was used.
This transport workaround is not a new contributor authentication requirement.

## Environment and setup

Ubuntu 24.04.3 LTS, Linux x86-64, CPython **3.11.16**, pip **24.0**,
setuptools **79.0.1**, wheel **0.48.0**, pytest **9.1.1**. Runtime dependencies:
pandas 3.0.6, NumPy 2.4.6, openpyxl 3.1.5, xlrd 1.2.0, oyaml 1.0,
PyYAML 6.0.3, thefuzz 0.22.1, python-Levenshtein/Levenshtein 0.27.5,
RapidFuzz 3.14.6, six 1.17.0, requests 2.34.2 and python-dateutil 2.9.0.post0.
Ancillary versions were et_xmlfile 2.0.0, certifi 2026.7.22,
charset-normalizer 3.5.2, idna 3.20, urllib3 2.8.0, packaging 26.3,
iniconfig 2.3.0, pluggy 1.6.0 and Pygments 2.21.0. These are observed versions,
not pins or a support policy.

Prepared CPython-3.11-compatible wheels were copied into the private task
directory. A fresh venv and offline editable installation succeeded with
`PIP_NO_INDEX=1`, `PIP_FIND_LINKS` pointing at that local wheel set, and
`--no-build-isolation`. The final recipe also sets task-local `PIP_CACHE_DIR`;
the install commands were repeated successfully with it. The explicit
`python3.11` executable came from the already provisioned interpreter (full path
used when it was not on the shell PATH). No dependency acquisition from a clean
internet-only machine was claimed. Legacy setup also creates ignored `.eggs`
inside the owning checkout; #61 can replace that packaging mechanism.

| Exercised setup command | Result |
| --- | --- |
| `python3.11 -m venv "$GCF_DEV/venv"` | Fresh isolated environment created |
| `python -m pip install setuptools wheel pytest` | Passed from local wheels under the offline environment above |
| `python -m pip install --no-build-isolation -e "$GCF_REPO"` | Installed `gcf-tools 0.3.0` from this worktree |
| `python -m pip check` | `No broken requirements found.` |

The surrounding variable assignments, directory creation and cwd/PATH changes
in CONTRIBUTING were also exercised. `TMPDIR` was task-local,
`PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`; pytest cache was
disabled in the advertised test commands.

For this rehearsal, an additional **temporary, non-shipped** `sitecustomize`
audit hook was inherited by Python subprocesses. It raised on socket connection,
DNS and SMTP audit events, and on Python subprocess launches of Git, wget, curl
and mail clients. Tests and probes passed under that guard; the source paths
exercised contain no mail sender. This is extra verification isolation, not a
new available repository command or a general sandbox for arbitrary programs.
Git acquisition/publication and local workflow export happened outside that
test phase. No scientific tools or services were launched.

## Advertised checks actually run

| Command (worktree cwd unless noted) | Observed result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider tests/test_validation.py tests/test_libprep.py tests/test_workflow_config.py` | **67 passed**, 8 existing invalid-escape deprecation warnings |
| `python -m pytest -q -p no:cacheprovider tests/test_validation_cli.py tests/test_libprep_cli.py` | **15 passed** |
| `python -m pytest -q -p no:cacheprovider tests` | **82 passed**, same 8 warnings; union of the two tiers |
| `configmaker.py --help` outside checkout | Exit 0; legacy editable wrapper emits `pkg_resources` deprecation warning |
| `create_testdata.py --help` outside checkout | Exit 0; same wrapper warning; producer not executed |
| `python -m configmaker.configmaker --help` outside checkout | Exit 0 |
| `python -m testdata.create_testdata --help` outside checkout | Exit 0 |

The API illustrations in the validation and libprep guides were exercised using
private local paths: `validate_inputs`, `ok`, `render_text`, JSON serialization
of `to_dict`, `LibprepConfig.load/select`, geometry lookup, diagnostics and
byte-preserving `write`. Their example absolute paths are placeholders, not
facility paths used in this verification.

## Additional bounded source/behavior probes

An independently generated, private two-sample input used exact string IDs `001`
and `002`, customer headers at row 15, an empty valid lab sheet, flat renamed
FASTQs, geometry `[150, 150]` and 20 paired reads per sample. FASTQ gzip timestamps
were fixed to zero. The manifest had the actual supported name
`md5sum_GCF-2026-001_fastq.txt` and checksums of compressed bytes. This did not use
the dormant testdata producer or alter tracked fixtures.

With `$RUN` set to that input and cwd set to the fresh probe project containing
the local export at `src/gcf-workflows`, the executed command was:

```bash
configmaker.py "$RUN" -p GCF-2026-001 --libkit Custom --organism 'Homo sapiens'
```

It exited 0 with normal PEP enabled, workflow `default`, entry `Custom PE`,
`project_id` as a list, `read_geometry: [150, 150]`, 2 planned/discovered samples
and no missing IDs. Effective libprep SHA-256 was
`c7ffe64e0a6d2c441abfdc5d600287c4b46883c732cdbbdcf95caf5c648b582f`.
Assertions checked YAML values, two PEP CSV rows, four resolved symlinks,
derived PEP paths, all four copied MD5 values, valid four-line FASTQ structure,
150-base sequence/quality lengths and identical R1/R2 read-ID order (40 pairs).
No `peppy` parser, Snakemake DAG, scientific rule or container ran. This is
one-off evidence; #62 still owns a committed reusable representative fixture.

Small offline probes also confirmed:

- `is_valid_gcf_id('GCF-2026-1000')` returns `GCF-2026-100`.
- Descriptor conversion maps `A-B/C` to `ABC`, `10-20` to 15 and `<5` to 5;
  string-indexed `Organism: Human` stays `Human` under pandas 3.0.6.
- Discovery accepts an L001 R1 alongside an L002 R2 for the same sample.
- Retaining only one checksum record for the four-file probe causes an uncaught
  `TypeError` (exit 1), with four links already created and no `config.yaml`.
- Both historical `116_R1.fastq.gz` fixtures listed in
  [known limitations](known-limitations.md#testdata-producer) have 11 decompressed
  lines and fail four-line FASTQ structure checks.

Other limitations (directory-order selection, launcher paths, nested YAML
duplicates, workflow kit reselection and producer safety) were established by
source inspection, not broad operational execution. All probes used unchanged
runtime source.

Final documentation checks found 55 valid local links/anchors and balanced fenced
blocks; `git diff --check` passed. All changed paths are Markdown documentation.

## Remaining checks

No wheel/sdist build, clean-wheel install, Python 3.8/3.12 rerun, full legacy CI
initialization matrix, testdata production, BFQ suite/container integration,
workflow DAG execution, real mail, deployment or facility onboarding ran here.
Earlier assessment build/Python-3.12 results and upstream CI are historical
evidence, not newly performed checks. Maintainers retain the relevant manual
integration and merge/promotion gates; no operational decision blocks this PR.
