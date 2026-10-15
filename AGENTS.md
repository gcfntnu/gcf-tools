# Working in gcf-tools

- Read the issue, [CONTRIBUTING.md](CONTRIBUTING.md), and the relevant
  [compatibility](docs/compatibility.md) sections before editing. The issue owns
  scope; [#66](https://github.com/gcfntnu/gcf-tools/issues/66) supplies direction.
- Start a bounded issue branch and separate checkout/worktree from current
  `bfq-dev`; record its exact SHA. Inspect open PRs and agree ownership before
  overlapping files/interfaces. Never edit another task's checkout or environment.
- Keep environment, fixtures, working directories, caches and outputs task-local.
  Use copied/synthetic inputs. Do not mutate `/opt`, instrument mounts, production
  state/data, or global Python/shell configuration during development.
- Preserve standalone configmaker, installed command names/options, BFQ imports,
  formats, IDs, generated values/types, defaults, selection, paths and failure
  behavior unless the issue explicitly owns a reviewed behavior change. Record
  defects separately; their presence does not make them desirable requirements.
- Reuse [input-validation.md](docs/input-validation.md) and
  [libprep-config.md](docs/libprep-config.md); do not create competing contracts.
  Update the relevant documentation with changes to the behavior it describes.
- Run the smallest relevant [available checks](CONTRIBUTING.md#available-checks).
  Routine checks require no production paths, credentials, services or fresh
  downloads. Pre-stage local workflow inputs. Never send real email; block/mock
  any exercised email path, including subprocesses. `BFQ_ENV=test` is not a mail
  isolation mechanism.
- Pin explicit workflow revisions or identify local stubs when making consumer
  claims. No scientific or server integration claim follows from CLI success.
  gcf-workflows implementation is outside the foundation issues' scope.
- Commit/push logical checkpoints when authorized. Put decisions, overlap and
  blockers in the issue/PR, not only chat. Follow the
  [PR handoff](CONTRIBUTING.md#pr-handoff); distinguish performed checks from plans.
  Stop at the reviewable PR unless explicitly authorized further: merge,
  production promotion and manual facility integration belong to maintainers.

## Public repository content

Treat project-specific data and facility infrastructure details as non-public unless
explicitly approved for publication. This applies even when identifiers are pseudonymous,
contain no personal information, or cannot independently identify a person.

- Do not introduce real project, customer, sample, donor, pool, library or run identifiers;
  project-specific assignments or experimental designs; internal hostnames, addresses,
  storage paths, topology or deployment configuration into public repository content.
  This includes issues, comments, PR descriptions, commits, documentation, fixtures,
  logs, screenshots and uploaded artifacts.
- Describe the general behavior and use clearly synthetic examples. Preserve the
  relationships and edge cases needed to explain or reproduce the problem without
  copying real identifiers or unnecessary project details. Do not publish a mapping
  between synthetic and real identifiers.
- Reading information in a local file, user conversation, existing issue or repository
  history does not establish permission to republish it. Existing exposure is not
  permission to repeat it.
- Before committing or posting, review the complete content, including generated output
  and attachments, for project and infrastructure details. Replace unnecessary details
  with synthetic examples. If exact operational evidence is essential, keep it in an
  approved private location and publish only a general verification summary.
- Public software architecture, interfaces and documented path conventions may be
  described where needed. Distinguish these from facility-specific infrastructure and
  project-specific configurations.
