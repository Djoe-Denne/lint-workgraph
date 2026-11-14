# Synthetic offline demonstration

From the tool checkout:

```powershell
python -B examples/offline.py
```

Only Python 3.11+ standard-library modules are used. No MCP, Git, Cargo, Sonar,
GitHub or network service is contacted. The script deliberately imports the
curated test-only `Fixture` builder from
`ops/tests/test_clippy_constraint_plan.py`; that builder and its small Rust
fixture must remain present. It is not a public library API.

All sources, diagnostics, captures and authorization-like metadata are invented.
The Rust snippets are lexical test data, not compiled application code. Fixture
timestamps and HEAD strings are test labels, not real capture provenance.
The compatibility-profile layout is synthetic, not an exported implementation.

The script writes a strict inventory, raw witnesses, origin proof, snapshot,
evidence and observations in acyclic order. It then runs the **actual planner
CLI** twice and asserts byte-identical plans from identical inputs, retained
records, explicit unknown mappings and three soft edges with zero hard unions.
This demonstrates schema/graph behavior, not a fresh audit or safety certificate.
Expected summary: 4 retained diagnostic records, 6 file nodes, 3 candidate
edges, 0 hard edges, 1 unknown mapping, `global_independence: unproven`,
and identical repeated plan bytes.

By default generated files live in an owned temporary directory removed on exit.
To inspect them, use `--directory` with a new directory whose parent exists:

```powershell
python -B examples/offline.py --directory <new-output-directory>
```

The generated `plan.json` and `plan.md` can then be inspected locally. Generated
artifacts contain the local fixture root; they are not public source files.
No input acquisition/binding orchestration or corrective edits are implemented.
