---
title: Pipeline architecture
created: 2026-11-14
status: current-design
---

# Pipeline architecture

The code is an ordinary Python CLI pipeline. It does not require an agent host.

This is a quick POC using `rust-code-mcp` and Serena. The proposed Rust-focused
successor would replace both MCP integrations with a rust-analyzer-based backend.
A Sonar-based analysis library is an unselected alternative for broader language
coverage. Neither direction has been implemented or validated; equivalent graph
evidence and coverage remain evaluation criteria. See [[backlog]].

## Stages

Before dependency investigation, `diagnostic-scope.py` applies a simple rule
policy: known documentation and explicit local mechanical exceptions are local;
all other rules, including unknown rules, are transverse by default.
It does not inspect function signatures/bodies or certify independence.
Its routing artifact is a selection input, not an automatic rewrite of a saved
MCP collection plan or an approved co-edit constraint.

The final `lint-workgraph.py` command applies this policy directly, enumerates
native crates/items without manual seeds, hydrates their locations and queries
direct incoming/outgoing/import relations for every transverse diagnostic scope.
It reuses the existing collector and native HIR graph, not a second semantic
engine. A generic capture is validated and assembled into file coupling and
tentative ownership groups; legacy origin-proof artifacts remain a separate path.

After graph export, `partition-workgraph.py` selects practical correction lots
offline. Strict diagnostic units supply file workload weights; exact aliases
count once. LPT initializes loads, then deterministic file moves/swaps minimize
overload, verified cross-lot affinity and finally load variance in that order.
Only distinct verified writable-file pairs drive affinity. Other native
observations remain coordination witnesses, not hard co-edit constraints.
One file has one write owner; ambiguous paths remain manual and context-only
files are shared read-only. Lot count is not worker concurrency.

1. **Input inventory.** Read captured Clippy JSONL and complete Sonar pages.
   Keep original issue provenance, strict aliases and uncertain matches.
2. **Source and MCP evidence.** Select an explicit target workspace, capture
   source hashes, and call only curated read-only tools on existing local MCP
   servers. The tool checkout and analyzed Rust checkout are separate.
3. **Physical localization.** Replay source coordinates, function extents and
   captured symbol witnesses. Exact physical location is not semantic-reference
   completeness.
4. **Dependency observations.** Preserve verified file endpoints and unresolved
   observations with query/hash provenance. Do not invent consumer identities.
5. **Work graph.** Retain diagnostic files, observed consumers, qualified hard
   constraints, candidate edges and tentative ownership groups.

## The two edge classes

- `hard_must_coedit`: an independently reviewed and evidence-qualified required
  file set. Only these constraints union file ownership groups.
- `candidate_dependency`: a dependency/impact observation to review when
  partitioning work. It does not force joint edits.

The current file-observation arrow runs from a queried declaration/provider to
an observed consumer: **impact direction**, not `depends_on` or execution order.
Repeated usage sites and distinct file boundaries have different counts.

## Artifact order

Raw captures, source/context and origin proofs precede the snapshot. Normalized
evidence binds that snapshot. Optional observations bind finalized snapshot and
evidence hashes. The planner binds its input artifacts.

Observations must not be hashed back into the snapshot they reference; that
would create a circular hash dependency.

## Trust and safety boundaries

The portable campaign skill delegates deterministic wave planning to
`campaign-wave.py` through Context Mode, then leaves approved execution to the
host's actual tools. Scheduling uses all known cross-lot boundaries and write
overlaps, not just the optimization affinity projection. Generation-bound state
separates active leases from lead-accepted/integrated completion. Dry-runs reserve
nothing; the lead rechecks and acquires exclusive leases before native execution.

Accepted resolutions are caller-normalized into a common read-only CSV snapshot.
Project skills remain authoritative separately. Workers propose new decisions
per lot; only the lead reviews and merges them between waves. Missing Context
Mode blocks bulk work. No Python-to-host API, global configuration or new
framework is introduced. See [[history]] for the verified planning boundary.

Explicit target-root selection, reported MCP root checks, source/hash replay,
bounded queries, root-confined references and output alias checks protect the
evidence workflow. Unknown language/index coverage remains explicit.
No index rebuild, project activation, corrective edit or worker dispatch is
performed.

See [[limitations]], [[reproduction-gap]] and [[backlog]].
