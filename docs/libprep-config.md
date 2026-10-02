# Library-preparation configuration

For setup and checks see [CONTRIBUTING.md](../CONTRIBUTING.md); for caller and
generated-file boundaries see [architecture](architecture.md) and
[compatibility](compatibility.md). This page owns source/selection semantics.

`gcf-tools>=0.2` provides a portable configuration API in `configmaker.libprep`.
It has no BFQ dependency, logging setup, import-time file creation, or mandatory
`/opt` paths. The caller chooses the source (API illustration; substitute private
local paths):

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
The Python `add_workflow(config, src_dir=...)` API also accepts other workflow
locations for loading/materialization, but the generated Snakefile still includes
the literal `src/gcf-workflows` path (a known launcher limitation). If the workflow
tree is absent, it is cloned as before.

An explicit file can be supplied independently of the workflow location using
`--libprep-config PATH`, together with the usual runfolder/project selection and
`--libkit` when overriding the SampleSheet kit. See the
[offline CLI checks](../CONTRIBUTING.md#available-checks) for exercised examples.

The effective bytes are written into the project workflow tree. The generated
`config.yaml` includes `libprep_selection` diagnostics. Nested kit defaults are
merged recursively into project settings, so `filter.subsample_fastq` no longer
suppresses kit-specific `filter.trim`; explicitly supplied project values win.
The generated Snakefile include and output configuration use the same selected
workflow. This does not validate the included scientific workflow or relocate
its hard-coded paths when `--output` is changed; see
[known limitations](known-limitations.md#fixed-workflow-comparator-gaps).

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

This API/CLI was introduced for `gcfntnu/gcf-bfq#123`. Shared metadata validation
from `gcf-tools#56` / `gcf-bfq#121` has since landed. At the
[inspected BFQ baseline](architecture.md), BFQ requires `gcf-tools>=0.3.0` and
validation API 1, loads libprep configuration before demultiplexing, and selects
the geometry-specific entry once Stats.json is available. Both BFQ's Python
environment and the interpreter running `configmaker.py` must contain compatible
gcf-tools; BFQ checks the exact validator version at that subprocess boundary.

At that BFQ baseline, the authoritative source is fixed to
`/opt/gcf-workflows/libprep.config`; `BFQ_LIBPREP_CONFIG` is ignored with a warning.
BFQ captures bytes for the execution, so later source edits cannot change that
selection; a deliberate restart from analysis captures configuration again. Standalone
configmaker retains the portable local/explicit source behavior above. Metadata
parsing, structured reports and passive imports now follow
[input-validation.md](input-validation.md). Rebuild and manually verify relevant
facility environments as part of a deliberate deployment, not routine local
checks. This guidance does not authorize promotion or impose a new release policy.

Use the [contributor test tiers](../CONTRIBUTING.md#available-checks) for API and
real standalone CLI checks. The CLI
checks initialize temporary projects using the repository's small input fixture;
they do not launch Snakemake or require an `/opt` installation.
