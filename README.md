# lint-workgraph

> **Quick POC, not a production-ready platform.** This prototype currently uses
> `rust-code-mcp` and Serena. For a Rust-focused successor, the intended direction
> is to replace both MCP integrations with a rust-analyzer-based backend.
> For broader language coverage, an alternative to investigate is a
> Sonar-based analysis library. Neither replacement is implemented or validated;
> no specific Sonar library has been selected, and equivalent dependency-graph
> coverage must be evaluated rather than assumed.

Build evidence-backed dependency/work graphs to help allocate diagnostic work
among workers.

The pipeline keeps observation, physical source localization, correction
constraints and partition review separate. It does **not** fix code, dispatch
agents, prescribe a worker count, or turn every reference into a mandatory joint
edit.

## Included tools

- [`github-lint-inventory.py`](ops/scripts/github-lint-inventory.py): optional
  read-only GitHub issue inventory.
- [`clippy-sonar-overlap.py`](ops/scripts/clippy-sonar-overlap.py): strict,
  provenance-preserving overlap inventory from captured diagnostics.
- [`mcp-code-evidence.py`](ops/scripts/mcp-code-evidence.py): bounded direct MCP
  evidence collection against an explicitly selected source workspace.
- [`clippy_source_ranges.py`](ops/scripts/clippy_source_ranges.py): shared
  deterministic source-range verification.
- [`clippy-constraint-plan.py`](ops/scripts/clippy-constraint-plan.py): offline
  evidence replay and work-graph export.

The output distinguishes qualified `hard_must_coedit` constraints from
`candidate_dependency` observations. Candidate boundaries and unresolved evidence
remain visible; missing edges do not certify independence.

## Requirements and discovery

Use Python 3.11+ and Git. The offline planner and synthetic fixture mechanics do
not require OpenCode, an LLM, Docker or a Rust build.

```powershell
python -B ops/scripts/clippy-sonar-overlap.py --help
python -B ops/scripts/mcp-code-evidence.py --help
python -B ops/scripts/clippy-constraint-plan.py --help
python -B -m unittest discover -s ops/tests -p "test_*.py"
```

## Try the self-contained synthetic example

```powershell
python -B examples/offline.py
```

It generates invented inputs, runs the actual planner CLI twice and verifies
identical plans: **4 retained records, 6 nodes, 3 candidate edges, 0 hard edges
and 1 unknown mapping**. Default temporary outputs are removed on exit. See
[the example guide](examples/README.md) to retain them in a new directory.
This does not acquire real Clippy/Sonar data or close the cold-start gap.

All **194 extracted offline tests** also pass with site packages disabled:

```powershell
python -S -B -m unittest discover -s ops/tests -p "test_*.py"
```

## Optional live collection

Live collection additionally needs the optional pinned MCP SDK and already
running compatible local MCP servers:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r ops/scripts/requirements-mcp-code-evidence.txt
```

These are optional environment-setup commands, not a server installer. The tool
does not start servers, activate shared projects, rebuild indexes or change
global configuration. Source-bearing collection requires an explicit target
workspace; the tool checkout is not implicitly the Rust source checkout.

See the [collector guide](docs/guides/mcp-code-evidence.md) and
[offline graph planner guide](docs/guides/clippy-constraint-planner.md).

## Read the contracts and notes

- [Extraction boundary](docs/contracts/extraction.md)
- [Pipeline IO and invariants](docs/contracts/io.md)
- [New Obsidian vault](obsidian/index.md)
- [Current limitations](obsidian/limitations.md)
- [Cold-start reproduction gap](obsidian/reproduction-gap.md)
- [Remaining work](obsidian/backlog.md)

Open the `obsidian/` directory as a vault in Obsidian. It contains newly written,
linked history, architecture, provenance, limitations and backlog notes. No old
vault or private campaign artifacts are included.

## Important current limits

This is an experimental extracted implementation, not a one-command fresh audit
of an arbitrary Rust project. Clippy/Sonar acquisition, collection-plan generation
and independent historical source binding are not yet a complete durable
cold-start workflow.

The live positive origin-binding profile remains tied to
`apparatus_contracts::runtime::validate_runtime_uid` and its expected compatibility
layout. Generic offline planning can consume valid supplied evidence; this narrow
live profile is not a general Rust resolver. Full macro/cfg/trait/feature/test
reference coverage is not guaranteed.

The extracted code was originally exercised on Windows. Other platforms and
server-response formats require their own verification.

Diagnostic messages, captures and graph outputs may contain sensitive source
information. Keep real run artifacts private; the pipeline is not a general
secret redactor. Local run/environment directories are ignored by default.

## Provenance and license status

Curated extraction from source revision
`c4bba486291edd63dabafd5b5235c2d1ba628fa0`, without importing source Git history,
private application implementations, real captures, credentials or personal
configuration. Existing host-project copies are provisionally retained.

No project software license has been selected. Public visibility does not
constitute a permissive license grant; license selection is tracked in the
backlog.
