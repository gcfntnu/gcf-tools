# Offline organism resolution

New analyses use the same local resolver for effective project values and
`dtype=string, subtype=organism` descriptors. There is no Bionty dependency,
service, account, network lookup or persistent organism cache. Recognizing a name
does not install or choose a scientific reference, assembly or index;
gcf-workflows retains that responsibility.

## Values and precedence

Exact canonical keys and scientific-name forms ignore case, surrounding space,
and differences between underscores and whitespace: `Homo sapiens` and
`homo_sapiens` emit `homo_sapiens`. Unambiguous aliases resolve automatically.
Full strain keys and qualified aliases remain distinct: `C57BL/6NJ` resolves to
`mus_musculus_c57bl6nj`, while `Mouse` uses the explicitly curated species-level
alias `mus_musculus`. Generic aliases for pig, dog, sheep, goat, bread wheat,
olive, domesticated barley, panicgrass, potato, field mustard and cocoa similarly
select their existing unqualified species key. These are explicit inventory
decisions, not runtime tie-breaking or truncation of strain names.

Other collisions remain ambiguous. For example, `reference`, `Chinese hamster`
and `hybrid cattle` require an exact canonical key. Fuzzy similarities are
diagnostic suggestions only: `Homo sapens` does **not** select a reference.
An unresolved or ambiguous nonmissing project value exits 2 before links,
config, PEP, Snakefile or analysis summaries change. Diagnostics include canonical
choices/suggestions and the inventory hash.

The established project label `metagenome` is a non-species community context.
It remains `metagenome` only when the existing libprep selector selects the
metagenome workflow from the supplied local snapshot; those same immutable bytes
are used for initialization. Its classifier database is still chosen by workflow
configuration. This label is rejected for species-reference workflows such as
RNA-seq and is not added as a fictitious species or alias to the inventory.
Descriptive per-sample annotations still follow the resolver rules below.

A truthy CLI value still takes precedence over SampleSheet `Organism` options;
later SampleSheets retain their existing option precedence. The shared validator
still represents SampleSheet `N/A` as `None`: this leaves the global `organism`
key absent. Explicit CLI `--organism N/A` emits the text `N/A`. Missing values
(`None`, empty/whitespace, `NA`, `N/A`, `<NA>`, `nan`, `none`, `null`, ignoring
case) are valid, not unresolved species.

Per-sample mixed species remain separate; per-sample values are never promoted
into the global setting. A uniform resolved/missing sample column retains the
existing global override/fill behavior. Unresolved or ambiguous descriptive
annotations are preserved verbatim, including punctuation and whitespace, with
sample-ID/column diagnostics; a global value never erases them. Missing
descriptive values retain their existing representation/stringification. Other
descriptor conversions, metadata precedence and validator/libprep contracts are
unchanged. Retained configurations are not rewritten on BFQ resume.

## Inventory and Python compatibility

`descriptors/organisms.json` is the required runtime resource. Schema 1 contains
`inventory_version`, `provenance`, `species` (canonical key to aliases), explicit
`curated_aliases` and `ambiguous_aliases`. Canonical/scientific-name matches take
precedence over historical aliases. Undeclared alias conflicts, conflicting
canonical keys, malformed data, duplicate JSON keys and unsupported schemas are
errors. A missing/corrupt resource reports an installation error; it never
downloads a replacement or falls back to a cache or pickle.

The initial JSON retains all 433 legacy keys and every legacy alias. Provenance
records the original resource SHA-256 and its last recorded Git revision/date.
The upstream release and retrieval date were not recorded and remain unknown;
the version does not claim a newly acquired taxonomy release. The old
`ens_org.pkl` is retained unchanged for historical/custom readers, and is not a
runtime fallback. Inventory updates require deliberate review and packaging.
Version `legacy-433-curation-2` additionally recognizes the exact canonical and
scientific name `rangifer_tarandus` / `Rangifer tarandus`, reviewed against
[NCBI Taxonomy record 9870](https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=9870&mode=info).
Its separate source/review date are recorded in the inventory; no upstream
release is claimed. The resulting inventory has 434 keys. This addition does
not provide or choose an assembly, index or other scientific reference.

`fuzzmatch_organism(query, min_score=80, min_letters=4)` and its package import
remain available. It returns a canonical string for exact/curated resolution,
and `None` for missing, unresolved or ambiguous inputs. Automatic fuzzy selection
is intentionally removed; the score/length arguments now filter suggestions,
not exact aliases. `fuzzmatch_reference` keeps its original behavior. `ORG_DB`
remains an iterable mapping of canonical keys and historical aliases (including
`copy()`), but is now read-only; callers must provision a reviewed inventory
instead of mutating an unrecorded global dictionary.

`descriptors.organisms.resolve_organism()` exposes status, canonical value,
candidates, suggestions and inventory SHA-256. `inventory_identity()` returns
schema/version/hash/provenance, also recorded in new config and PEP as
`organism_inventory`. Python callers may explicitly `load_inventory(local_path)`
and pass that object as `inventory=` to the resolver; its returned hash identifies
those exact bytes. Configmaker uses only the packaged artifact. There is no
environment-driven or remote/latest override, and no new Python support-floor
claim.

## Explicit maintenance and offline provisioning

Use a task-owned local JSON input containing `species`, reviewed
`curated_aliases`, and exact collision declarations in `ambiguous_aliases`.
An existing inventory is also valid input. Obtain any upstream data deliberately,
outside ordinary analysis, and record its actual release/date when known.
The retained `fetch_ensembl_species(...)` helper is an explicit network acquisition
API returning data only; it is never invoked by normal import/lookup/initialization.

```bash
python -m descriptors.inventory build supplied.json candidate.json \
  --version candidate-v1 --source-description 'Reviewed supplied local data' \
  --source-release RELEASE --source-date YYYY-MM-DD
python -m descriptors.inventory validate candidate.json
```

Build validates before creating a new output and refuses existing destinations.
The same input, options and version produce identical bytes. Its provenance
records the supplied input hash; omit release/date options when unknown rather
than inventing them. Review aliases, strains, collision declarations, provenance
and the resulting hash before replacing the repository's fixed resource in a
separate inventory update. Build/install reviewed wheel or sdist artifacts into
offline environments and compare the recorded resource hashes. Ordinary analysis
does not run maintenance, download data or alter package files/caches.
