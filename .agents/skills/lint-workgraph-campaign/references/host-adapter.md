# Thin host adapter: discover, prepare, approve, invoke

Only transport changes between hosts. The helper remains offline Python and
never receives an SDK client, evaluates input code, imports an input-selected
module, accesses credentials or calls a host tool.

## Record observed capabilities

The host agent records this JSON-shaped evidence in its authorized handoff:

```json
{
  "context_mode": {
    "available": true,
    "tool": "<exact tool path returned by the current catalogue>",
    "evidence_ref": "<catalogue and successful bulk-run evidence>"
  },
  "agent_launch": {
    "available": false,
    "tool": null,
    "evidence_ref": "<catalogue/permission check showing native launch unavailable>"
  },
  "permissions_ref": "<current host permissions and approval record>",
  "project_rules_ref": "<target instructions, skills and decision canon>"
}
```

These bracketed values are descriptions to fill from actual observations,
not runnable tool names or a dynamic adapter format. `capability_status(record)`
in `campaign-wave.py` is a small pure validation aid for simulations; it neither
discovers tools nor enforces permissions. Missing Context Mode means **BLOCKED**:
ask for an explicit alternative, never silently dump data or install a tool.
Missing native launch permits preparation only, with execution unavailable.
An available tool still requires permissions, explicit approval and leases.

## Concrete think-as-code pattern

First discover the actual Context Mode execution tool and its current schema.
When it exposes `language`, `code` and `intent`, submit the following **code
payload** through that tool; these are Python sandbox instructions, not another
orchestrator. Fill authorized absolute paths in the host before submitting.
If that host's schema/runtime differs, adapt only this transport under its
documented capabilities instead of pretending this example is universal.

```python
import json
import subprocess
from pathlib import Path

package = Path("/authorized/full/lint-workgraph")
args = [
    "python", "-S", "-B", str(package / "ops/scripts/campaign-wave.py"),
    "--lots", "/authorized/campaign/lots.json",
    "--state", "/authorized/campaign/state.json",
    "--resolutions", "/authorized/campaign/resolutions.json",
    "--output", "/authorized/campaign/wave.json",
    "--csv", "/authorized/campaign/accepted.csv",
    "--max-workers", "3",
]
run = subprocess.run(args, capture_output=True, text=True)
if run.returncode:
    print("BLOCKED:", run.stderr[-2000:])
else:
    wave = json.loads(Path(args[args.index("--output") + 1]).read_text(encoding="utf-8"))
    print(json.dumps({
        "wave_id": wave["wave_id"],
        "selected": wave["selected_lots"],
        "excluded": wave["excluded"],
        "manual_units": wave["manual_queue_count"],
        "conflict_pairs": wave["conflict_pair_count"],
        "snapshot": wave["common_snapshot"],
        "request_refs": [r["id"] for r in wave["action_requests"]],
        "execution": wave["execution"],
    }, sort_keys=True))
```

The host's sandbox must permit those paths and Python invocation. A blocked
path is not permission to bypass its sandbox. The subprocess above runs only
the existing offline helper: **the helper itself never spawns a subprocess**.
Inspect wave requests/provenance in Context Mode with bounded summaries.
Do not dump full inputs or treat a tool catalogue read as bulk-run evidence.

## Native handoff after approval

1. Review the wave and project constraints; resolve conflicting precedents.
2. Refresh state/hashes, then acquire exclusive leases through the project's
   actual coordination mechanism. A saved plan has not reserved anything.
3. Discover the exact native launch tool/profile and argument schema. The host
   agent—not Python—invokes that real tool with the selected request's target
   root, files, lease, read-only context/CSV, policy and validation contract.
   There is intentionally no fabricated universal `launch()` function here.
4. Verify the native result and record actual tool/lease evidence. Without an
   allowed launch capability, stop at requests for explicit parent/manual action.

Per-lot proposals remain separate JSON. Only the lead reviews/accepts decisions
and integrates changes. Refresh inventory and create new-generation state after
lot regeneration; do not auto-migrate old completion by lot name.

## Discovery portability, not runtime certification

The primary client documentation describes project `.agents/skills` discovery
within the current directory/ancestor repository scope:

- [Codex skills](https://developers.openai.com/codex/build-skills.md):
  explicit `/skills` selection or `$skill` mention.
- [Pi skills](https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/skills.md):
  explicit `/skill:lint-workgraph-campaign`.
- [OpenCode skills](https://opencode.ai/docs/skills):
  use its native skill-loading tool when this name is exposed and permitted.

A neighboring lint-workgraph checkout is **not** automatically discoverable from
an unrelated target checkout. A practical neutral prompt is:

> Read `<absolute lint-workgraph checkout>/.agents/skills/lint-workgraph-campaign/SKILL.md`
> and its linked adapter. Use this full checkout's helper, but treat
> `<absolute target checkout>` as the application workspace. Plan only; stop
> before execution unless I explicitly approve the wave and the project permits it.

No global install, plugin, copied policy or client configuration is required.
The frontmatter does not grant tools or suppress host approvals. Simulated
capability tests do not prove native execution on Codex, Pi or OpenCode.
