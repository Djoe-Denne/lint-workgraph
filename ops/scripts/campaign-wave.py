#!/usr/bin/env python3
"""Prepare a generation-bound campaign wave and read-only decision CSV; never execute."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys


SPEC = importlib.util.spec_from_file_location("_campaign_guards", Path(__file__).with_name("clippy-constraint-plan.py"))
guards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guards)
require, fields, text = guards.require, guards.fields, guards.text
MAX_INPUT_BYTES = 64 * 1024 * 1024
CSV_FIELDS = ("id", "status", "decision", "conditions", "exceptions", "source_ref", "approval_ref")
RESOLUTION_STATUSES = ("Accepted", "Proposed", "Superseded", "Rejected")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(path):
    """Parse and hash exactly the same bounded bytes."""
    with path.open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    require(len(raw) <= MAX_INPUT_BYTES, "input exceeds 64 MiB byte budget")
    return guards.json_document(raw.decode("utf-8")), digest_bytes(raw)


def array(value, label):
    require(isinstance(value, list), label + ": expected array")
    return value


def ids(value, label):
    array(value, label)
    for item in value:
        text(item, label)
    require(len(value) == len(set(value)), label + ": duplicate ID/path")
    return set(value)


def capability_status(record):
    """Interpret host-reported checks, not host APIs or independently verified grants."""
    fields(record, ["context_mode", "agent_launch", "permissions_ref", "project_rules_ref"], "host record")
    for key in ("permissions_ref", "project_rules_ref"):
        text(record[key], key)
    for key in ("context_mode", "agent_launch"):
        entry = fields(record[key], ["available", "tool", "evidence_ref"], key)
        require(type(entry["available"]) is bool, key + ": available must be boolean")
        text(entry["evidence_ref"], key + " evidence")
        if entry["available"]:
            text(entry["tool"], key + " actual catalogue tool")
        else:
            require(entry["tool"] is None or isinstance(entry["tool"], str), key + ": invalid tool")
    if not record["context_mode"]["available"]:
        return {"status": "BLOCKED", "execution_available": False,
                "reason": "Context Mode missing; request an explicit alternative, no silent fallback"}
    return {"status": "approval_and_lease_required" if record["agent_launch"]["available"] else "requests_only",
            "execution_available": record["agent_launch"]["available"],
            "reason": "Host checks are caller evidence; no approval, lease or launch is performed here"}


def resolution_csv(registry):
    guards.envelope(registry, "lint-reviewed-resolutions", ["rows"])
    rows, seen, counts = [], set(), Counter()
    for row in array(registry["rows"], "resolution rows"):
        fields(row, CSV_FIELDS, "resolution")
        require(all(isinstance(row[k], str) for k in CSV_FIELDS), "resolution fields must be strings")
        identifier = text(row["id"], "resolution ID")
        require(identifier not in seen, "duplicate resolution ID")
        seen.add(identifier)
        require(row["status"] in RESOLUTION_STATUSES, "unsupported resolution status")
        counts[row["status"]] += 1
        if row["status"] == "Accepted":
            text(row["source_ref"], "Accepted source reference")
            text(row["approval_ref"], "Accepted approval reference")
            rows.append(row)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_FIELDS)
    for row in sorted(rows, key=lambda r: r["id"]):
        writer.writerow([row[key] for key in CSV_FIELDS])
    return buffer.getvalue(), {
        "accepted_rows": len(rows),
        "excluded_status_counts": {s: counts[s] for s in RESOLUTION_STATUSES if s != "Accepted"},
        "authority": "caller-normalized provenance, not independent certification or permission",
    }


def conflict_graph(manifest):
    guards.envelope(manifest, "lint-work-lots", ["lots", "files", "units", "unresolved_queue",
                                               "edge_registry", "accounting", "inherited"])
    lots, owners, unit_ids = {}, defaultdict(set), set()
    for lot in array(manifest["lots"], "lots"):
        fields(lot, ["id", "writable_files", "readonly_context", "strict_unit_ids", "workload",
                     "boundary_edge_ids", "internal_edge_ids"], "lot")
        identifier = text(lot["id"], "lot ID")
        require(identifier not in lots, "duplicate lot ID")
        writable = ids(lot["writable_files"], "writable files")
        readonly = ids(lot["readonly_context"], "read-only context")
        require(writable and not writable & readonly, "empty writable lot or writable/read-only overlap")
        units = ids(lot["strict_unit_ids"], "strict unit IDs")
        require(not unit_ids & units, "strict unit assigned twice")
        require(guards.number(lot["workload"], 1) and lot["workload"] == len(units), "lot workload mismatch")
        unit_ids.update(units)
        ids(lot["boundary_edge_ids"], "boundary IDs")
        ids(lot["internal_edge_ids"], "internal IDs")
        for path in writable:
            owners[path].add(identifier)
        lots[identifier] = lot
    files = {}
    for entry in array(manifest["files"], "file registry"):
        fields(entry, ["path", "source_status", "write_owner"], "file")
        path = text(entry["path"], "file path")
        require(path not in files, "duplicate file registry path")
        require(entry["write_owner"] is None or entry["write_owner"] in lots, "unknown registry write owner")
        require((entry["write_owner"] in owners[path]) if owners[path] else entry["write_owner"] is None,
                "file registry/lot ownership mismatch")
        if owners[path]:
            require(entry["source_status"] == "verified_current", "writable file not verified_current")
            require(not path.startswith(("/", "\\")) and "\\" not in path and ":" not in path
                    and all(p not in ("", ".", "..") and not p.endswith((".", " ")) for p in path.split("/")),
                    "noncanonical writable path")
        files[path] = entry
    require(set(owners) <= files.keys(), "missing writable file registry entry")
    for lot in lots.values():
        require(set(lot["readonly_context"]) <= files.keys(), "unknown read-only context path")
    units = {}
    for unit in array(manifest["units"], "unit registry"):
        fields(unit, ["id", "lot_id", "owner_path"], "unit")
        identifier = text(unit["id"], "unit ID")
        require(identifier not in units, "duplicate unit registry ID")
        if unit["lot_id"] is not None:
            require(unit["lot_id"] in lots and identifier in lots[unit["lot_id"]]["strict_unit_ids"]
                    and unit["owner_path"] in lots[unit["lot_id"]]["writable_files"], "unit owner mismatch")
        else:
            require(unit["owner_path"] is None, "manual unit has a write owner")
        units[identifier] = unit
    queued = []
    for entry in array(manifest["unresolved_queue"], "manual queue"):
        queued.append(text(fields(entry, ["unit_id"], "manual entry")["unit_id"], "manual unit ID"))
    queued_set = ids(queued, "manual unit IDs")
    require(not queued_set & unit_ids and unit_ids | queued_set == units.keys(), "unit accounting mismatch")
    require(all(units[key]["lot_id"] is not None for key in unit_ids), "assigned unit has no lot owner")
    require(all(units[key]["lot_id"] is None for key in queued_set), "manual unit assigned to a lot")
    account = fields(manifest["accounting"], ["assigned_units", "queued_units", "strict_units", "writable_files"],
                     "accounting")
    for name, expected in (("assigned_units", len(unit_ids)), ("queued_units", len(queued)),
                           ("strict_units", len(units)), ("writable_files", len({p for p, o in owners.items() if o}))):
        require(guards.number(account[name]) and account[name] == expected, "manifest accounting mismatch: " + name)

    neighbors = {key: set() for key in lots}
    witnesses = defaultdict(lambda: {"edge_ids": set(), "overlap_files": set()})

    def connect(a, b, edge_id=None, path=None):
        if a == b:
            return
        neighbors[a].add(b)
        neighbors[b].add(a)
        record = witnesses[tuple(sorted((a, b)))]
        if edge_id is not None:
            record["edge_ids"].add(edge_id)
        if path is not None:
            record["overlap_files"].add(path)

    for path, claimants in owners.items():
        for a in sorted(claimants):
            for b in sorted(claimants):
                if a < b:
                    connect(a, b, path=path)
    boundary, internal, edges = defaultdict(set), defaultdict(set), {}
    for edge in array(manifest["edge_registry"], "edge registry"):
        fields(edge, ["id", "origin_path", "destination_path", "qualification"], "edge")
        identifier = text(edge["id"], "edge ID")
        require(identifier not in edges, "duplicate edge ID")
        a, b = edge["origin_path"], edge["destination_path"]
        require(isinstance(a, str) and isinstance(b, str) and a in files and b in files, "unknown edge endpoint")
        text(edge["qualification"], "edge qualification")
        edges[identifier] = edge
        left, right = owners[a], owners[b]
        for x in left:
            for y in right:
                connect(x, y, edge_id=identifier)
        for owner in left | right:
            if left == right == {owner}:
                internal[owner].add(identifier)
            else:
                boundary[owner].add(identifier)
    for key, lot in lots.items():
        require(set(lot["boundary_edge_ids"]) == boundary[key], "missing/inconsistent boundary IDs: " + key)
        require(set(lot["internal_edge_ids"]) == internal[key], "missing/inconsistent internal IDs: " + key)
    conflicts = [{"lots": list(pair), "edge_ids": sorted(proof["edge_ids"]),
                  "overlap_files": sorted(proof["overlap_files"])} for pair, proof in sorted(witnesses.items())]
    return lots, neighbors, conflicts


def validate_state(state, lots_hash, lots):
    guards.envelope(state, "lint-campaign-state", ["lots_sha256", "active", "completed"])
    guards.sha(state["lots_sha256"])
    require(state["lots_sha256"] == lots_hash, "stale state generation; explicit new state required")
    for key, names in (("active", ("lease_id", "owner_ref")),
                       ("completed", ("lead_acceptance_ref", "integration_ref"))):
        require(isinstance(state[key], dict), key + ": expected ID map")
        for identifier, entry in state[key].items():
            require(identifier in lots, "unknown " + key + " lot ID")
            fields(entry, names, key + " entry")
            for name in names:
                text(entry[name], name)
    require(not state["active"].keys() & state["completed"].keys(), "active/completed IDs overlap")
    leases = [entry["lease_id"] for entry in state["active"].values()]
    require(len(leases) == len(set(leases)), "duplicate active lease ID")


def plan(manifest, state, registry, input_hashes, max_workers=1, csv_ref="accepted.csv"):
    require(guards.number(max_workers, 1), "max-workers must be positive")
    fields(input_hashes, ["lots", "state", "resolutions"], "input hashes")
    for value in input_hashes.values():
        guards.sha(value)
    lots, neighbors, conflicts = conflict_graph(manifest)
    validate_state(state, input_hashes["lots"], lots)
    csv_text, resolution_summary = resolution_csv(registry)
    csv_hash = digest_bytes(csv_text.encode("utf-8"))
    active, completed = set(state["active"]), set(state["completed"])
    excluded, eligible = {}, set()
    for key in sorted(lots):
        if key in active:
            excluded[key] = {"reason": "active", "lease": state["active"][key]}
        elif key in completed:
            excluded[key] = {"reason": "completed", "acceptance": state["completed"][key]}
        elif neighbors[key] & active:
            excluded[key] = {"reason": "conflicts_with_active", "lot_ids": sorted(neighbors[key] & active)}
        else:
            eligible.add(key)
    order = sorted(eligible, key=lambda key: (len(neighbors[key] & eligible), -lots[key]["workload"], key))
    selected = []
    for key in order:
        blockers = neighbors[key] & set(selected)
        if blockers:
            excluded[key] = {"reason": "conflicts_with_selected", "lot_ids": sorted(blockers)}
        elif len(selected) == max_workers:
            excluded[key] = {"reason": "planning_cap"}
        else:
            selected.append(key)
    options = {"max_workers": max_workers, "plan_only": True}
    identity = {"input_hashes": input_hashes, "csv_sha256": csv_hash, "options": options, "selected_lot_ids": selected}
    wave_id = digest_bytes(canonical(identity).encode("utf-8"))
    requests = [{
        "id": wave_id + ":" + key, "lot_id": key, "status": "awaiting_lead_approval_and_exclusive_lease",
        "writable_files": lots[key]["writable_files"], "readonly_context": lots[key]["readonly_context"],
        "strict_unit_ids": lots[key]["strict_unit_ids"], "workload": lots[key]["workload"],
        "boundary_edge_ids": lots[key]["boundary_edge_ids"], "review_tasks": lots[key].get("review_tasks", []),
        "common_snapshot": {"csv_ref": csv_ref, "sha256": csv_hash, "access": "read_only_logical_contract"},
        "requires_host_context": ["target_project_root", "project_rules_ref", "permissions_ref",
                                 "capability_evidence", "validation_contract", "exclusive_lease_ref"],
        "decision_proposals": "separate per-lot JSON; lead reviews and merges between waves",
    } for key in selected]
    return {
        "schema_version": 1, "kind": "lint-campaign-wave", "wave_id": wave_id, **identity,
        "execution": "not_available_in_offline_helper", "leases_reserved": False,
        "selected_lots": selected, "excluded": excluded, "active_ids": sorted(active), "completed_ids": sorted(completed),
        "selection_order": order, "conflicts": conflicts, "conflict_pair_count": len(conflicts),
        "manual_queue_count": manifest["accounting"]["queued_units"], "accounting": manifest["accounting"],
        "resolution_summary": resolution_summary, "common_snapshot": {"csv_ref": csv_ref, "sha256": csv_hash},
        "action_requests": requests, "empty_wave_reason": None if selected else
        ("no_lots" if not lots else "all_lots_active_completed_or_blocked_by_active"),
        "coverage_review_gates": {
            "inherited": manifest["inherited"], "limitations": manifest.get("limitations", []),
            "required": ["Lead reviews partial coverage, all boundaries and unknown scope before approval.",
                         "Refresh/recheck state and hashes, then acquire exclusive leases before native launch.",
                         "No maximum independent set or independence certification; no automatic serial bypass.",
                         "Completed means lead accepted and integrated; completion does not refresh this graph.",
                         "Manual units stay manual; no index rebuild, correction or worker launch performed."],
        },
    }, csv_text


def positive(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("lots", "state", "resolutions", "output", "csv"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--max-workers", type=positive, default=1)
    args = parser.parse_args(argv)
    try:
        paths = {key: getattr(args, key).resolve(strict=True) for key in ("lots", "state", "resolutions")}
        output, csv_path = args.output.resolve(), args.csv.resolve()
        protected = [*paths.values(), Path(__file__).resolve(), Path(guards.__file__).resolve(),
                     Path(guards._RANGES.__file__).resolve()]
        # Fail before reading inputs; publish() repeats the two-output alias guards.
        require(output != csv_path and output.parent.is_dir() and csv_path.parent.is_dir(), "invalid output paths")
        for target in (output, csv_path):
            require(not target.exists() or target.is_file(), "output must be a regular file")
            require(all(target != source and not (target.exists() and source.exists()
                        and target.samefile(source)) for source in protected), "output/input/script alias")
        require(not (output.exists() and csv_path.exists() and output.samefile(csv_path)), "outputs alias")
        previous = None
        if output.exists():
            previous, _ = snapshot(output)
            guards.envelope(previous, "lint-campaign-wave", ["csv_sha256"])
        if csv_path.exists():
            require(previous is not None and guards.sha(previous["csv_sha256"]) == guards.digest(csv_path),
                    "refusing foreign/unbound CSV overwrite")
        documents, hashes = {}, {}
        for key, path in paths.items():
            documents[key], hashes[key] = snapshot(path)
        wave, csv_text = plan(documents["lots"], documents["state"], documents["resolutions"], hashes,
                              args.max_workers, str(csv_path))
        wave["input_refs"] = {key: str(path) for key, path in paths.items()}
        for request in wave["action_requests"]:
            request["provenance_snapshot"] = {"lots_ref": str(paths["lots"]), "sha256": hashes["lots"]}
        guards.publish([(output, json.dumps(wave, indent=2, sort_keys=True, ensure_ascii=False,
                                            allow_nan=False) + "\n"), (csv_path, csv_text)],
                       protected, {paths[key]: value for key, value in hashes.items()})
        print(f"Planned {len(wave['selected_lots'])} lots; {wave['conflict_pair_count']} conflict pairs; "
              f"{wave['manual_queue_count']} manual units; CSV {wave['resolution_summary']['accepted_rows']} rows; "
              f"wave {wave['wave_id']}; no launch or lease reserved")
        return 0
    except (guards.Invalid, OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        print("campaign-wave: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
