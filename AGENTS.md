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
