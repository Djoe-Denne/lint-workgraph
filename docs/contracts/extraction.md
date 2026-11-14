# lint-workgraph — bounded public extraction contract

Status: authorized extraction contract, 2026-11-14. This file governs the new
project only; it does not replace AIForAll rules or authorize source deletions.

## Decisions and provenance

- Destination: a new independent repository, `lint-workgraph`, under the user's
  repositories directory. Intended public remote: `Djoe-Denne/lint-workgraph`.
- Source baseline: AIForAll commit
  `c4bba486291edd63dabafd5b5235c2d1ba628fa0`. Preserve existing source copies.
- Extract the delivered Python analysis pipeline, not private application code,
  repository history, campaign captures or the surrounding agent infrastructure.
- Preserve `ops/scripts` and `ops/tests` layout. Make target-workspace selection
  explicit without loosening read-only tool/root safeguards.
- No new ADR is necessary: this is the explicitly authorized repository boundary
  and a reversible packaging change, not new business architecture.
- The source delivery reported 148 fixture tests, 23 exact mappings, 132 graph
  nodes and five candidate boundaries. These are historical source-run results,
  not fresh validation or generic completeness claims for this extracted repo.

## 1. Owned deliverables and exclusions

Implementation scope in the new repository:

```text
ops/scripts/github-lint-inventory.py
ops/scripts/clippy-sonar-overlap.py
ops/scripts/clippy_source_ranges.py
ops/scripts/mcp-code-evidence.py
ops/scripts/clippy-constraint-plan.py
ops/scripts/requirements-mcp-code-evidence.txt
ops/tests/test_github_lint_inventory.py
ops/tests/test_clippy_sonar_overlap.py
ops/tests/test_clippy_source_ranges.py
ops/tests/test_mcp_code_evidence.py
ops/tests/test_clippy_constraint_plan.py
ops/tests/fixtures/                 # curated synthetic inputs only, if required
docs/guides/                       # five corresponding English tool guides
docs/contracts/                    # this contract and necessary curated IO rules
README.md
.gitignore
obsidian/                          # new text-only vault described below
```

Copy only fixtures actually needed by these tests. Keep the SDK requirement
`mcp==1.21.1`; no dependency upgrade, new parser, package framework or runtime
harness. Python stdlib remains sufficient for offline planner/fixture tests.
Do not copy unrelated scripts or recursively copy source directories.

The architect owns only this contract. The parent assigns one exclusive owner
for shared scanner/adapter code and file-disjoint documentation ownership;
do not let multiple authors independently modify the shared scanner. Use direct
workers under the user's existing Sol medium constraint, no Ensemble or new
worktrees. This contract does not dispatch workers.

Never export `.tmp`, cached real outputs, raw MCP captures, logs, credentials,
private Rust/application sources, source Git history, source Obsidian content or
manifest, global/project `AGENTS.md`, agent instructions, personal configuration,
absolute home paths, session IDs, environment dumps or generated vault state.
The new repository gets its own minimal ignore rules, not inherited policy.

Tests/examples must use synthetic semantic equivalents. Replace any embedded
copy of the actual C102 function with an invented function preserving the lexical
discriminants (comments, strings, closures, macro token trees and header range).
Preserve the real bug-regression semantics, not private source spelling. Audit
embedded multiline strings as well as fixture files. Author, organization,
private-repository and absolute-path literals must not leak incidentally.
The explicitly documented source baseline and narrowly named compatibility
profile below are intentional provenance, not permission to export their source.

## 2. Explicit target workspace; tool checkout is not source checkout

Separate `TOOL_ROOT` (these scripts/tests/docs) from the selected Rust
`workspace`. The latter is the only authority for source reads, manifests,
relative source/capture references and source Git identity.

For source-bearing `collect` and `produce`, require an explicit CLI
`--workspace <absolute-target-root>`; do not let a manifest select a new root
and do not silently default to the tool checkout. `catalog` may remain
workspace-independent because listing tools alone proves no source root.
Remove personal `CANONICAL_WORKSPACE` constants and the project-name equality
assumption `Active project: AIForAll`.

Resolve/validate the CLI root once, require it to be the intended Git top-level
root, and compare all manifest `workspace`/request `directory` values against
that resolved root. Keep existing out-of-root/alias/input-output checks.
Do not relax path validation to make extraction fixtures pass. No arbitrary
directories, tool names or selectors gain authority from input JSON.

SDK sessions remain direct and independent of OpenCode, with curated read-only
allowlists, bounded queries/timeouts, loopback URL validation, no ambient proxy,
no redirects and owned client-session cleanup. Preserve observed schema checks,
semantic pagination accounting, partial/error handling and root confinement.
No activate_project, rebuild, cache clearing or shared-server reconfiguration.

Serena must run initial instructions and verify that its **reported source
root** equals the selected workspace and its language server is ready.
The display project name is not a root identity check. Adapt only verified
reported-root formats; if configuration does not expose a reliable root, fail
closed with an actionable limitation. Do not infer root identity from readiness,
name, requested argument or the presence of a file alone.

Source HEAD/binding checks compare to `git_head(workspace)`, not
`git_head(TOOL_ROOT)`. Record tool version/source provenance separately.
Never require tool and Rust repositories to share a commit. Retain source
hashes and before/after source checks: target HEAD alone does not prove a dirty
tree or historical captures equivalent. Snapshot evidence and historical source
equivalence remain explicit caller-provided, verified inputs.

Existing relative capture references remain confined to the selected source
workspace; extraction does not silently redesign storage or permit external
capture references. Clearly document this limitation. Test external temporary
target fixtures independently of the tool checkout.

## 3. IO, graph semantics and compatibility scope

Preserve the delivered strict overlap identity, normalized evidence/proof
schemas, semantic-pagination rules, range-local scanner and graph behavior.
Carry only the necessary IO/invariant passages into an English standalone
contract/guide; remove links requiring the private source checkout and do not
publish the whole historical mission contract.

Physical mapping is not reference closure. Candidate file/symbol dependencies
remain soft observations; only approved, evidence-qualified must-coedit
constraints create hard unions. Unknown mappings remain nodes and review tasks.
No fixed worker count, forced pairs, rule-only locality, inferred independence
from missing edges, corrective edits or dispatch.

Keep the source-specific
`direct_crate_module_function_v1` origin profile clearly labeled an
**AIForAll-specific compatibility limitation**, including its
`apparatus_contracts::runtime::validate_runtime_uid` target. Do not generalize it
into a purported Rust resolver during extraction. Explain that generic offline
planning works with schema-valid supplied evidence, but live positive origin
binding currently supports that narrow profile only. Synthetic fixtures may
exercise its expected package/module layout without publishing application
implementation. No live origin validation against the private project is
required for this packaging acceptance.

Preserve the acyclic artifact order: raw captures/context/origin proof,
snapshot, normalized evidence, optional observations, plan. Observation files
reference snapshot/evidence hashes but are not hashed back into snapshot inputs.
The planner protects them as separate CLI inputs and rechecks before publishing.

## 4. Honest documentation and new Obsidian vault

Create `obsidian/` as a new local Markdown vault, not a copy/import of AIForAll.
Do not modify global Obsidian/QMD configuration, register indexes, invoke plugins
or publish application/cache state. A linked Markdown folder openable as a vault
is sufficient; no `.obsidian` configuration is required.

Minimal linked notes:

- `obsidian/index.md`: navigation and project purpose;
- `obsidian/history.md`: authorized extraction, baseline, actual validations and
  publication reference after the parent verifies it;
- `obsidian/architecture.md`: diagnostic → localization/evidence → candidate
  graph → qualified hard constraints → tentative work groups;
- `obsidian/limitations.md`: language/index/identity/coverage boundaries,
  source-specific origin profile, no automatic safety/dispatch certification;
- `obsidian/backlog.md`: remaining bounded work, including license choice;
- `obsidian/reproduction-gap.md`: cold-start inputs not yet durably generated;
- `obsidian/provenance.md`: curated source/tool provenance and public-data rules.

Link these notes to standalone README/guides/contracts and to each other.
Use English throughout; avoid inventing progress or completion dates.
No copied source wiki, global taxonomy or personal metadata.

The cold-start gap is **not solved by extraction**. Current campaign inventory,
capture plans and binding preparation depended on temporary source-project
scripts/artifacts not transferred here. Document required input schemas and
which inputs a caller must prepare; give a runnable synthetic offline example
where fixtures permit. Do not advertise a one-command fresh Rust audit or
transfer temporary scripts implicitly to make that claim true.
Completing durable acquisition/binding orchestration is future work.

## 5. Public export gate, legal boundary and publication

Public visibility is explicitly authorized, but does not determine a software
license. No source root `LICENSE` was supplied/identified in the briefing.
Do not invent MIT/Apache terms, claim all rights cleared or inherit a license
from a dependency. Preserve any discovered applicable notices and raise an
actual conflicting license/provenance issue before publication. Otherwise
document that no project license has been selected and record the choice as
backlog; public availability is not a permissive license grant.

Before `gh repo create` or push, the parent prepares an exact public candidate
path list and obtains a fresh read-only exposure/security check over its actual
content. Check source-derived test bodies, absolute paths, tokens/PEMs,
repository/session IDs, captures, private URLs and hidden files, not just names.
No blanket `git add .` before curation; no commit/push containing raw artifacts.
Ensure Git history is new and contains no AIForAll history or private blobs.

The parent performs authorized Git initialization, account verification,
repository-name/visibility checks, public creation through `gh`, scoped
commit/push and remote-reference verification. Do not overwrite an existing
repository or force-push; report a collision. Record the actual public URL,
commit, remote branch and verification result in the handoff/documentation
without embedding credentials. The architecture leaf performs none of these
mutations.

Keep original AIForAll scripts until the new repository has passed validation
and its remote commit is verified. No source deletions, redirection shims or
source migration edits in this implementation lot. A later parent-owned
migration note/handoff can explain the provisional duplication.

## 6. Acceptance

1. Review curated file inventory and portability diff; no incidental public
   export or scope expansion.
2. In the new root run all five named Python unittest suites, offline, plus any
   existing synthetic fixture dependencies they require. Preserve meaningful
   assertions; the historical 148-test result is not a substitute for the new
   run. No Cargo, runtime, live MCP writes or network is needed for these tests.
3. Verify root separation with a temporary synthetic target Git fixture:
   different tool/target HEADs accepted; wrong manifest root, wrong reported
   Serena root, traversal and stale source binding rejected. Use mocked
   sessions, no shared-server activation or index modification.
4. Run the documented synthetic offline example end to end; verify retained
   diagnostics/nodes, soft edges not unioned, explicit unknowns and stable
   deterministic output. Any optional replay using private cached captures is
   local-only, is not required for public reproducibility, and never exported.
5. Check standalone documentation links and the new vault's navigation, explicit
   cold-start gap, source-specific profile and unselected-license disclosure.
6. Complete the public export gate, then verify the pushed commit/branch and
   public visibility. Preserve source copies and foreign source-project changes.

Closeout reports actual test commands/counts, synthetic replay result, public
review disposition, published commit/URL and remaining limitations. Packaging
success is not certification of complete Rust dependency closure or completion
of the acquisition pipeline.
