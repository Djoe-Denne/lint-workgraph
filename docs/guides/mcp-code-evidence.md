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
