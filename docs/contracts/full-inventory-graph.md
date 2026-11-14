# Full-inventory work graph — bounded implementation contract

Status: implementation contract authorized by the lead on 2026-11-14 for the
user-requested generalization. No production correction or dispatch authorization.
Baseline supplied by the parent: published `9887b39` on `master`, plus existing
uncommitted scope-routing work, which must be preserved.

## Decision

Add one final command that consumes the **entire** existing diagnostic inventory,
automatically discovers relevant native Rust graph items, collects their
dependencies through the existing read-only backend, and emits a provenance-rich
file work graph and report. Reuse the collector/SDK, routing policy, range
validator and planner graph semantics. Do not introduce another semantic engine,
Rust resolver or mandatory manual source/seed/origin plan.

Multiple upstream commands are acceptable: acquiring Clippy/Sonar and producing
the overlap inventory remain outside this command. The new command generalizes
the legacy sampled producer; it does not rewrite its proof schemas to pretend
unsupported generic observations meet the old source-specific origin profile.

Sources inspected: `docs/contracts/io.md`, the extraction contract,
`docs/guides/diagnostic-scope.md`, collector allowlists/producer entry points and
the existing source-specific `ORIGIN_*` constraints. The latter remain a legacy
compatibility path, not the new command's mandatory origin identity.

## Ownership and dependencies

- **A — native adapter:** existing `ops/scripts/mcp-code-evidence.py`,
  `ops/tests/test_mcp_code_evidence.py`, corresponding guide. Own curated generic
  read tools, native graph discovery, pagination, automatic item selection and
  generic capture export. Reuse existing transport/capture utilities; do not
  copy a second SDK client.
- **B — final command and offline graph:** new
  `ops/scripts/lint-workgraph.py`, `ops/tests/test_lint_workgraph.py`, existing
  `ops/scripts/clippy-constraint-plan.py` and its tests as needed, and
  `docs/guides/full-inventory-graph.md`. Own orchestration, full-record accounting,
  generic graph validation/assembly, output/report and timing.
- **Parent:** live schema witnesses, integration, final real run and narrowly
  necessary README/vault updates. Preserve `diagnostic-scope.py`, its tests,
  guide and uncommitted README/vault changes; do not replace or reset them.

B can implement against synthetic captured fixtures while A implements the
adapter. Live integration waits for the verified adapter schema. No concurrent
writers on the same files. Existing shared scanner is reused, not independently
expanded by A/B. Direct workers only; no new team, worktree or runtime.

## Command and operating boundary

```text
python -B ops/scripts/lint-workgraph.py
  --workspace <absolute-target-git-root>
  --inventory <overlap.json>
  --output <graph.json>
  --report <report.md>
  [--url <loopback-MCP-URL>]
  [--serena-url <loopback-MCP-URL>]
  [--binding <existing-source-binding.json>]
```

Use existing requirements and root/output conventions. The command creates a
fresh run-artifact directory adjacent to the output, disjoint from outputs,
inputs and source files. Name/report that directory explicitly. An existing
artifact directory is an error, not permission to overwrite captures.
Persist a small run manifest and partial capture/error evidence on failure.
Keep accepted final output atomic; no swallowed exceptions or exception-to-zero.

Workspace authority is the explicit target root, never the tool checkout or an
input manifest. Tool and target HEADs may differ. Read-only loopback SDK,
finite deadlines/budgets, no proxy/redirect, source/hash/root guards and owned
client-session cleanup remain mandatory. No OpenCode dependency, backend writes,
build_hypergraph, cache clearing, activation, indexing, runtime startup, Cargo
build/test, repository mutation or correction dispatch.

## Whole-inventory selection, not another sampling plan

1. Validate overlap accounting and retain every Clippy/Sonar source record and
   alias/hint. Invoke/reuse the existing scope policy, not a new taxonomy.
2. Retain every diagnostic file as a graph node, including local-only files,
   missing ranges, unsupported items and unresolved paths.
3. Local routes skip dependency queries initiated **for that route**. Routing is
   query selection, not proof of source-local correction or independence.
   A local diagnostic's file can still appear on a dependency edge discovered
   for a transverse item.
4. Every transverse source record enters a work queue and ends in a named
   outcome: queried, reused-query, unresolved localization, unavailable backend,
   budget/deadline stopped, or source-invalid. No hidden seeds, rule samples,
   fixed top-N or manually prepared source file list.
5. Automatically discover native items in every transverse diagnostic file.
   Map diagnostics by verified file/range where possible. If exact diagnostic
   attribution is unavailable, query positively file-bound relevant item
   candidates and label the attribution candidate, rather than silently skipping
   that record. Record shared query IDs when several diagnostics reuse a query.
   If relevant scope cannot be narrowed safely, attempt all discovered native
   items in that file/module within the declared budget; never select one by
   nearest name or line.

Deduplicate backend requests by workspace/capture/tool/selector/arguments, not
by lint name. Every reused query remains linked to all records it serves.
The scope router's historical strict union 328 local / 292 transverse is a
baseline for the supplied snapshot, not hard-coded selection.

## Native graph reuse and discovery

The parent supplies the actual catalogue and successful/negative payload
examples. Adapt those schemas only; this contract does not invent MCP return
keys, graph IDs, coordinate units or file spans.

Use existing indexed graph APIs, in this order of evidence needs:

- paginated `crate_dependency_metric` without `top_n` to enumerate crates,
  supplemented by `crate_edges` to establish graph
  scope; crate relations are context, not automatic file-level co-edit edges;
- `module_tree` to enumerate native qualified items, including private items
  where actually returned; preserve kind/identity/hierarchy;
- source-bound native item locations where available; targeted exact definition
  lookup or existing Serena file/tree/range adapters where required to bind
  native identities to diagnostic files;
- paginated `who_uses`, `calls_from`, and applicable `who_imports` queries for
  selected mapped/candidate items, collecting incoming usage, outgoing item
  dependencies and module imports without treating all entries as strict calls.

Catalogues or historical descriptions saying “public only” do not override a
current payload proving private items exist. Conversely, the reported 6,873
indexed items and visibility counts are not proof every source/test/feature is
covered. Verify actual return coverage and keep unknowns.

Crate identifiers must come from backend inventory or an independently validated
manifest/graph correspondence. If the backend cannot enumerate crates, a bounded
stdlib read of workspace/package manifests and literal member globs may supply
**candidate** crate selectors. Overrides/inheritance/indirection not handled by
that adapter remain explicit; do not write a Cargo resolver or infer positive
item identity from a directory name. No cargo metadata subprocess is required.

`build_codemap` may provide optional bounded neighborhoods only after its real
schema is verified. Its node/depth/incoming caps are **not** pagination and
cannot establish a complete graph export. It must not replace the complete
work queue or hide unexpanded transverse items. Prefer paginated native relation
queries for accounting; do not rebuild the backend to obtain a better API.

If module items lack locations, preserve them as unlocated native identities.
Definition/Serena evidence can establish selected locations. If a particular
kind or ambiguity cannot be resolved with existing read tools, retain candidate
file observations or unresolved endpoints. A zero result is not absence proof.
No backend Rust changes are included.

### Verified native hydration path and stale-snapshot handling

The parent's local `.tmp/full-inventory-discovery/` captures establish this
concrete route; they remain private, not published fixtures:

- `crate_dependency_metric` at limit 100 returned all 73 rows with
  `crate_name` and `item_count`. Follow its actual limit/offset/total metadata
  for larger inputs; omit optional `top_n`, which is not exhaustive pagination.
- `module_tree` without a depth cap returned recursive apparatus items including
  private functions/methods, names/kinds/visibility, but no native IDs or spans.
  A depth-one tree is insufficient enumeration. Record a tree's coverage/
  truncation limits rather than assuming it offers cursor pagination.
- `build_codemap` can hydrate enumerated qualified seeds into native IDs,
  qualified names, file paths, byte-pair spans, lines and a `snapshot_id`.
  Use depth zero for **node hydration only**, in explicit batches within the
  advertised 500-node bound. Its verified zero-depth result had no edges even
  for two known connected seeds. Never interpret that as no dependency.
- A depth-one sample contained five nodes/four edges, including private
  `uid_string` and `controller_owner`. Native Calls/Uses edges were oriented
  consumer → provider; preserve that orientation, not an assumed query direction.
  Per-target paginated `who_uses`/outgoing/import observations provide the main
  relation collection, or retain explicitly capped depth-one observations with
  unexpanded/truncation accounting. A private target with zero returned usages
  is still only a zero within the indexed query scope.

Automatically batch enumerated names, record seed-to-returned-node
correspondence and missing/ambiguous seeds. Similar test/library qualified names
must not be resolved by picking the first result. Generic identity comes from
native evidence and verified file/span correspondence, not another source-body
parser or a hard-coded package profile. Avoid rehydrating identical native
targets for each diagnostic.

The sample backend warned that its snapshot was approximately 16.8 days older
than the newest Rust file. Preserve that warning and snapshot identity on the
capture and inherited edges. It is a backend freshness heuristic, not proof
that every returned endpoint is stale. The parent checked all five sampled
byte spans/recorded lines against current files and found the declaration names
at those spans; those endpoint checks do not prove global graph freshness.

For each usable endpoint, record current file hash and source-check result
independently of backend freshness. Verify byte bounds, line consistency and
declaration/identity correspondence, not just a name anywhere in the file.
Passing checks permits current endpoint localization while relation coverage/
freshness remains partial or unknown. A warning alone must not globally discard
otherwise verified locations or block the whole exploratory representation.

If a span fails current projection, retain the native node/edge with its captured
snapshot, original file/span and an explicit failed-source-check reason.
Where a root-confined endpoint file still exists, it can be displayed as a
**backend-observed, unverified-current** candidate boundary; never mark it
`source_verified`, use it as exact diagnostic attribution, or union it as hard
co-edit. Unknown/nonexistent endpoint files stay in unresolved native endpoints.
Report these separately from source-verified candidate edges. Preserve all
native facts actually returned rather than laundering stale ones into current
facts or dropping them silently.

No refresh/rebuild is authorized by this warning. Continue with independently
supported current endpoints and explicit stale/unresolved coverage. Request a
separately scoped refresh decision only if no meaningful current projection is
possible and the real useful-output acceptance therefore cannot be met.

## Meaning of “dependencies found”

The default scope is indexed **direct incoming/outgoing dependencies of all
selected transverse diagnostic item/file scopes**, plus native crate/module
context. This is not a recursively exhaustive transitive graph of the entire
workspace. Record this scope prominently in JSON and report. Preserve all
dependencies actually returned, including outside-diagnostic consumer files;
deduplicate identities without discarding provenance.

Do not omit a returned edge because its endpoint has no diagnostic or cannot
be assigned a function. Do not certify a file edge if even its endpoint file
is unknown: retain the native edge in an unresolved-endpoint queue.
No transitive closure inferred from names, same lint, similarity or common crate.
Future recursive expansion is not required for this lot.

Every collection has explicit query/result budgets and a whole-operation
deadline, with documented defaults and optional CLI overrides. Exhaustion marks
the remaining work queue `not_attempted_budget`/`not_attempted_deadline`; it
never shrinks the inventory or silently certifies the current graph complete.
Ordinary successful acceptance must attempt every transverse record, even when
some attempts end unresolved rather than queried.

## Generic artifact and evidence qualification

Add a separate version-1 capture artifact:
`kind: "lint-native-dependency-capture"`. Do not overload the legacy
`clippy-origin-binding` or require the hard-coded `ORIGIN_TARGET`.
Required logical fields, normalized by A and validated by B:

- `workspace`, `inventory_sha256`, `captured_at`, `target_head`,
  `source_files` (root-relative path/hash and before/after verification);
- `backend` (server/catalogue references, declared workspace evidence,
  native graph scope/freshness/coverage limitations);
- `queries` (IDs, exact tools/arguments, raw artifact references/hashes,
  status, pagination counters and limitations);
- `items` (capture-local ID, native selector/identity, kind, optional path/range,
  location status `verified | candidate | unknown`, evidence references);
- `diagnostics` (namespaced key, route, item IDs, query IDs, attempt outcome,
  localization status and reasons);
- `dependencies` (ID, kind, native origin/destination item IDs or unresolved
  native endpoint records, optional bound endpoint files, evidence references,
  qualification `source_verified | backend_observed | unresolved`);
- `limits`, `timing`, `limitations`.

A/B freeze the exact field representation using parent's real schema fixtures
before integration; these logical fields are mandatory, but no extra general
adapter framework is required. B may reuse existing planner graph assembly and
report helpers through a small generic-input path; never bypass strict legacy
validators by filling invented origin proofs or converting unknowns to exact.

Current source-bound backend observations can enter an exploratory graph even
without historical diagnostic/source equivalence. Mark their diagnostic
attribution `candidate` or `stale` as appropriate. Exact current physical
diagnostic mapping still requires independent historical/fresh source binding
and verified coordinates. Missing historical binding is not a reason to suppress
otherwise valid current native dependency observations.

Distinguish positive **native identity** within one backend graph from speculative
cross-system identity. Generic file endpoints can rely on native ID/selector,
verified definition location/current source and captured backend relation
witnesses; no special crate-module-function profile is required.
Serena/HIR links still require positive file/range/declaration correspondence;
equal unqualified names alone never suffice.

Use hashed references to raw captures and source-only proof context. Final
capture/graph files are not hashed into inputs they themselves reference.
Recheck inputs/source files at publication and preserve drift as blocked/stale.
All real captures and source snippets remain local ignored data, not Git content.

## Output and partition view

Final JSON exposes inventory accounting, all record outcomes, source/backend
coverage, native items, dependency observations, unresolved endpoints and a
file `work_graph` using existing hard/candidate semantics:

- all diagnostic files, plus source-bound dependency endpoint files;
- candidate dependency edges with origin/query/symbol/file scope and provenance;
- qualified hard edges only from separately approved correction-specific
  constraints, if supplied through the existing planner path;
- tentative minimal groups relative to those hard constraints, with boundary
  candidate edges and unresolved review tasks.

The scope router creates no hard constraints. Backend dependency edges do not
create hard unions. No hard constraints can legitimately yield singleton
tentative groups, but the report must not call them independent or dispatchable.
Nodes with no observed edges say `not_observed`, not `independent`.
Keep scheduling metadata separate. The useful deliverable is complete inventory
representation plus observed coupling/risk, not a fabricated safe partition.

Report both retained-record and strict-union populations. Include monotonic
stage/total timings, backend request/page counts, cache/reuse counts, local
skips, transverse attempted/query-served/unresolved/stopped counts, all edge
qualification counts, item-kind/visibility coverage where actually known and
truncation/unexpanded totals. Query success, page completeness, source binding
and language/index completeness are separate dimensions.

## Acceptance and stopping boundary

Use existing unittest infrastructure and synthetic fixtures; no runtime harness
or new dependency. Test an arbitrary target package not named AIForAll and not
matching the legacy profile. Include private functions, impl methods, structs,
traits, modules, missing ranges and no-symbol findings; duplicate names,
unsupported macros/features/tests and missing native locations stay explicit.
Test pagination gaps/repeats/total drift, budget/deadline exhaustion, all records
accounted for, local skip without dropping nodes, query reuse, source drift,
wrong root, output aliases and candidates never causing hard unions.

Real acceptance uses a **fresh** output/artifact directory and the full supplied
1,046-record / 77-rule inventory. Verify totals against inputs, including strict
union 620 and raw Sonar keys 1,312 for this snapshot. Compute routes rather than
hard-code expected results. Every transverse record must have an attempted
terminal outcome; report actual query coverage, not promise all resolved.
Produce source-bound dependency observations beyond the previous single manual
origin, selected automatically from the inventory. Do not repeat a one-origin
sample and call it generalization. Validate representative incoming/outgoing
edges and outside-diagnostic endpoints against raw native evidence.

If existing APIs cannot positively bind a class of items, finish its explicit
unresolved queue and proceed with independent supported classes. If **no**
automatically selected transverse scope can yield meaningful dependency
observations, record the precise API/schema obstacle and stop without claiming
utility acceptance. A backend modification would require a separate scoped
decision, not a hidden rebuild or another taxonomy detour.

No new acquisition engine, cold-start Clippy/Sonar feature, automatic reviews,
source fixes or correction-agent dispatch is included. Existing uncommitted work
must remain intact; publication and review routing stay with the parent.
