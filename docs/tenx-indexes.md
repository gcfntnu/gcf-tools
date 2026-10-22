# Offline 10x index normalization

`configmaker.indexes` API 1 owns sequence expansion. It has no network or Cell Ranger
requirement. `normalize_indexes(index, index2='', i5_orientation='forward')` returns
all `{index, index2}` assignments; `normalize_rows(records, ...)` retains exact IDs,
project, lane, settings and source-row fields and adds `_index_provenance`.
`catalogue_identity()` supplies schema/version, content SHA-256, orientation and
vendor source URLs/hashes. These resources are included in wheel and sdist builds.

The bundled catalogue covers all 96 SI-GA wells (four 8-base i7 oligos per well)
and all 96 SI-TT wells (one paired 10-base i7/i5 assignment per well). The GA
reference files supplied for the Chromium i7 Multiplex Kit and Single Index Kit T
Set A use the same GA names and sequences; both sources and hashes are recorded.
No additional aliases are inferred. NA, historical GemCode/P01/3A, TN, NT, NN,
ATAC and other families are outside this initial catalogue. Supply verified explicit
sequences or retain the documented legacy converter when the full mapping is absent.
A catalogue entry establishes translation coverage, not assay or scientific support.

Sources are the vendor's [3-prime index reference resources](https://www.10xgenomics.com/support/universal-three-prime-gene-expression/documentation/steps/sequencing/sample-index-sets-for-single-cell-3).
Updates are deliberate reviewed changes to `configmaker/tenx_indexes.json`; normal
validation never downloads or refreshes it. The file itself contains each source's
hash, acquisition-independent schema and fixed version. Forward i5 in the catalogue
matches the vendor workflow-A column; its reverse complement matches workflow B.
Callers choose that representation explicitly. Literal nucleotide cells are already
oriented and are used as supplied, even when an orientation is passed for named rows.
A dual name belongs in `index`; `index2` may be empty, the same name, or its exact
expected oriented sequence. A different symbolic name or partial mixed pair fails.
Stable `IndexNormalizationError.code` values describe unknown names, conflicting or
incomplete pairs, invalid sequences, invalid orientation and broken catalogue entries.

`expand_samplesheet(content)` provides a materialized sequence sheet for an explicit
orientation edit. It retains the original symbolic label in `I7_Index_ID`, preserves
other sections and returns original bytes for sheets without named index cells.
Named dual inputs require `Index2Orientation` in `[CustomOptions]`. The caller owns
backups and reversible edit history; this function does not write any file.

Metadata validation now permits repeated Sample_ID rows in overlapping/unscoped
lanes when their index assignments are distinct and their project and metadata,
including per-row read/settings fields, agree. Exact duplicate assignments,
conflicting metadata/projects and indexed/unindexed overlaps still fail. One
expanded library requires one submission row and contributes one logical sample
in summaries, configuration and PEP. `validate_inputs` remains metadata validation;
conversion-specific sequence/cycle/collision validation belongs to
`validate_project_pairs` and the normalizer, rather than requiring every historical
metadata-only caller to translate its symbolic indexes.

`validate_project_pairs` normalizes assignments before lane/index collision checks.
Distinct oligos of the same logical library may share a mismatch neighborhood;
collisions between libraries and exact duplicate assignments remain errors.
The additive `effective_settings` mapping binds a caller's already planned settings
by project (or `legacy` for a sole unqualified pair). `validate_legacy=True` checks
conversion assignments for that sole pair. `allow_separate_passes=True` defers global
setting compatibility to BFQ's explicit pass planner; it retains whole-flowcell
index checks. `skip_conversion_projects` permits metadata-only checking for explicitly
retained legacy backend profiles. Defaults preserve previous project-pair acceptance.

The shared [workflow compatibility matrix](https://github.com/gcfntnu/gcf-workflows/blob/bfq-dev/docs/tenx-demultiplexing.md)
records assay/read layouts, images, consumer checks and unverified historical cases.
See [BFQ #156](https://github.com/gcfntnu/gcf-bfq/issues/156) and
[workflows #208](https://github.com/gcfntnu/gcf-workflows/issues/208) for coordinated
integration. Offline unit/CLI/distribution checks do not establish scientific
compatibility or authorize retirement of a legacy converter.
