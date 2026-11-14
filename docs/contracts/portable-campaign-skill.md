# Portable campaign skill and wave helper

Status: implementation contract under explicit user authorization, based on
published `bc8278cc9725c0dc7ed8d9d62aca53813638e59d`. Build/test the skill only;
do not launch correction workers, patch sources or recollect diagnostics now.

## Deliverables and owner

One author owns these new files and their narrow documentation:
- `.agents/skills/lint-workgraph-campaign/SKILL.md`;
- `.agents/skills/lint-workgraph-campaign/references/host-adapter.md`;
- `ops/scripts/campaign-wave.py`;
- `ops/tests/test_campaign_wave.py`;
- `docs/guides/campaign-wave.md`.

Parent owns README/vault integration and publication. No global skill install,
profile/client configuration, plugin, workflow engine, LangGraph or new harness.
Use existing stdlib/unittest conventions. Frontmatter name is
`lint-workgraph-campaign`; describe applicability and link the one adapter.
Manual reading is the fallback when a client does not discover this local path.

## Portable host contract

The skill first reads the target project's instructions, applicable skills,
decision registry, permissions, ownership and validation/build-slot rules.
Do not copy AIForAll policy into this public skill. Project canonical policy
remains authoritative even when it is absent from the common CSV.

Inspect **actual exposed capabilities**, not Codex/Pi/OpenCode brand names:
bulk reading/planning uses think-as-code and Context Mode. If Context Mode is
unavailable, report `BLOCKED` and request an explicit alternative; do not silently
dump inputs, install tooling or alter configuration. Tool discovery by itself
does not prove a bulk analysis ran. Respect operator pauses and native harness
requirements, including an existing Ensemble requirement where applicable.

The single adapter reference describes a host-filled record:
`{context_mode: {available, tool, evidence_ref},
agent_launch: {available, tool, evidence_ref}, permissions_ref, project_rules_ref}`.
These are reported catalogue/permission checks, not a dynamic execution format.
Use only actual native tools/profiles under the host's permissions. If native
launch is unavailable, emit launch requests for the parent/manual workflow and
state execution unavailable; never invent an API or substitute credentials.
Only transport differs across clients; lot/graph/decision semantics do not.

Python prepares data and action requests; it cannot implicitly call host tools.
No eval/import from inputs, API placeholders presented as working adapters,
embedded credentials or bypass of client approval/coordination requirements.

## Offline helper IO

`campaign-wave.py --lots <lots.json> --state <state.json>
--resolutions <decisions.json> --output <wave.json> --csv <accepted.csv>
[--max-workers N]`

Default is planning/dry-run, never agent launch. `max-workers` defaults to 1
conservatively; it is an overridable planning cap, not a fixed campaign worker
count or the number of lots. No database, implicit state mutation or lease daemon.

State schema 1, kind `lint-campaign-state`:
`{schema_version, kind, lots_sha256, active, completed}`.
`active` maps lot ID to `{lease_id, owner_ref}`.
`completed` maps lot ID to `{lead_acceptance_ref, integration_ref}`.
References are nonempty explicit caller records; author-finished alone is not
completed. IDs must exist, maps must be disjoint and generation hash must match.
Refuse stale-generation state; do not migrate it by same-name lot inference.

Decision schema 1, kind `lint-reviewed-resolutions`:
`{schema_version, kind, rows}`. Each row has string fields
`id, status, decision, conditions, exceptions, source_ref, approval_ref`.
IDs are unique. Only exact `Accepted` rows with nonempty source/approval refs
enter CSV; keep Proposed/Superseded/Rejected excluded and report their counts.
The host prepares this normalized JSON from applicable project canon under
explicit permissions; no automatic Markdown acceptance parser or author
self-promotion. Accepted is caller provenance, not independently certified by
the helper. Conflicting precedents return to the lead before application.

CSV header is those seven fields in that order. Preserve field text verbatim
with standard CSV quoting, UTF-8 and deterministic row-ID order, including
multiline conditions/exceptions. This is a **read-only shared snapshot**:
workers never append. Missing project decisions do not become invented rows.

## Conflict graph and deterministic wave

Validate lots manifest kind/schema, IDs, file ownership and edge references.
Use **all** cross-lot boundaries in `edge_registry`, including unverified ones,
not merely source-verified optimization affinity. Recompute owners/endpoints
and cross-check boundary IDs; missing/inconsistent references fail closed.
Writable-file overlap also conflicts. Shared read-only context alone does not.
An edge to context with no write owner is a review boundary, not a fake lot.

Exclude active/completed IDs. Exclude every active lot's conflicting neighbors;
completed lots release scheduling conflicts but do not refresh graph evidence.
Greedily select remaining mutually nonconflicting lots by ascending eligible
conflict degree, descending workload, then lot ID, stopping at the requested cap.
Return selected IDs and exclusion reasons; do not claim a maximum independent
set or prove independence from missing graph edges.

Output schema 1, kind `lint-campaign-wave`: input hashes, CSV hash, options,
selected lots, excluded reasons, active/completed IDs, manual queue count,
coverage/review gates and common snapshot/action-request references.
Wave ID is SHA-256 of canonical input hashes, CSV bytes hash, options and selected
IDs; exclude timestamps. Protect input/output/script aliases, distinct outputs,
and recheck input hashes before atomic publication; do not overwrite foreign
artifacts. No source writes, subprocesses, network calls or graph regeneration.

## Host execution pattern and acceptance

Host reviews inherited partial coverage and boundary risks before approving any
wave. Unknown graph scope forbids independence certification; serial fallback
requires lead approval, not an automatic bypass. The 22 manual units remain
manual. No eligible wave means explain active/completed/conflicts; never loop
recollection on untouched code.

After explicit approval, native workers receive exclusive files, read-only
context, CSV snapshot/hash, project policy, boundaries and validation contract.
They return per-lot decision proposals as JSON, never edit the shared registry.
The lead validates/integrates, reviews proposals and updates canonical decisions
between waves. Then refresh global inventory and assess MCP freshness under
project authority; never auto-rebuild an index. New lots require new generation
state. Reserve project-specific validation/build slots centrally.

Tests cover all-edge conflicts, active neighbors, stale/completed state, unknown
IDs, overlaps, shared context, deterministic selection/ID, CSV multiline fidelity,
Accepted filtering and output collisions. Simulate adapter capabilities,
including missing Context Mode; do not claim native cross-client execution.
Replay the actual saved 12-lot manifest locally with empty matching state and
synthetic/caller-approved resolutions; verify 598 assigned/22 manual accounting
without launching workers. Public fixtures contain no private policy/captures.
