# Full-inventory dependency graph command

`ops/scripts/lint-workgraph.py` is the final command after diagnostic acquisition
and overlap generation. It processes the entire supplied overlap inventory,
automatically collects native graph scopes through the existing collector, and
exports a file ownership/review graph. No manual seed, selected validator,
source-file plan, legacy origin profile, fresh Clippy acquisition, correction
agent or dispatch step is required.

## Run

Use the existing collector environment and its pinned
`ops/scripts/requirements-mcp-code-evidence.txt`; the command does not install
dependencies or create another SDK client. Output parent directories must exist.

```powershell
python -B ops/scripts/lint-workgraph.py `
  --workspace "C:\src\arbitrary-rust-project" `
  --inventory ".tmp\overlap.json" `
  --output ".tmp\full-inventory-001.json" `
  --report ".tmp\full-inventory-001.md"
```

For a different authorized loopback endpoint, add:

```text
--url http://127.0.0.1:3062/mcp?tags=rust-code-mcp
```

The explicit absolute target Git root is the workspace authority. It is not
the tool checkout, the shell directory, the captured artifact's workspace, or
the inventory's origin directory. Tool and target commits may differ. The
target remains read-only; Git root validation is the existing read-only
collector check, not Cargo or a repository mutation.

By default the new run directory is adjacent to the JSON:
`.tmp/full-inventory-001.artifacts`. The command prints it on completion.
It must not already exist. To repeat a run while atomically replacing a previous
graph/report, supply a fresh directory:

```text
--artifacts .tmp/full-inventory-002.artifacts
```

The run directory must not contain the workspace, input inventory or either
output. Sources, inputs and raw artifacts cannot be output aliases. Existing
JSON/report destinations are replaceable only when recognized as previous
outputs of this command; unrelated files are not overwritten.

Keep real inventories, captures and reports local/ignored. They may contain
private identifiers, paths and backend evidence. Synthetic tests are not a
replacement for a parent-owned real full-inventory run and representative review.

## What the command does

1. Strictly parse and hash one bounded immutable inventory byte buffer. Compute
   routes with the existing `diagnostic-scope.py` policy and validate exact-alias
   identities/provenance. Retain every Clippy/Sonar record, source key, hint and
   ambiguous alias; strict union is not a semantic defect count.
2. Call `collect_native_dependencies()` once with that full inventory and the
   exact protected output paths. The collector owns the existing SDK connection,
   native enumeration/hydration, request deduplication, incoming/outgoing/import
   queries, raw captures, deadline and session cleanup.
3. Validate the returned version-1 native capture against the caller-owned
   workspace, inventory digest and fresh artifact root. Validate raw/catalogue
   references, request roots/schema keys, IDs and per-record routes/outcomes.
   Parse raw evidence and identify its hash from the same bytes.
   Corpus alias checks index resolved paths and device/inode identities once per
   file; they reject raw/source and raw/raw aliases without pairwise filesystem
   comparisons across the entire capture.
4. Independently replay current native declaration/header correspondence using
   the collector's shared source validator: native snapshot/ID/selector/file
   witnesses, byte bounds, UTF-8, lines and current hashes must agree. No second
   Rust lexer/resolver or origin profile is introduced.
5. Preserve each returned dependency. Positively bound files become candidate
   edges; unknown endpoint files remain in the unresolved native-endpoint queue.
   Current-source-verified and backend-observed/unverified-current observations
   are counted and labeled separately. A producer qualification flag alone is
   insufficient.
6. Assemble all diagnostic-file nodes, including local routes, missing coordinates
   and unresolved paths, plus returned dependency endpoint files outside the
   inventory. Mere whole-workspace node hydration does not add unrelated files
   as requested dependency scopes.
7. Recheck inventory, capture, raw and source bytes before publication. Replace
   the final JSON and Markdown atomically per file. Retain owned run evidence
   and an error manifest on failures when the artifact authority remains safe.

There is no switch that quietly samples diagnostics. Local routes skip dedicated
dependency lookup for that route; they are not source-local correction approval.
A local diagnostic's file can still be a native dependency endpoint discovered
for a transverse scope. Every transverse record has a terminal outcome:
`queried`, `reused_query`, `unresolved_localization`, `unavailable_backend`,
`source_invalid`, `not_attempted_budget`, or `not_attempted_deadline`.

## Dependency and partition meaning

The scope is **direct indexed incoming/outgoing/import observations for selected
transverse diagnostic item/file scopes**. It is not recursively exhaustive
whole-workspace dependency closure. Depth-zero native node hydration is not a
zero-dependency proof. Private methods, structs, traits and modules remain native
facts even when their current location or applicable relation tool is unresolved.

Arrows are native **consumer → provider**, not the legacy provider → observed
consumer impact arrows. They express observed boundary coupling, not task
execution order. A cyclic or self-referential native graph is not an instruction
to schedule workers topologically.

`work_graph.edges` contains only `candidate_dependency` edges. Matching file pair,
kind and qualification observations may share a coupling edge; `dependency_ids`
and query references retain every contributing native observation. Counts
distinguish raw dependency observations, candidate file edges and unique
cross-file boundaries. Same-file loops are not cross-file boundaries.

No generic dependency creates a hard union. `proposed_groups` are singleton
file ownership proposals, minimal relative to the empty set of approved hard
constraints on this path. All have `review_required` readiness, boundary-review
IDs and unresolved tasks. They are not independent, dispatchable or a fixed
worker count. Separately approved correction-specific hard constraints still
use the existing strict planner path; this command does not fabricate them.

No observed edge means `not_observed`, not `independent`. Query success,
count-complete pagination, native identity, current source projection, historical
diagnostic attribution and language/index completeness remain separate.

In particular, a backend snapshot-age warning does not automatically invalidate
every current endpoint. Valid current byte/declaration checks can remain useful,
while inherited snapshot IDs and freshness warnings stay visible. Failed source
projection with known root-confined endpoint files can remain
`backend_observed`; it cannot become `source_verified` or exact diagnostic
attribution. Unknown endpoint files are not guessed from module names or folders.
Generic diagnostic localization stays candidate/unknown without independently
supported historical equivalence; an unqualified `exact` claim is not promoted.
No refresh, indexing, cache purge, activation or backend configuration change is
performed.

## Output and attempt accounting

The JSON retains the original inventory, full native capture, normalized
per-record outcomes, consumer source/item checks and dependency qualifications.
Raw dependency rows, selectors/IDs, snapshot identities and query references
remain inspectable even for unresolved endpoints. References to raw files are
relative to the independently authorized run-artifact directory, not source-root
authority.

The report shows record and strict-union populations, raw Sonar key routes,
local skips, transverse attempted/query-served/unresolved/stopped counts, native
kind/visibility coverage, query records and received semantic pages, shared
query assignments, qualification counts and boundary review tasks.
Stopped records can already have partial successful queries; that overlap is
reported explicitly rather than making unresolved counts negative. Unknown
unexpanded index totals stay unknown; limits, known stopped records and unlocated
item counts remain explicit.

Monotonic command timings cover preflight, collection, validation, assembly and
publication. The graph records timings through publication preparation and the
collector's stage/request/cache timings. **Completed publication and total
durations** are in `command-manifest.json` inside the run directory; a file cannot
truthfully contain the measured duration of its own future replacement.
`native-capture.json`, the collector's `run-manifest.json`, raw responses and
catalogue/server evidence stay there as well.

## Limits and exit codes

Defaults reuse the collector:

- `--timeout 1800`: finite collection operation deadline, including sessions.
- `--max-queries 20000`, `--max-pages 128`, `--page-size 100`.
- `--hydration-batch-size 400`, `--max-items 100000`,
  `--max-dependencies 500000`.

Increase an explicitly exhausted bound for a later fresh run if appropriate;
there is no hidden automatic retry or recursive expansion. The final received
page is retained rather than truncated to disguise exhaustion.

- **0:** published an exploratory representation with candidate file coupling,
  or an all-local inventory. Inspect `status`: partial unsupported coverage can
  still be useful, but is not a complete/fresh graph claim.
- **2:** fatal authority, integrity, malformed-input or publication failure.
  Do not treat a previous output as the new run's successful result.
- **3:** published partial representation with budget/deadline-unattempted
  transverse records. Every input record remains represented.
- **4:** transverse work exists but no usable file candidate edge was obtained.
  The graph/report and unresolved native facts are saved; useful-output
  acceptance is not claimed.

The collector owns failures before its API returns and retains its own failure
manifest/capture. After return, command failures record `command-manifest.json`
when safe. No cleanup deletes that evidence. JSON and Markdown replacements are
individually atomic, not a two-file filesystem transaction; a second replacement
failure can leave a new graph and an old report, with nonzero exit status.

## Fixture verification

```powershell
python -S -B -m unittest discover -s ops/tests -p test_lint_workgraph.py -q
```

Tests mock the one asynchronous collector call and use valid hashed synthetic
captures for an unrelated target package, with tool/target roots and commits
distinct. They exercise routing/accounting, private and other native kinds,
incoming/outgoing/import directions, unknown endpoints, query reuse, raw
pagination failures, source projection/drift, root and hash authority, aliases,
read/parse/hash replacement races, stopped records and atomic failure handling.
They do not call a live backend, run Cargo or establish real full-inventory
acceptance.

## Observed real-data verification

The complete saved inventory was exercised through the actual native collector
and the final command's validation/assembly/report functions, reusing the
completed capture rather than making a second live collection. It retained
1,046 records, 1,312 Sonar source keys and strict union 620. All 462 transverse
source records were attempted: 336 query-served and 126 unlocalized.

The resulting graph contains 256 files, 517 candidate file edges and 289 unique
cross-file boundaries from 9,348 native observations. No consumer validation
issues or unattempted records remained. Coverage is still partial.
Successful measured stages were 110.93 seconds for collection and 144.27 seconds
for subsequent validation, assembly and publication. These are not a timing
measurement of a second unified CLI invocation.

The parent reran all 257 offline tests after the real-data scaling correction.
Actual inventories, source captures, graph and report remain local/ignored.
