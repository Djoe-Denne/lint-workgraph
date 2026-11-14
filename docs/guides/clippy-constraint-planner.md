# Offline constraint planner and work graph

The planner consumes supplied, hash-bound local artifacts. It does no discovery,
network access, Git/Cargo execution, correction, agent scheduling or dispatch.
See the [IO contract](../contracts/io.md) for schemas, exact physical mapping
proofs, policy binding, closure and path/publication invariants.

```powershell
python -B ops/scripts/clippy-constraint-plan.py --inventory <overlap.json> --snapshot <snapshot.json> --evidence <evidence.json> --observations <observations.json> --output <plan.json> --report <plan.md>
```

`--observations`, `--constraints` and `--report` are optional. Observations are
separate inputs bound to finalized snapshot/evidence hashes, never snapshot
inputs themselves. Constraints use `clippy-coedit-constraints` schema version 1
and require matching snapshot-bound approval, policy and complete relevant
query scope before `must_coedit` can create a hard union. Merely supplying a
dependency or an all-true proof summary does not approve a union.

Output retains every diagnostic and file node, exact alias accounting, current
hash checks, mappings, query coverage, constraints, blockers and a `work_graph`.
Soft arrows run queried declaration/provider → observed consumer (impact),
not `depends_on`. Repeated sites remain distinct; same-file loops are not
cross-file boundaries. Unknown mappings remain attached to nodes.
Only qualified hard constraints compose into ownership groups. Candidate
boundaries are review tasks and never force pairs or fixed worker counts.
Missing edges mean `not_observed`, not independent.

The planner independently replays physical and origin witnesses. Its HEAD check
is format-only; live source freshness and historical diagnostic equivalence
remain distinct claims. Publication rechecks protected input/capture/source
hashes. Separate JSON/Markdown replacement is not a multi-file transaction.

Try the [runnable synthetic example](../../examples/README.md), which uses no
MCP or private source. It is not a one-command fresh Rust audit: capture plans,
binding preparation and acquisition are still caller responsibilities.

```powershell
python -B -m unittest discover -s ops/tests -p test_clippy_constraint_plan.py
python -B -m unittest discover -s ops/tests -p "test_*.py"
```

The narrow live origin profile remains a compatibility limitation, even though
generic offline planning works with supplied schema-valid evidence. No plan
certifies complete reference closure, globally safe concurrency or authorization
to edit application code.
