---
name: lint-workgraph-campaign
description: Prepare and coordinate reviewed correction waves from lint-workgraph lots, respecting project policy, known conflicts, generation-bound leases and a shared read-only resolution CSV. Use for campaign planning or explicitly approved native worker handoffs, not automatic fixes.
---

# Lint workgraph campaign

## Scope and prerequisites

- Read the **target application's** project instructions, applicable skills,
  canonical decisions, permissions, ownership and validation/build-slot rules.
  The lint-workgraph checkout is the helper package, not the correction target.
- Keep project policy authoritative even when absent from the shared CSV.
  Never copy another project's policies into the target or treat this skill as a grant.
- Read [the host adapter](references/host-adapter.md). Inspect actual exposed
  catalogue capabilities and permissions; do not infer them from the client brand.
  Record `context_mode`, `agent_launch`, `permissions_ref`, `project_rules_ref`
  and evidence references as specified there.
- Use **think-as-code with Context Mode** for bulk manifests, provenance,
  planning, build/test output and decision normalization. Catalogue discovery
  alone is not proof of execution. If unavailable, report **BLOCKED** and ask
  for an explicit alternative. No silent dump, install or configuration change.
- Honor operator pauses and native harness rules, including existing Ensemble
  coordination requirements. Execution always needs explicit authorization.
- Keep the full lint-workgraph checkout: the helper imports existing sibling
  validators. A copied SKILL.md alone is not a self-contained installation.

## Prepare a wave, not a launch

1. Obtain the reviewed lots snapshot. Preserve its partial coverage, unknowns,
   manual queue, proposed status and all boundary qualifications.
2. The lead supplies schema-1 `lint-campaign-state` bound to the exact lots SHA:
   active IDs need explicit lease/owner references; completed IDs need **lead
   acceptance and integration references**, not merely an author's finished report.
   Refuse stale state; same-name IDs never imply completion in a new generation.
3. Under project permissions, normalize applicable decisions into
   `lint-reviewed-resolutions` JSON. Each row has string fields
   `id,status,decision,conditions,exceptions,source_ref,approval_ref`.
   Only exact `Accepted` rows with source and approval references enter the CSV.
   Never parse Markdown status automatically, invent missing rows, self-promote
   proposals or use CSV omission to override canonical project policy.
4. In Context Mode, run the existing helper from this package, with explicit paths:

   ```text
   python -S -B <package>/ops/scripts/campaign-wave.py
     --lots <lots.json> --state <state.json> --resolutions <resolutions.json>
     --output <wave.json> --csv <accepted.csv> [--max-workers N]
   ```

   Use the concrete execution pattern in the adapter. Default planning cap is 1,
   not a required campaign size. Python never calls native tools or reserves leases.
5. Inspect selected IDs, exclusions, manual count, all known conflict pairs,
   CSV hash, action requests and coverage/review gates. Conflict edges include
   backend-observed boundaries and writable overlaps, not just optimization
   affinity. Shared read-only context is not a write conflict.
6. With no eligible wave, explain the active/completed/conflict exclusions.
   Do not loop recollection/index rebuilding on untouched code. Unknown scope
   prevents independence certification; serial fallback also needs lead approval.

## Explicitly approved host execution

- A plan is **not atomic dispatch authority**. Before each native launch, the
  lead refreshes/rechecks state and input/CSV hashes and acquires an exclusive
  project-authorized lease covering the requested files. Coordinate with other
  planners/leases; concurrent dry-runs may otherwise select the same work.
- Review and approve inherited coverage and boundary risk first. If a native
  launch tool/profile is unavailable or not permitted, return the action
  requests for manual/parent execution and state **execution unavailable**.
  Never invent an API, bypass a harness or substitute credentials.
- Give each native worker the target root, exclusive files and lease reference,
  read-only context, boundary witnesses, unit/provenance references, CSV path/hash,
  canonical project rules, permissions and its validation contract.
- The shared CSV is a read-only **logical contract**, not an OS permission
  mechanism. Workers never append to it or the common registry. They return
  separate per-lot JSON decision proposals with evidence and unresolved risks.
  Apply project-specific validation/build-slot controls centrally.
- The lead verifies results, validates and integrates retained changes, then
  records acceptance/integration and reviews decision proposals between waves.
  Proposed/Superseded/Rejected rows never silently become Accepted.
- After integration, refresh global diagnostics/lots and assess MCP freshness
  under project authority; no automatic index rebuild. A new lots hash requires
  explicitly reviewed new-generation state. Fixed-generation completed records
  release known scheduling conflicts, not graph freshness/review requirements.

## Handoff

Report input generation/hashes, selected/excluded IDs, manual work, CSV/hash,
capability evidence, leases actually acquired, native calls actually made,
validation/integration evidence and unresolved gates. Distinguish a prepared
request, a successful native launch, author completion and lead acceptance.
Never claim cross-client execution from simulated adapter tests.
