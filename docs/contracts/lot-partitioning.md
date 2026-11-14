# Offline work-lot partitioning

Status: implementation contract authorized by the lead under the user's explicit
optimization request. Input baseline: published `6986a3e9704899e53c4d095c42e2f17fef0ec300`.
No backend collection, source corrections or worker dispatch.

## Decision and algorithm

Balanced weighted graph partitioning fits the objective better than community
detection: balance correction workload while reducing cross-lot coupling.
METIS multilevel k-way partitioning is the preferred established native solution,
but the parent verified no official Windows wheel for PyMetis 2025.2.2 on this
native Windows/Python 3.13 host. Do not add Conda, a compiler or global packages
for this POC. Leiden optimizes communities, not this workload constraint.

Implement a small stdlib heuristic: **LPT workload seeding, then deterministic
weighted-cut local refinement with single-file moves and pairwise swaps**.
This is a bounded local search, not a new graph engine, METIS implementation,
full Kernighan–Lin algorithm or optimality guarantee. Keep the algorithm isolated
so a verified METIS adapter can replace it later without changing manifests.

Research supplied by the parent:
- https://github.com/KarypisLab/METIS
- https://documen.tician.de/pymetis/functionality.html
- https://pypi.org/project/pymetis/2025.2.2/
- https://leidenalg.readthedocs.io/en/stable/intro.html
- https://arxiv.org/abs/1801.05489 (LPT definition and scheduling context).
- https://networkx.org/documentation/networkx-3.4/reference/algorithms/generated/networkx.algorithms.community.kernighan_lin.kernighan_lin_bisection.html
  (pair-swap cut refinement comparison, not the exact algorithm implemented here).

## Command and ownership

One implementation owner: `ops/scripts/partition-workgraph.py`,
`ops/tests/test_partition_workgraph.py`, `docs/guides/partition-workgraph.md`.
Parent owns narrowly necessary README/vault updates and real replay.
Do not modify/recollect the existing graph or introduce a dependency.

`python -B ops/scripts/partition-workgraph.py --graph <graph.json>
--output <lots.json> --report <lots.md>
[--parts K | --target-issues N]`

Offline only; strict schema/accounting checks, output/input alias guards and
atomic publication. Record graph SHA-256 and recheck it before publication.
No source bodies or real private artifacts committed. No final-command
integration is required in this lot.

## Work units and ownership

Input is existing `kind: lint-workgraph`, schema 1. Preserve all diagnostics.
Build strict work units from validated exact alias pairs: keep the Clippy
representative with both provenances; unmatched Sonar sites remain units.
Never deduplicate uncertain hints, names, rule families or raw Sonar keys.
Malformed/conflicting alias or diagnostic accounting is an error.

A physical file is the indivisible writable atom, weighted by its strict-unit
count. Only graph nodes with `source_status: verified_current` and a unique
canonical path receive write ownership. Do not resolve compiler dot segments or
guess aliases. Unknown symbol localization on a verified file is permitted work
ownership, but carries `review_required`, not independence certification.
Missing/ambiguous/multiple-file unit ownership stays in an unresolved queue;
never duplicate its workload across lots or silently choose a primary file.

Context-only nodes have zero correction workload and no write owner. Attach
needed context paths as read-only references to incident lots; shared read-only
context is allowed, shared writable files are not. Do not create empty jobs for
context nodes or introduce fake affinity through a shared context neighbor.

Respect approved hard must-coedit atoms if an existing validated representation
can be consumed. For this POC, **refuse nonempty hard-constraint/hard-edge input
whose approval and grouping semantics are unsupported**, rather than ignore it
or infer approval. Candidate dependencies never become hard unions.

## Objective and deterministic optimization

Project candidate edges between writable atoms to undirected affinity:
one positive integer weight **1 per distinct unordered file pair**.
Ignore self-loops; duplicate callsites/directions do not increase affinity.
Keep every original edge ID/direction/qualification for boundary reporting.
Unverified-current/backend-only observations remain visible boundary context,
not optimization affinity; count excluded observations explicitly.

Default `target-issues=50`; K is `ceil(assignable_units / target)`, bounded to
1..writable-atoms, or explicit positive `--parts` in that range. Zero work yields
zero lots. K is lot count, not worker concurrency. Explicit options conflict.
Target size is a workload proxy, not a time estimate or hard feasibility promise.

Seed with descending-weight atoms, canonical-path tie break, assigning to the
least-loaded lot then lowest lot ID. Preserve this LPT baseline for comparison.
Let M be total assignable weight and C=max(largest atom, ceil(1.20*M/K)).
Score lexicographically: sum squared excess above C, weighted crossing-pair
cut, then sum squared loads. Consider nonempty-lot-preserving moves and swaps;
apply the best strictly improving score, deterministic path/lot tie breaks.
Stop at a local optimum or 100 accepted improvements; report why and timing.
No randomness, tuning service or stochastic multi-start needed.

Report baseline/final cut, loads, overload, imbalance and objective. Refinement
cannot worsen the declared lexicographic score; cut reduction is secondary to
overload. Heavy single files remain intact and visibly exceed target if needed.
Do not claim the baseline or final partition globally optimal.

## Manifest and acceptance

JSON `kind: lint-work-lots`, schema 1: input hash, algorithm/options, strict
accounting, baseline/final metrics, lots, unresolved queue and limitations.
Each lot exposes ID, writable files, strict-unit IDs with full diagnostic
provenance, workload, read-only context, internal/boundary edge IDs, neighboring
lots, review tasks and `status: proposed`. Retain directed boundary witnesses.
Every strict unit is assigned once or queued once; every writable file has one
owner. Candidate coupling and unknowns require handoff checks, never auto-dispatch.

Fixtures cover aliases, unknown paths/localization, context-only nodes,
duplicate/reverse edges, heavy atoms, determinism, improvement/termination,
unsupported hard constraints and invalid accounting/output collisions.
Replay the actual saved graph offline: reconcile strict 620 units, distinguish
131 verified editable files from five unresolved raw paths and context-only
nodes; compute rather than hard-code counts. All 1,046 provenance records remain
traceable. Deliver actual lot manifests, load/cut comparison and concrete
boundary-review tasks, not only tests. No backend, Cargo or runtime is needed.
