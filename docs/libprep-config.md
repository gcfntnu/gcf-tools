# Library-preparation configuration

`gcf-tools>=0.2` provides a portable configuration API in `configmaker.libprep`.
It has no BFQ dependency, logging setup, import-time file creation, or mandatory
`/opt` paths. The caller chooses the source:

```python
from configmaker.libprep import LibprepConfig, find_read_geometry

snapshot = LibprepConfig.load("/my/workflows/libprep.config")
selection = snapshot.select("Illumina Nextera XT DNA Library Prep",
                            find_read_geometry(["/data/flowcell"]))
print(selection.diagnostics())
snapshot.write("/project/src/gcf-workflows/libprep.config")
```

The immutable snapshot retains the exact source bytes, including comments and
uncommitted edits. Its SHA-256 identifies those bytes. `selection.parameters`
returns independent data; source edits and consumer mutations cannot change the
snapshot. The diagnostics contain source, hash, input kit, selected entry,
read lengths and workflow. `LibprepConfigError` carries actionable failures.

## Standalone configmaker

Without flags, configmaker reads `src/gcf-workflows/libprep.config` in the project.
The Python `add_workflow(config, src_dir=...)` API also supports other workflow
locations. If the workflow tree is absent, it is cloned as before.

An explicit file can be supplied independently of the workflow location:

```console
configmaker.py /data/flowcell -p GCF-2026-001 --libkit "My kit" \
  --libprep-config /configs/local-libprep.config
```

The effective bytes are written into the project workflow tree. The generated
`config.yaml` includes `libprep_selection` diagnostics. Nested kit defaults are
merged recursively into project settings, so `filter.subsample_fastq` no longer
suppresses kit-specific `filter.trim`; explicitly supplied project values win.
The Snakefile and `config.yaml` always use the same selected workflow.

BFQ additionally supplies `--libprep-sha256`, `--libprep-entry`, and
`--expected-read-geometry` to check agreement across its subprocess boundary.
These are assertions, not overrides. A mismatch fails before the Snakefile is
generated. The equivalent `add_workflow` keywords are `expected_sha256`,
`expected_entry`, and `expected_read_geometry`; `libprep_config` accepts either
a path or a `LibprepConfig` snapshot.

## Kit and read-geometry policy

- Geometry comes from non-index reads in `Stats/Stats.json`, checked across all
  lanes and input flowcells. One positive length means SE; two mean PE. A missing
  or inconsistent geometry is an error, never an arbitrary SE/PE guess.
- Kit matching ignores outer whitespace and letter case. Prefer `<kit> SE` or
  `<kit> PE` for the actual geometry, then an exact unsuffixed entry. A supplied
  suffix or configured `library_layout`/`reads` value must agree with the geometry.
- Unknown or empty kits fail. There is no implicit fallback. To intentionally run
  the default workflow, select a defined kit with `workflow: default`, such as
  the workflow repository's `Custom SE`/`Custom PE` entries. An explicitly defined
  unsuffixed `default` entry can also be selected with `--libkit default`.
- Empty/malformed YAML, duplicate top-level kit names (including case-only
  duplicates), invalid entry mappings, and missing/invalid workflow names fail.
  This validates configuration selection; it does not validate all possible
  workflow parameters or submission metadata.

## Coordinated BFQ deployment

This API/CLI is the dependency for `gcfntnu/gcf-bfq#123`. Install the companion
gcf-tools revision in **both** BFQ's Python environment and the environment of
`/opt/conda/bin/configmaker.py`. The BFQ package requires `gcf-tools>=0.2`; older
subprocess installations will reject the new CLI flags rather than silently use
a different configuration. Promote the dependency to the relevant development
and production branches before building BFQ without a branch override.

Future work in `gcf-bfq#121` / `gcf-tools#56` can reuse `LibprepConfig.load()` for
early configuration validation and this selection API when geometry is known.
SampleSheet/submission-form compatibility and structured metadata validation
remain separate work. Existing configmaker logging/metadata parsers are unchanged.

Run `python -m pytest -q tests` for API and real standalone CLI checks. The CLI
checks initialize temporary projects using the repository's small input fixture;
they do not launch Snakemake or require an `/opt` installation.
