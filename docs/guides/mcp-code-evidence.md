# Bounded MCP evidence collection

Offline planner/tests use Python 3.11+ stdlib. Live collection additionally
requires the exact `mcp==1.21.1` SDK from
`ops/scripts/requirements-mcp-code-evidence.txt` and caller-managed compatible
loopback servers. No service configuration/activation is performed here.

## Explicit target, independent tool checkout

`collect` and `produce` require `--workspace <absolute-target-git-top-level>`.
The target needs an existing full HEAD. It may be completely separate from this
tool checkout and at a different commit. Manifest/request directory fields
cannot authorize another root. Inputs, outputs and capture references for
`produce` remain inside the selected target. Run from the target or supply
absolute artifact paths; relative CLI paths are relative to the process CWD.

`catalog` is workspaceless metadata only:

```powershell
python -B ops/scripts/mcp-code-evidence.py catalog --output <catalog.json>
python -B ops/scripts/mcp-code-evidence.py collect --workspace <absolute-target-root> --requests <requests.json> --output <collected.json>
```

Request manifests contain `workspace` and a bounded `requests` list with unique
`id`, curated short `tool` and schema-checked `arguments`. The CLI is the root
authority. Tool listing alone proves no source or language coverage.
The `collect` envelope is not normalized planner evidence.

## Planner-ready production

Prepare a strict overlap inventory, explicit source/symbol/target plan and
independent source-binding proof as described in the
[IO contract](../contracts/io.md#producer-inputs). These preparation steps are
not automated by this extraction.

```powershell
python -B ops/scripts/mcp-code-evidence.py --timeout 300 produce --workspace <absolute-target-root> --inventory <inventory.json> --plan <capture-plan.json> --binding <binding.json> --snapshot <snapshot.json> --output <evidence.json> --artifacts <new-capture-directory> --serena-url "http://127.0.0.1:3062/mcp?tags=serena" --max-queries 128 --max-sources 256 --max-pages 8 --page-size 50 --allow-partial
```

`--url` and `--timeout` are global flags placed before the subcommand. Only
validated loopback URLs are accepted; proxy inheritance and redirects are
disabled. Queries are curated, bounded and sequential. Serena's reported root
must match the target and its language server must be ready. Display project
names are not hardcoded. Unsupported/missing root reporting fails closed,
without activating a project.

`--context <file>` may be repeated for mapping context and policy/review text.
Use `--allow-partial` only to retain explicitly partial/error/unsupported
observations, never to declare reference closure. Newly discovered destinations
can be queued without gaining pre-query source stability.

## Optional observations

`produce --observations <output.json>` captures one file observation per usage
row. It currently supports only the **AIForAll-specific compatibility profile**
`direct_crate_module_function_v1` for
`apparatus_contracts::runtime::validate_runtime_uid`. That origin's Cargo/default
library/unconditional module/signature/definition/Serena chain must agree.
This is not a generic Rust resolver or a live positive-origin facility for an
arbitrary workspace. Omit observations for generic normalized evidence capture.

The producer-only exact definition lookup has a narrow plain-text decoder;
`collect` is not expanded into arbitrary definition pass-through. Origin proofs
are bound before snapshot finalization. Observations hash finalized
snapshot/evidence/inventory; their own hash never enters the snapshot.

Stable prehashed destination + positive origin + matching spelling/span can be
a soft `file_candidate`. Mismatches and late sources remain unresolved/path-only;
missing caller fields do not invent consumer identities. Contexts are not
dependency edges. Partial or complete pagination does not establish complete
Rust/index/feature/private-item coverage.

All outputs are checked against inputs, sources, other outputs and raw-artifact
descendants before transport and publication, including discovered aliases.
Hashes are rechecked. Replacements are per-file atomic, not a multi-file
transaction: mixed generations must be rejected by consumers. Raw artifacts may
remain after failure for local diagnosis; do not publish them by default.

```powershell
python -B -m unittest discover -s ops/tests -p test_mcp_code_evidence.py
```

Tests mock every service and use owned temporary Git repositories. No live
server, application source, global configuration or private capture is needed.

## Generic native capture API (version 1)

The full-inventory command imports this module rather than creating a second SDK
client. Its asynchronous entry point is frozen as:

```python
async def collect_native_dependencies(
    workspace, inventory_path, artifacts, *,
    url=DEFAULT_URL, timeout=1800, max_queries=20000, max_pages=128,
    page_size=100, hydration_batch_size=400, max_items=100000,
    max_dependencies=500000, protected_paths=(),
):
    ...
```

Paths are `Path`-compatible; workspace must be an explicit absolute target Git
top-level. `artifacts` must be an explicitly supplied new run directory, which
may be outside the target. The function
returns a JSON-compatible `lint-native-dependency-capture` and writes
`native-capture.json` plus raw query/catalogue captures inside that directory.
`protected_paths` supplies final graph/report and other inputs so discovery
cannot overwrite their filesystem aliases. Fatal authority/collision/integrity
errors raise `EvidenceError`; ordinary backend failures/budgets/deadline produce
a partial capture with terminal outcomes for every diagnostic.

`ops/tests/fixtures/native_dependency_capture.json` freezes the wire-independent
consumer representation. Top-level fields are `schema_version`, `kind`, `status`,
`workspace`, `inventory_sha256`, `captured_at`, `target_head`, `source_files`,
`artifact_root`, `orientation`, `backend`, `queries`, `items`, `diagnostics`, `dependencies`, `limits`, `timing`
and `limitations`. Unknown IDs, files, spans and hashes are null, never invented.
Query evidence references are capture-local query IDs; queries carry the
run-artifact-root-relative raw artifact/hash. The caller must authorize the
artifact root independently of captured JSON; it never authorizes source paths.
`orientation` is the literal `consumer_to_provider`. Backend `server_ref` and
`catalogue_ref` carry `{path, sha256}`; `context_refs` links query IDs.
Source records use captured `sha256`, `before_sha256`,
`after_sha256` and `status` (`verified`, `changed` or `missing`).

Items have native selector/ID/kind/visibility, optional current path/byte range,
source hash, snapshot, location status, original native location, evidence refs
and reasons. Ranges use zero-based UTF-8 byte offsets and one-based lines.
Diagnostics retain namespaced keys, route, files, item/query IDs, terminal
attempt outcome, localization status and reasons. Dependencies retain native
origin/destination records, nullable item/file endpoints, original row,
evidence refs and qualification (`source_verified`, `backend_observed`,
`unresolved`). Arrows in this native capture are **consumer → provider**,
not the legacy observation impact direction. Candidate dependencies never
authorize hard unions. The example fixture is invented, not a private capture.

### Generic collection scope and qualification

The adapter loads the existing `diagnostic-scope.py` policy without modifying
its taxonomy. All source records remain in `diagnostics`; local records end
`skipped_local`. Every transverse record ends `queried`, `reused_query`,
`unresolved_localization`, `unavailable_backend`, `source_invalid`,
`not_attempted_budget` or `not_attempted_deadline`. Empty pages are not absence
proofs. This API does not authorize historical source equivalence, so all
positively file-bound items are retained as candidates even when an old
diagnostic line happens to overlap a current item. Missing ranges do not hide
records. There is no first-item, top-N or manual seed selection.

Crate metric pages enumerate names without `top_n`; recursive module trees
enumerate native names/kinds/visibility. Explicit batches of at most 500 names
are hydrated at depth zero with the advertised node cap. Missing and ambiguous
native identities stay explicit. Depth-zero empty edge lists do not mean no
dependencies. All selected scopes use paged incoming usage, outgoing function
dependencies and importer queries. Non-function `calls_from` is explicitly
inapplicable; errors on other selected kinds do not abort the rest of the queue.
Outgoing `call_sites` categories are retained, not all declared strict calls.

Hydration uses the canonical `build_codemap` arguments
`seed_qualified_names`, `depth: 0`, `max_nodes: 500`,
`embedding_policy: "no_rerank"`, `format: "json"` and
`include_snippets: false`, alongside the explicit target `directory`.
`module_tree` uses `krate` with no depth cap. Unknown argument names remain
rejected against the advertised catalogue before transmission. The single
`crate_edges` page uses explicit offset/limit/summary and is marked partial
context, not global crate-edge coverage; it does not replace accounting for
every selected item relation sequence.

Import bindings have no source spans: only a positively hydrated `from_module`
may supply an importer file. No directory/module-name inference is used.
Repeated rows, wrong offsets, non-progress and changing totals mark a sequence
incomplete. Raw malformed-page facts remain captured and cannot become
source-verified normalized dependencies through that failed page.

Generic current projection reuses the shared lexer/declaration scanner without
changing it. Byte bounds, UTF-8 boundaries, recorded line, item kind and exact
declaration/header correspondence must agree. This supports bounded function,
method, type, trait and explicit module declarations; unsupported forms remain
candidate/unlocated native facts. Native IDs are scoped by backend snapshot.
Duplicate selectors are not resolved by choosing the first ID.

Source hashes are rechecked after collection. Current node projection and
historical diagnostic attribution are separate: missing historical binding
leaves attribution candidate, without suppressing valid current observations.
Sources first discovered after relation queries cannot gain pre-query stability.
Failed current spans with known endpoint files remain `backend_observed`;
unknown endpoint files stay `unresolved`. Backend age warnings and snapshot IDs
are preserved independently, not used to globally discard current checks.
Dependencies inherit capture warnings and expose their endpoint `snapshot_ids`.

The SDK connection and all sessions use existing transport code. No activation,
index rebuild, cache purge, Cargo command, semantic search, embedding model or
legacy origin profile is used by this generic API. Native payloads do not
independently report their index root; `backend.workspace_evidence` explicitly
says `requested_directory_only`, never “verified backend root”.

Default limits are a 1,800-second whole-operation deadline, 20,000 query records,
128 pages per sequence, 100 rows per page, 400 names per hydration batch,
100,000 items and 500,000 dependency observations. A final received page is
retained in full rather than truncated to hide over-budget rows. Source guards
retain the existing 8 MiB per-file and 128 MiB aggregate bounds.
`timing` uses monotonic stage/total seconds and distinguishes actual tool
requests, query records, cache hits and shared diagnostic query assignments.

The function writes a fresh `run-manifest.json` immediately and a final or
partial `native-capture.json`. Raw hashes and source/input/output aliases are
rechecked before publication. Source drift remains source-invalid evidence;
input/raw-capture drift or output/source collision is fatal, with failed-run
evidence retained when the artifact root is still safe. No accepted final graph
is written by this adapter; that is the final command's responsibility.
The inventory is read once into a bounded buffer (64 MiB maximum), strictly
parsed with duplicate-key/non-finite rejection, and hashed from those exact
bytes. Its initial digest is passed into run state rather than reread from the
mutable path. The final on-disk drift check remains mandatory.
