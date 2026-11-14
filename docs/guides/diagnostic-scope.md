# Simple diagnostic scope routing

Policy version 1: **transverse by default, with explicit local exceptions**.
This is a first-pass rule lookup, not a function-body or dependency analyzer.

## Local

- All currently known documentation rules: `missing_errors_doc`,
  `missing_panics_doc`, `doc_markdown`, `doc_lazy_continuation`,
  `too_long_first_doc_paragraph`.
- Explicit local mechanical rewrites: literal readability, raw-string hashes,
  formatting idioms, assertion idioms, and listed expression/control-flow
  simplifications. The executable catalog lists every exception.

## Transverse

- API, parameter passing, types, visibility and annotation rules.
- Structural changes, signatures, complexity and naming.
- Runtime, ownership, casts, error handling and allocation/drop concerns.
- Imports, item movement and uncertain mechanical cases.
- Native Sonar rules until specifically admitted as local.
- Every unknown rule, including future documentation-looking rule names.

The old `mechanical` category is not a blanket local exception.
Only exact rule identifiers are matched; `external_clippy:` is normalized to
`clippy::`. No message text, symbol name or source location is used to infer
locality.

## Commands

From the tool checkout, inspect the complete known rule catalog:

```powershell
python -B ops/scripts/diagnostic-scope.py --catalog
```

Route every record of an existing overlap inventory:

```powershell
python -B ops/scripts/diagnostic-scope.py `
  --inventory <overlap.json> `
  --output <scope-routing.json>
```

The output parent must exist. Input/output aliases are rejected. Output is
deterministic and replaced only after validation; it includes the inventory
SHA-256, one route per retained diagnostic, a per-rule catalog and separate counts
for Clippy diagnostics, Sonar sites, raw Sonar keys and the strict union.
Exact one-to-one alias pairs are counted once in the union, not discarded from
the retained records. Invalid accounting fails rather than silently losing rows.

`needs_dependency_analysis` is false for local routes and true for transverse
routes. Use it to select the next dependency investigation. This new stage does
not rewrite a saved MCP collection plan or automatically filter the existing
collector; it performs no source reads, MCP calls, corrections or dispatch.

“Transverse” means conservatively selected for investigation, not a proven
cross-file change. Routing creates no hard co-edit constraints and changes no
existing graph qualification rules. Local corrections still receive ordinary
code review; expanding their scope requires reconsidering the route.

## Verified historical inventory

On the saved input of 1,046 retained records, all **77 observed rule types** were
recognized. The strict union of 620 entries routes to **328 local** and
**292 transverse**. The 1,312 raw Sonar keys route to **644 local** and
**668 transverse**. These are different populations, not additive totals.
Private input and routing output remain local and are not bundled here.

```powershell
python -S -B -m unittest discover -s ops/tests -p test_diagnostic_scope.py
```
