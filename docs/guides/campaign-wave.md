# Plan a portable correction wave

The repository skill is
[lint-workgraph-campaign](../../.agents/skills/lint-workgraph-campaign/SKILL.md).
Keep the full checkout: it uses existing sibling JSON/hash/publication helpers.
It prepares native action requests but **does not launch agents or fix sources**.
The [host adapter](../../.agents/skills/lint-workgraph-campaign/references/host-adapter.md)
explains catalogue checks, the concrete Context Mode invocation pattern,
manual skill discovery, and explicit host approval/lease handoff.

## Offline command

Prepare input files in an existing authorized campaign directory, then run:

```powershell
python -S -B ops/scripts/campaign-wave.py `
  --lots .tmp/correction-lots.json `
  --state .tmp/campaign-state.json `
  --resolutions .tmp/campaign-resolutions.json `
  --output .tmp/campaign-wave.json `
  --csv .tmp/campaign-accepted.csv `
  --max-workers 3
```

The default cap is 1. This is a planning cap, not fixed concurrency or dispatch
authorization. The helper is stdlib-only and never performs subprocess, network,
backend, source-edit, state-write, lease-reservation or index-rebuild operations.
Exit 0 means files were published; exit 2 means validation/publication failed.

State is schema 1, kind `lint-campaign-state`:

```json
{
  "schema_version": 1,
  "kind": "lint-campaign-state",
  "lots_sha256": "<SHA-256 of the exact lots file bytes>",
  "active": {},
  "completed": {}
}
```

For an active ID, supply `{"lease_id":"...","owner_ref":"..."}`. For completed
work, supply `{"lead_acceptance_ref":"...","integration_ref":"..."}`. References
must be nonempty caller evidence; author-finished alone is not completion.
IDs must exist, maps must be disjoint and active lease IDs unique.
Stale generations are refused, never automatically migrated by lot name.

No applicable project decisions supplied? Use an explicitly empty registry:

```json
{"schema_version":1,"kind":"lint-reviewed-resolutions","rows":[]}
```

The lead may normalize project-approved rows with seven string fields:
`id,status,decision,conditions,exceptions,source_ref,approval_ref`. Only exact
`Accepted` with nonempty source/approval references enters the CSV. Other supported
statuses (`Proposed`, `Superseded`, `Rejected`) are excluded and counted. Unknown
statuses, duplicate IDs and malformed rows fail. No acceptance Markdown parser,
invented precedent or author self-promotion is provided.

CSV is UTF-8 with those seven columns, standard quoting and deterministic ID
order. Commas, quotes, CR/LF and multiline text round-trip verbatim. A header-only
CSV explicitly means zero supplied accepted rows, not absence of canonical policy.
Workers treat it as a **shared read-only snapshot**; this logical contract is not
an OS permission grant. Per-lot decision proposals stay separate for lead review
and integration between waves. Missing CSV precedents do not override project
instructions, skills, permission rules or decision canon.

## Selection and output

The helper validates IDs, units, accounting, writable file registry and all edge
endpoints. It recomputes every boundary/internal reference and refuses missing or
inconsistent IDs. Conflicts include **every** cross-lot edge qualification,
including backend-observed facts, plus writable overlaps. Shared read-only
context alone creates no conflict; an unowned context endpoint is not a fake lot.

Active and completed lots are excluded. Neighbors of active lots are blocked.
Completed lots release known scheduling conflicts but not graph review/freshness
gates. Candidates are statically ordered by ascending conflict degree within the
eligible set, descending workload, then ID. A greedy scan selects mutually
nonconflicting lots up to the cap. It is not a maximum-independent-set solver
and does not certify independence from absent edges or unknown graph scope.

`lint-campaign-wave` JSON contains input hashes, CSV hash/reference, options,
selected/excluded IDs with reasons, known conflict witnesses, manual count,
inherited coverage gates and per-lot action requests. Its wave ID hashes canonical
input hashes, CSV hash, options and selected IDs; timestamps and filesystem paths
are not identity inputs. Request IDs combine the wave ID and lot ID.

The plan is **not a reservation**. Multiple planners can select the same files.
Before actual native calls, the lead must refresh/recheck state and hashes,
approve partial-coverage/boundary risks and acquire exclusive project-authorized
leases. Honor operator pauses, native harness/Ensemble rules and validation slots.
Without native launch capability return requests for explicit parent/manual action;
without Context Mode report BLOCKED and ask for an alternative, no silent dump.
No eligible wave means explain exclusions, not repeated recollection.
Even a serial fallback requires lead approval under unknown scope.

After lead verification, acceptance and integration, update state and canonical
decisions under project authority. Refresh diagnostics/lots when appropriate and
create reviewed state for the new lots hash. Never automatically rebuild an MCP
index or equate unchanged names with accepted work in a new generation.

## Publication and validation limits

All three JSON inputs are strictly parsed and hashed from bounded buffers
(64 MiB per input), then hash-rechecked before publication. Output paths must be
distinct from inputs, each other and loaded helper scripts, including hardlinks.
Existing JSON must be a recognized wave; an existing CSV must be hash-bound to
that prior wave, otherwise replacement is refused. Output parents must exist.
Both files are staged first, but replacements are individually atomic: a second
replacement failure can leave a new wave and old CSV. Nonzero status is not a
successful pair; inspect/recover it under lead authority before retrying.

```powershell
python -S -B -m unittest discover -s ops/tests -p test_campaign_wave.py -q
python -S -B -m unittest discover -s ops/tests -p "test_*.py" -q
```

Fixtures test conflict qualifications, active/completed/stale state, overlaps,
shared context, deterministic identity, CSV fidelity/filtering, collisions,
input drift, atomic failures, skill references and simulated capability records.
They do not prove real native execution on any client. The authorized real replay
uses the saved lots, empty matching state and an explicitly empty decision registry,
without correction workers or private decisions copied into public fixtures.

## Observed real planning replay

The parent ran the actual helper through Context Mode against the saved twelve
lots. With cap six it selected `lot-007`, `lot-004`, `lot-006`, `lot-012`,
`lot-003`, `lot-011` in 0.144 seconds; the default cap selected only `lot-007`.
All 24 known lot-conflict pairs were retained, versus only 11 pairs if filtering
to source-verified links. No selected pair shared a known boundary.

The replay preserved 598 assigned units, 22 manual units and 131 file owners.
Inputs remained unchanged; the six-lot wave ID matched the author's repeat.
The CSV hash matched its published bytes and contained zero supplied decision
rows. All 287 offline tests passed, including simulated capability records.
No leases, native launches, source corrections or client-runtime proof resulted.
Independent correctness review passed after checking the implementation and
replaying saved inputs in memory against the parent's conflict/accounting oracle.
