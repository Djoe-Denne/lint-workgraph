# IO and evidence invariants

This is the standalone pipeline contract, not a full Rust resolver specification.
Executable validators and negative fixtures in `ops/tests` define the exact
accepted structures. All generated evidence is local review material, not an
authorization to correct sources, dispatch agents or certify independence.

## Pipeline and callers' responsibilities

1. `github-lint-inventory.py` inventories supplied issue pages or explicit GitHub
   GET results. Issue metadata is not the diagnostic overlap inventory.
2. `clippy-sonar-overlap.py` consumes successful Cargo diagnostic JSONL lanes and
   a complete saved Sonar issue page set, producing inventory schema version 1.
3. `mcp-code-evidence.py produce` consumes that inventory, an explicit capture
   plan and optional source binding/context. It emits source snapshot, normalized
   evidence and optionally file observations.
4. `clippy-constraint-plan.py` independently validates supplied local inputs and
   produces a conservative plan/graph and optional Markdown report.

The caller must obtain the diagnostics and prepare the capture plan,
inventory/source equivalence, selected source list and any independent review
proofs. Durable cold-start acquisition/binding orchestration is not delivered.
The [offline example](../../examples/README.md) uses invented test data instead.

## Workspace authority and paths

`TOOL_ROOT` identifies this tool checkout, never an implicit Rust source root.
`collect` and `produce` require explicit absolute `--workspace` selecting an
existing target Git top-level with a full HEAD. The only collector child
process is a bounded read-only `git rev-parse --show-toplevel` check. Subsequent
HEAD reads use target Git metadata. Tool and target commits may differ.
Producer metadata records adapter identity and tool/scanner hashes separately.

A request manifest cannot grant a different root: its `workspace` and every
request `directory` must resolve to the CLI root. Curated producer directory
arguments use that root, including fixed origin queries. `catalog` records
`workspace: null`; listing tools establishes no source coverage.

Producer inputs, context/capture references and outputs remain under the target
root, not under the tool checkout. Capture/proof references use root-relative
paths and SHA-256 of exact bytes; moving an artifact without rebinding invalidates
it. Traversal, outside-root paths, case ambiguity and filesystem aliases are not
ways to gain source authority. Output files cannot overwrite sources, inputs or
one another, including discovered sources and filesystem aliases. Accepted
outputs cannot be descendants of the fresh raw-artifact directory.

Serena initial instructions must report exactly one absolute source root in
the supported `The project with name '…' at … is activated.` text format.
That resolved root must match the selected workspace; the current configuration
must independently report `Language server status: ready`. Project display
names do not select or authorize roots. Missing/unsupported root formats fail
closed. No activation, indexing or service reconfiguration is performed.

## Diagnostic identities

Inventory fields include `schema_version`, `clippy`, `sonar`, `matches`,
`ambiguous_exact_matches`, `unmerged_hints`, unmatched ID lists, `counts`,
`coverage_percent`, `source_stats` and `limitations`. All accounting is rechecked.
An exact alias requires compatible normalized rule, full physical primary span
and message, with unique endpoints. Only `external_clippy:` is translated into
`clippy::`; native Sonar rules are not assumed synonymous.

Only path separators are normalized in overlap identity. Different messages,
ranges, multiple primary spans or ambiguous matches are retained, not merged
by proximity or spelling. Strict union is Clippy unique records plus Sonar
unique sites minus exact alias pairs, **not** a semantic defect count.
Unknown mappings and unmatched diagnostics remain records and file nodes.

## Producer inputs

The explicit plan has `schema_version: 1`, `source_files: [relative path, …]`,
optional `symbols: [{path, name_path}, …]`, optional qualified `targets`, and
optional `configuration`. It is a bounded seed list, not arbitrary tool calls.

Independent binding has `inventory_sha256`, target `head`, `method`
(`fresh_capture` or `independent_equivalence`), `files: [{path, sha256}, …]`
and nonempty `evidence_refs: [{path, sha256, locator}, …]`. Current source bytes
alone do not establish historical diagnostic equivalence. Missing binding
cannot silently produce exact physical mappings. Optional JSON mapping context
binds `diagnostic_key`, `source_sha256` and `inventory_column_unit`; see the
synthetic producer fixtures for complete examples. `--context` also binds
explicit policy/review text. Source-equivalence inputs remain explicit and hashed.

## Snapshot, evidence and queries

All normalized artifacts use `schema_version: 1` and an explicit `kind`.
`clippy-source-snapshot` has `workspace`, target `head`, `captured_at`,
`files: [{path, sha256}, …]`, `inputs: [{role, path, sha256}, …]`,
`configuration`, `source_binding` and `limitations`.
`clippy-code-evidence` binds workspace, inventory/snapshot hashes, producer
metadata, mappings, relations, queries and limitations.

Each query retains ID, exact tool, arguments, raw artifact path/hash, status,
pagination and separate language/index coverage. Pagination completion proves
only the captured indexed query scope. Private items, macros, traits, features,
tests and freshness are not proved by empty results or a completed page list.
Partial/error/unsupported sequences remain explicit. `--allow-partial` allows
export of such evidence, not promotion into complete closure.

Transport is direct SDK `mcp==1.21.1`, loopback-only, bounded, without ambient
proxies or redirects. Curated tool/schema checks are not arbitrary pass-through.
Raw captures may contain sensitive data and must not be published by default.

## Physical localization and scanner limits

Exact mappings require independent source binding, stable source hashes and
replayable `clippy-localization-proof` inputs. Proof summaries/true booleans
alone are insufficient: the planner replays source and query witnesses.
Ranges are explicit about coordinate units and normalization; no offset repair.

The shared scanner recognizes a bounded lexical subset, not arbitrary Rust.
It keeps macro token trees/comments/literals opaque, excludes nested items and
bodyless foreign declarations, and checks every relevant source ancestor with
ordered trait/self roles. Invented parents and reversed impl roles fail closed.
Closures/async attribution and unsupported identities remain unresolved.

Inner attributes attach to nearest lexical scope; selected items and relevant
ancestors are checked without rejecting unrelated nested scopes. The only
non-rewriting attribute subset is a fully parsed inner or outer
`allow|warn|deny|forbid(lint, …)` with at least one ASCII identifier, optional
`clippy::`/`rustdoc::` prefix and optional trailing comma. `cfg`, `cfg_attr`,
unknown attributes, comments inside this grammar, raw identifiers, nested lists,
extra arguments, `reason` and `expect` remain unsupported. This physical
attribution predicate does not approve lint suppression or corrections.

## Origin profile and observations

`direct_crate_module_function_v1` is an **AIForAll-specific compatibility
limitation**, not a general resolver. The only live positive origin target is
`apparatus_contracts::runtime::validate_runtime_uid`, in
`crates/apparatus-contracts/src/runtime.rs`, with the default package/library and
literal unconditional `pub mod runtime;` in `src/lib.rs`. The manifest, module
root, fixed qualified signature, literal exact definition and current Serena
declaration range must all agree. Overrides, cfg/path indirection and unsupported
syntax cannot be guessed. Synthetic fixtures implement only the layout and
signature contract, not the source application's business implementation.
Generic offline planning still accepts schema-valid supplied evidence; live
origin generation has not been generalized to arbitrary projects.

`clippy-origin-binding` binds target, source path/hash, declaration range,
crate manifest/module root refs, query IDs and method. It contains no self,
snapshot or evidence hash and no approval flag.
`clippy-file-observations` binds workspace, snapshot/evidence/inventory hashes,
observations and limitations. Each usage row gets a distinct observation with
ID, kind, origin/destination path/hash and nullable symbol/range, query IDs,
origin binding ref, identity/endpoint status, relationship scope and reasons.

Only positive origin binding plus a stable prehashed destination and matching
spelling/span witness permits `file_candidate` / `source_verified`. Consumer
IDs/ranges remain null without independent identity proof. Missing
`consumer_function` does not fabricate a caller. Late sources and mismatched
spans remain `unresolved` / `path_only`. Context files are not dependency edges.

Artifact order is acyclic: raw queries + sources/context + origin proof →
snapshot → evidence → optional observations → plan. Observations are **not**
hashed back into snapshot inputs. Per-file atomic replacement is not a
multi-file transaction: consumers must reject mixed-generation hash mismatches.

## Existing policy

This section replaces the private policy-file location without granting new
correction authority. Its snapshot-bound location is
`docs/contracts/io.md#Existing policy`. The caller must bind an unchanged copy
as a context under the target workspace. An alternative accepted decision must
be under `docs/guides/clippy-decisions/`, identify its exact section, contain
`Accepted` and not `Proposed`, and be snapshot-bound.

The existing literal/local rule hints are `doc_markdown`, `missing_errors_doc`,
`missing_panics_doc`, `uninlined_format_args`, `needless_raw_string_hashes` and
`unreadable_literal`. They are conditional classification precedents, not
rule-wide locality, approval or exemptions from source/query checks.
Only approved, evidence-qualified `must_coedit` constraints with matching bound
review approval, complete relevant scope and query closure create hard unions.
Candidate/unqualified constraints stay review material. Multiple approved hard
constraints compose transitively; soft edges never force unions.

## Work graph and publication

The planner retains diagnostic and outside-diagnostic consumer files as nodes,
hard/candidate edges separately, unresolved observations and tentative groups.
Candidate arrows run provider/declaration → observed consumer (impact), not
`depends_on`. Same-file loops are not cross-file boundaries. Absent edges mean
`not_observed`, not independent. Unknown mappings remain attached to nodes.

Plan/report publication protects CLI inputs, referenced captures and sources
and rechecks hashes immediately before replacement. The offline planner checks
HEAD format, not live Git truth; review time/freshness remain caller concerns.
It performs no network, discovery, corrective edit or dispatch. Neither a plan
nor an approved fixture certifies complete Rust dependency closure, fixed worker
counts, globally safe concurrency or completion of the cold-start pipeline.

No project license has been selected; public availability alone is not a
permissive license grant.
