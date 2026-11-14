# Offline correction-lot selection

Partition an existing full-inventory graph without a backend, source reads,
Cargo, package installation, fixes or worker dispatch:

```powershell
python -S -B ops/scripts/partition-workgraph.py `
  --graph .tmp/full-inventory-graph.json `
  --output .tmp/correction-lots.json `
  --report .tmp/correction-lots.md
```

Output parents must exist. Use either `--parts K` or `--target-issues N`
(default 50), never both. Both arguments must be positive. K is a proposed
lot count, not concurrent workers. Explicit K cannot exceed positive-work files;
zero assignable work produces zero lots. Exit 0 means publication succeeded,
not dispatch approval; exit 2 means invalid input or publication failure.

## Workload and boundaries

The command reuses the existing inventory validator and strict JSON/publication
helpers. It hashes and parses the same bounded input bytes (maximum 256 MiB),
rechecks the graph hash before publication, rejects input/output/hardlink aliases,
and only replaces recognized prior lot outputs. JSON and Markdown replacements
are individually atomic, not a two-file transaction.

Validated exact Clippy/Sonar pairs count as one strict unit with both original
records. Other records remain separate; uncertain hints never merge work.
The manifest retains original records, raw Sonar keys, per-unit provenance,
diagnostic context, and every original directed edge and qualification.

A uniquely spelled canonical `verified_current` file with assignable units is
an indivisible weighted atom. Dot segments are not normalized, case aliases
are not guessed, and no source is dereferenced. Missing, conflicting,
multi-file or unresolved owners stay in the manual queue once per strict unit.
Context-only files have no jobs or write owners. Incident nonwritable context
can be shared read-only; writable cross-lot neighbors require coordination.
Unknown symbol localization on an owned file still requires review.

Only distinct unordered pairs of source-verified writable files have optimization
weight 1. Duplicate/reversed observations and self-loops do not inflate affinity.
Backend-only observations remain in internal/boundary witnesses, never optimization
affinity. Nonempty unsupported hard constraints or group approvals are rejected,
not silently discarded.

## Small deterministic heuristic

Descending issue-count weights, then path order, seed the least-loaded lot
(lowest lot ID breaks ties). Default K is `ceil(assignable units / target)`,
bounded by file count. Capacity is
`max(largest atom, ceil(1.20 * assignable units / K))`.

Local refinement chooses the best strictly improving single-file move or pair
swap, preserving nonempty lots. Its lexicographic score is:

1. Squared overload above capacity.
2. Crossing distinct-pair affinity.
3. Sum of squared lot loads.

Candidate gains use incremental neighbor-lot affinity counts. Deterministic
path/lot ties avoid random results. Stop at a local optimum or 100 accepted
improvements. Report LPT/final scores, loads, cut, imbalance, accepted steps and
stop reason; baseline ownership is retained. A heavy file can exceed the target
and remains visibly indivisible. Issue counts are workload proxies, not minutes.

This is not METIS, full Kernighan–Lin, a global optimum, or independent/dispatch-safe
work certification. Before editing, inspect each lot's review tasks, directed
boundary witnesses, inherited partial coverage/warnings, and the manual queue.
The graph is a snapshot, not a current-source freshness certificate.

Research reused for the approved POC choice:

- [METIS upstream](https://github.com/KarypisLab/METIS): established multilevel
  partitioning, preferred when a supported native dependency is available.
- [LPT scheduling analysis](https://arxiv.org/abs/1801.05489): descending-weight
  load-balancing context.
- [NetworkX Kernighan–Lin reference](https://networkx.org/documentation/networkx-3.4/reference/algorithms/generated/networkx.algorithms.community.kernighan_lin.kernighan_lin_bisection.html):
  pairwise partition refinement context, not an implementation claim here.

The parent verified the Windows packaging limitation before authorizing the
stdlib heuristic. No dependency/toolchain installation is required.

## Tests

```powershell
python -S -B -m unittest discover -s ops/tests -p test_partition_workgraph.py -q
python -S -B -m unittest discover -s ops/tests -p "test_*.py" -q
```

Fixtures are synthetic. They cover strict provenance, manual ownership,
context-only nodes, deduplicated affinity, deterministic improvements,
incremental adjacent-swap gains against full cuts, heavy/zero work, unsupported
constraints, malformed accounting, output aliases, input drift and atomic failure.
Repeat the actual offline command and compare manifests after removing only
`timing`; partition ownership, metrics, witnesses and provenance should match.

## Verified real-data result

The actual command produced 12 proposed lots, with loads 47–59 under capacity
60. All 620 strict units reconcile: 598 assigned to 131 exclusive file owners,
22 queued from five ambiguous raw paths. All 1,046 original records and 1,312
Sonar keys remain traceable; 120 context-only nodes have no write owner.

Across 87 eligible source-verified unordered pairs, the cut decreased from
82 to 36 after 33 improvements. Load variance increased within capacity because
cut reduction takes priority once overload is zero. It stopped at a local
optimum for its move/swap neighborhood, not a proved global optimum.

The parent repeated the real CLI: exit 0, 0.764 seconds, identical manifests
outside timings and unchanged input graph. All 271 offline tests passed.
Independent review checked gains on 150 small graphs with full recomputation
and reconciled actual ownership, provenance and boundary witnesses.
Real graph and lot outputs remain local/ignored.
