#!/usr/bin/env python3
"""Offline LPT and bounded cut refinement for proposed correction-file lots."""

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


SPEC = importlib.util.spec_from_file_location("_partition_graph_helpers", Path(__file__).with_name("lint-workgraph.py"))
graph_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = graph_tool
SPEC.loader.exec_module(graph_tool)
guards = graph_tool.planner
require, fields, text = guards.require, guards.fields, guards.text
MAX_GRAPH_BYTES = 256 * 1024 * 1024
MAX_IMPROVEMENTS = 100


def canonical_file(path):
    """Snapshot spelling only; never resolve a source path on the filesystem."""
    return (isinstance(path, str) and bool(path) and not path.startswith(("/", "\\"))
            and "\\" not in path and ":" not in path
            and all(ord(c) >= 32 and ord(c) != 127 for c in path)
            and all(p not in ("", ".", "..") and not p.endswith((".", " ")) for p in path.split("/")))


def strings(value, label):
    require(isinstance(value, list) and all(isinstance(v, str) and v for v in value), label + " must be strings")
    require(len(value) == len(set(value)), label + " contains duplicates")
    return value


def prepare(graph):
    fields(graph, ["schema_version", "kind", "status", "inventory", "accounting", "diagnostics", "work_graph"],
           "input graph")
    require(type(graph["schema_version"]) is int and graph["schema_version"] == 1
            and graph["kind"] == "lint-workgraph" and graph["status"] in ("partial", "complete"),
            "expected accepted lint-workgraph schema 1")
    records, _ = graph_tool.inventory_records(graph["inventory"])
    account = fields(graph["accounting"], ["retained_records", "strict_union", "sonar_raw_keys"], "accounting")
    require(type(account["retained_records"]) is int and account["retained_records"] == len(records)
            and account["strict_union"] == graph["inventory"]["counts"]["strict_union"]
            and account["sonar_raw_keys"] == graph["inventory"]["counts"]["sonar_raw_keys"],
            "graph diagnostic accounting mismatch")
    work = fields(graph["work_graph"], ["nodes", "edges", "proposed_groups", "coverage"], "work graph")
    for container in (graph, work):
        for key in ("constraints", "hard_constraints", "hard_edges", "hard_must_coedit"):
            require(not container.get(key), "unsupported nonempty hard-constraint input: " + key)
    require(not work["coverage"].get("hard_edges"), "unsupported hard-edge count")
    for group in work["proposed_groups"]:
        require(not group.get("constraint_ids"), "unsupported approved hard grouping")
        require(not group.get("approved") and not group.get("approval")
                and group.get("readiness") not in ("approved", "dispatch_ready"),
                "unsupported group approval")
    rows = {}
    for row in work_array(graph["diagnostics"], "diagnostics"):
        fields(row, ["key", "record", "files", "localization_status"], "diagnostic")
        key = row["key"]
        require(key in records and key not in rows, "unknown/duplicate graph diagnostic")
        require(graph_tool.canonical(row["record"]) == graph_tool.canonical(records[key]),
                "graph/inventory diagnostic provenance mismatch")
        strings(row["files"], "diagnostic file candidates")
        rows[key] = row
    require(rows.keys() == records.keys(), "every original record must appear exactly once")
    node_rows, by_path, by_case = [], defaultdict(list), defaultdict(set)
    represented = defaultdict(set)
    for node in work_array(work["nodes"], "file nodes"):
        fields(node, ["path", "source_status", "diagnostic_keys"], "file node")
        path = text(node["path"], "node path")
        keys = strings(node["diagnostic_keys"], "node diagnostic keys")
        require(set(keys) <= records.keys(), "unknown node diagnostic")
        represented[path].update(keys)
        by_path[path].append(node)
        by_case[path.casefold()].add(path)
        node_rows.append(node)
    expected = defaultdict(set)
    for key, row in rows.items():
        for path in row["files"] or ["unlocated:" + key]:
            expected[path].add(key)
    require(all(represented[path] == keys for path, keys in expected.items())
            and all(keys == expected.get(path, set()) for path, keys in represented.items()),
            "graph nodes and diagnostic file references disagree")
    eligible, files = set(), {}
    for path, nodes in sorted(by_path.items()):
        reason = []
        if not canonical_file(path):
            reason.append("Noncanonical/unresolved snapshot spelling; no alias normalization")
        if len(nodes) != 1 or len(by_case[path.casefold()]) != 1:
            reason.append("Snapshot path/case identity is not unique")
        if len(nodes) != 1 or nodes[0]["source_status"] != "verified_current":
            reason.append("File is not verified_current in the input snapshot")
        if not reason:
            eligible.add(path)
        files[path] = {"path": path, "source_status": nodes[0]["source_status"] if len(nodes) == 1 else "ambiguous",
                       "eligibility_reasons": reason, "diagnostic_keys": sorted(represented[path])}
    aliases, matched_sonar = {}, set()
    for match in graph["inventory"]["matches"]:
        c, s = "clippy:" + match["clippy_id"], "sonar:" + match["sonar_id"]
        aliases[c] = s
        matched_sonar.add(s)
    units = {}
    for key in sorted(records):
        if key in matched_sonar:
            continue
        keys = [key] + ([aliases[key]] if key in aliases else [])
        candidates = [set(rows[k]["files"]) for k in keys]
        all_files = sorted(set().union(*candidates))
        reasons = []
        if any(len(c) != 1 for c in candidates):
            reasons.append("Missing or multiple file candidates for a provenance record")
        if len(all_files) != 1 or any(c != candidates[0] for c in candidates[1:]):
            reasons.append("Provenance records disagree on one file owner")
        if len(all_files) == 1 and all_files[0] not in eligible:
            reasons.extend(files.get(all_files[0], {}).get("eligibility_reasons", ["File node missing"]))
        owner = all_files[0] if not reasons and len(all_files) == 1 else None
        units[key] = {"id": key, "diagnostic_keys": keys, "file_candidates": all_files,
                      "candidates_by_diagnostic": {k: rows[k]["files"] for k in keys},
                      "owner_path": owner, "lot_id": None, "reasons": sorted(set(reasons))}
    require(len(units) == account["strict_union"], "strict-unit population mismatch")
    flattened = [key for unit in units.values() for key in unit["diagnostic_keys"]]
    require(len(flattened) == len(records) and set(flattened) == records.keys(), "lost/duplicated provenance record")
    weights = Counter(unit["owner_path"] for unit in units.values() if unit["owner_path"] is not None)
    edges, pairs, stats = {}, set(), Counter()
    for edge in work_array(work["edges"], "edges"):
        fields(edge, ["id", "origin_path", "destination_path", "class", "qualification"], "edge")
        identifier = text(edge["id"], "edge id")
        require(identifier not in edges, "duplicate edge id")
        require(edge["class"] == "candidate_dependency", "unsupported hard/unknown edge class")
        origin, destination = edge["origin_path"], edge["destination_path"]
        require(origin in by_path and destination in by_path, "edge references a missing node")
        edges[identifier] = edge
        if edge["qualification"] != "source_verified":
            stats["excluded_unverified_observations"] += 1
        elif origin == destination:
            stats["excluded_self_loops"] += 1
        elif origin not in weights or destination not in weights:
            stats["excluded_nonwritable_endpoint_observations"] += 1
        else:
            stats["eligible_observations"] += 1
            pairs.add(tuple(sorted((origin, destination))))
    adjacency = {path: {} for path in weights}
    for a, b in sorted(pairs):
        adjacency[a][b] = adjacency[b][a] = 1
    stats["input_edges"] = len(edges)
    stats["affinity_pairs"] = len(pairs)
    stats["duplicate_or_reverse_observations"] = stats["eligible_observations"] - len(pairs)
    return {"records": records, "rows": rows, "files": files, "units": units,
            "weights": dict(weights), "edges": edges, "adjacency": adjacency, "affinity": dict(stats)}


def work_array(value, label):
    require(isinstance(value, list), label + " must be an array")
    return value


def neighbor_weights(adjacency, owners):
    result = {}
    for path, neighbors in adjacency.items():
        counts = Counter()
        for neighbor, weight in neighbors.items():
            counts[owners[neighbor]] += weight
        result[path] = counts
    return result


def move_cut_delta(path, target, owners, by_lot):
    return by_lot[path][owners[path]] - by_lot[path][target]


def swap_cut_delta(a, b, owners, by_lot, adjacency):
    return (move_cut_delta(a, owners[b], owners, by_lot)
            + move_cut_delta(b, owners[a], owners, by_lot) + 2 * adjacency[a].get(b, 0))


def metrics(weights, adjacency, owners, parts, capacity):
    loads = [0] * parts
    for path, weight in weights.items():
        loads[owners[path]] += weight
    cut = sum(weight for a, neighbors in adjacency.items() for b, weight in neighbors.items()
              if a < b and owners[a] != owners[b])
    excess = [max(0, load - capacity) for load in loads]
    total = sum(loads)
    return {"loads": loads, "capacity": capacity, "weighted_cut": cut,
            "overload": sum(excess), "squared_overload": sum(v * v for v in excess),
            "sum_squared_loads": sum(v * v for v in loads),
            "score": [sum(v * v for v in excess), cut, sum(v * v for v in loads)],
            "min_load": min(loads, default=0), "max_load": max(loads, default=0),
            "mean_load": total / parts if parts else 0,
            "imbalance_max_over_mean": max(loads) * parts / total if total else 0}


def optimize(weights, adjacency, parts=None, target=50, max_improvements=MAX_IMPROVEMENTS):
    """LPT plus best strict improvement; candidate evaluation is O(1)."""
    started = time.monotonic()
    require(type(target) is int and target > 0, "target issues must be positive")
    require(parts is None or type(parts) is int and parts > 0, "parts must be positive")
    require(all(type(w) is int and w > 0 for w in weights.values()), "atoms need positive integer weights")
    paths, total = sorted(weights), sum(weights.values())
    if not total:
        empty = metrics(weights, adjacency, {}, 0, 0)
        return {"owners": {}, "parts": 0, "capacity": 0, "baseline": empty, "final": empty,
                "baseline_owners": {}, "steps": [], "stop_reason": "no_assignable_work",
                "elapsed_seconds": time.monotonic() - started}
    k = min(len(paths), (total + target - 1) // target) if parts is None else parts
    require(k <= len(paths), "parts exceeds positive-work file atoms")
    capacity = max(max(weights.values()), (6 * total + 5 * k - 1) // (5 * k))
    owners, loads, counts = {}, [0] * k, [0] * k
    for path in sorted(paths, key=lambda p: (-weights[p], p)):
        lot = min(range(k), key=lambda i: (loads[i], i))
        owners[path] = lot
        loads[lot] += weights[path]
        counts[lot] += 1
    baseline_owners = dict(owners)
    baseline = metrics(weights, adjacency, owners, k, capacity)
    current = tuple(baseline["score"])
    by_lot = neighbor_weights(adjacency, owners)
    steps, stop = [], "max_accepted_improvements"

    def candidate_score(a, b, new_a, new_b, cut_delta):
        old_a, old_b = loads[a], loads[b]
        overload_delta = sum(max(0, v - capacity) ** 2 for v in (new_a, new_b)) - sum(
            max(0, v - capacity) ** 2 for v in (old_a, old_b))
        return (current[0] + overload_delta, current[1] + cut_delta,
                current[2] + new_a * new_a + new_b * new_b - old_a * old_a - old_b * old_b)

    def relocate(path, target):
        old, weight = owners[path], weights[path]
        for neighbor, affinity in adjacency[path].items():
            by_lot[neighbor][old] -= affinity
            by_lot[neighbor][target] += affinity
        loads[old] -= weight
        loads[target] += weight
        counts[old] -= 1
        counts[target] += 1
        owners[path] = target

    for _ in range(max_improvements):
        best = None
        for i, path in enumerate(paths):
            a, weight = owners[path], weights[path]
            if counts[a] > 1:
                for b in range(k):
                    if a == b:
                        continue
                    score = candidate_score(a, b, loads[a] - weight, loads[b] + weight,
                                            move_cut_delta(path, b, owners, by_lot))
                    option = (score, (path, 0, b), ("move", path, b))
                    if score < current and (best is None or option[:2] < best[:2]):
                        best = option
            for other in paths[i + 1:]:
                b, other_weight = owners[other], weights[other]
                if a == b:
                    continue
                score = candidate_score(a, b, loads[a] - weight + other_weight, loads[b] - other_weight + weight,
                                        swap_cut_delta(path, other, owners, by_lot, adjacency))
                option = (score, (path, 1, other), ("swap", path, other))
                if score < current and (best is None or option[:2] < best[:2]):
                    best = option
        if best is None:
            stop = "local_optimum"
            break
        score, _, action = best
        kind, path, other = action
        old = owners[path]
        if kind == "move":
            relocate(path, other)
            files, before, after = [path], [old], [other]
        else:
            target = owners[other]
            relocate(path, target)
            relocate(other, old)
            files, before, after = [path, other], [old, target], [target, old]
        steps.append({"kind": kind, "files": files, "from_parts": before, "to_parts": after,
                      "score_before": list(current), "score_after": list(score)})
        current = score
    final = metrics(weights, adjacency, owners, k, capacity)
    require(tuple(final["score"]) == current and all(v > 0 for v in final["loads"]),
            "incremental optimization invariant failed")
    require(tuple(final["score"]) <= tuple(baseline["score"]), "refinement worsened objective")
    return {"owners": owners, "parts": k, "capacity": capacity, "baseline": baseline, "final": final,
            "baseline_owners": baseline_owners, "steps": steps, "stop_reason": stop,
            "elapsed_seconds": time.monotonic() - started}


def manifest(graph, prepared, partition, graph_hash, parts=None, target=50):
    owners, units = partition["owners"], prepared["units"]
    lot_name = lambda i: f"lot-{i + 1:03d}"
    lots = [{"id": lot_name(i), "status": "proposed", "readiness": "review_required",
             "writable_files": [], "strict_unit_ids": [],
             "workload": 0, "readonly_context": set(), "internal_edge_ids": [], "boundary_edge_ids": [],
             "neighbor_lots": set(), "review_tasks": [], "oversized_files": []} for i in range(partition["parts"])]
    for path, owner in sorted(owners.items()):
        lots[owner]["writable_files"].append(path)
        lots[owner]["workload"] += prepared["weights"][path]
        if parts is None and prepared["weights"][path] > target:
            lots[owner]["oversized_files"].append({"path": path, "strict_units": prepared["weights"][path]})
    for unit in units.values():
        if unit["owner_path"] is not None:
            owner = owners[unit["owner_path"]]
            unit["lot_id"] = lot_name(owner)
            lots[owner]["strict_unit_ids"].append(unit["id"])
    for identifier, edge in sorted(prepared["edges"].items()):
        a, b = edge["origin_path"], edge["destination_path"]
        left, right = owners.get(a), owners.get(b)
        for owner in {x for x in (left, right) if x is not None}:
            lot = lots[owner]
            if left == right == owner:
                lot["internal_edge_ids"].append(identifier)
            else:
                lot["boundary_edge_ids"].append(identifier)
                for path in (a, b):
                    if path not in owners:
                        lot["readonly_context"].add(path)
                for neighbor in (left, right):
                    if neighbor is not None and neighbor != owner:
                        lot["neighbor_lots"].add(lot_name(neighbor))
    for lot in lots:
        keys = sorted(key for unit_id in lot["strict_unit_ids"] for key in units[unit_id]["diagnostic_keys"])
        unknown = [key for key in keys if prepared["rows"][key]["localization_status"] != "exact"]
        if unknown:
            lot["review_tasks"].append({"kind": "localization_review", "diagnostic_keys": unknown})
        if lot["boundary_edge_ids"]:
            lot["review_tasks"].append({"kind": "boundary_coordination", "edge_ids": lot["boundary_edge_ids"]})
        lot["review_tasks"].append({"kind": "pre_edit_revalidation",
                                   "reason": "Snapshot ownership only; validate current sources and correction scope before edits"})
        lot["readonly_context"] = sorted(lot["readonly_context"])
        lot["neighbor_lots"] = sorted(lot["neighbor_lots"])
        lot["strict_unit_ids"].sort()
    queued = [u["id"] for u in units.values() if u["owner_path"] is None]
    assigned = [identifier for lot in lots for identifier in lot["strict_unit_ids"]]
    require(not set(assigned) & set(queued) and len(assigned) == len(set(assigned))
            and set(assigned) | set(queued) == units.keys(), "strict units lost/duplicated across lots/queue")
    require(sum(lot["workload"] for lot in lots) == len(assigned), "lot workload accounting mismatch")
    writable = [path for lot in lots for path in lot["writable_files"]]
    require(len(writable) == len(set(writable)) == len(owners), "write ownership is not unique")
    for path, entry in prepared["files"].items():
        entry["write_owner"] = lot_name(owners[path]) if path in owners else None
        entry["strict_workload"] = prepared["weights"].get(path, 0)
        entry["role"] = "writable" if path in owners else "readonly_or_manual"
    return {
        "schema_version": 1, "kind": "lint-work-lots", "status": "proposed", "input_graph_sha256": graph_hash,
        "algorithm": {"name": "LPT_then_best_strict_move_swap", "capacity": partition["capacity"],
                      "objective": ["squared_excess_above_capacity", "distinct_verified_pair_cut", "sum_squared_loads"],
                      "max_accepted_improvements": MAX_IMPROVEMENTS, "accepted_improvements": len(partition["steps"]),
                      "stop_reason": partition["stop_reason"], "steps": partition["steps"],
                      "global_optimality": "not_claimed"},
        "options": {"requested_parts": parts, "target_issues": target if parts is None else None,
                    "effective_parts": partition["parts"]},
        "accounting": {"original_records": len(prepared["records"]), "strict_units": len(units),
                       "assigned_units": len(assigned), "queued_units": len(queued), "writable_files": len(owners),
                       "raw_sonar_keys": graph["inventory"]["counts"]["sonar_raw_keys"],
                       "exact_alias_pairs": len(graph["inventory"]["matches"]),
                       "context_only_nodes": sum(not f["diagnostic_keys"] for f in prepared["files"].values()),
                       "unowned_diagnostic_paths": sum(bool(f["diagnostic_keys"]) and f["write_owner"] is None
                                                       for f in prepared["files"].values()),
                       "semantic_defect_count": None},
        "baseline": partition["baseline"], "final": partition["final"], "affinity": prepared["affinity"],
        "baseline_file_owners": {path: lot_name(owner) for path, owner in sorted(partition["baseline_owners"].items())},
        "lots": lots, "units": [units[k] for k in sorted(units)], "original_records": prepared["records"],
        "diagnostic_context": {k: {name: row[name] for name in
                                  ("files", "localization_status", "attempt_outcome", "query_ids", "item_ids", "reasons")
                                  if name in row} for k, row in prepared["rows"].items()},
        "files": [entry for _, entry in sorted(prepared["files"].items())],
        "edge_registry": [edge for _, edge in sorted(prepared["edges"].items())],
        "unresolved_queue": [{"unit_id": identifier, "diagnostic_keys": units[identifier]["diagnostic_keys"],
                              "file_candidates": units[identifier]["file_candidates"],
                              "reasons": units[identifier]["reasons"]} for identifier in queued],
        "inherited": {"graph_status": graph["status"], "coverage": graph["work_graph"]["coverage"],
                      "limitations": graph.get("limitations", []),
                      "backend_warnings": graph.get("native_capture", {}).get("backend", {}).get("warnings", []),
                      "unresolved_observation_count": len(graph["work_graph"].get("unresolved_observations", []))},
        "limitations": ["Strict issue counts are workload proxies, not minutes or semantic defect counts.",
                        "Bounded local heuristic; not METIS, full Kernighan-Lin or global optimum.",
                        "Source-verified distinct writable pairs drive affinity; other observations remain coordination context.",
                        "No source path was dereferenced or compiler dot/case aliases guessed.",
                        "Inherited partial graph and unknown localization remain; proposed lots are not independent or dispatch-safe."],
    }


def render(result):
    def safe(v):
        return str(v).replace("\r", " ").replace("\n", " ").replace("`", "'").replace("<", "&lt;")
    a, b, f = result["accounting"], result["baseline"], result["final"]
    lines = ["# Proposed correction lots", "",
             f"- Input graph SHA-256: `{result['input_graph_sha256']}`; inherited status: "
             f"{result['inherited']['graph_status']}.",
             f"- {a['strict_units']} strict units: {a['assigned_units']} assigned, {a['queued_units']} manual; "
             f"{a['original_records']} original records and {a['raw_sonar_keys']} Sonar keys retained.",
             f"- {a['writable_files']} uniquely owned files; {a['context_only_nodes']} context-only nodes; "
             f"{a['unowned_diagnostic_paths']} unowned diagnostic paths.",
             f"- K={result['options']['effective_parts']} proposed lots, not worker concurrency; "
             f"target={result['options']['target_issues']}; balance capacity C={result['algorithm']['capacity']}.",
             f"- LPT loads: {b['loads']}; final loads: {f['loads']}.",
             f"- Weighted cut: {b['weighted_cut']} → {f['weighted_cut']}; overload: "
             f"{b['overload']} → {f['overload']}; max/mean imbalance: "
             f"{b['imbalance_max_over_mean']:.4f} → {f['imbalance_max_over_mean']:.4f}.",
             f"- Lexicographic score: {b['score']} → {f['score']}; "
             f"{result['algorithm']['accepted_improvements']} strict improvements; "
             f"stop={result['algorithm']['stop_reason']}.",
             "- Units are issue-count proxies, not time estimates. No global optimality or dispatch safety is claimed.",
             "- Unknown localization on verified files remains review work. Ambiguous aliases stay manual.",
             "- Original arrows/qualifications remain witnesses; optimization uses undirected distinct verified pairs only.",
             "", "## Lots", ""]
    edges = {e["id"]: e for e in result["edge_registry"]}
    for lot in result["lots"]:
        lines += [f"### {lot['id']} — proposed, workload {lot['workload']}",
                  "- Writable: " + ", ".join(f"`{safe(p)}`" for p in lot["writable_files"]),
                  "- Unit IDs: " + ", ".join(lot["strict_unit_ids"]),
                  "- Read-only context: " + (", ".join(f"`{safe(p)}`" for p in lot["readonly_context"]) or "none"),
                  "- Neighbor lots: " + (", ".join(lot["neighbor_lots"]) or "none observed"),
                  "- Internal observations: " + (", ".join(lot["internal_edge_ids"]) or "none"),
                  "- Review: current source/correction validation and unknown localization; boundary coordination below."]
        for heavy in lot["oversized_files"]:
            lines.append(f"- Oversized indivisible file: `{safe(heavy['path'])}` "
                         f"({heavy['strict_units']} units, above target).")
        for edge_id in lot["boundary_edge_ids"]:
            edge = edges[edge_id]
            lines.append(f"- Boundary `{safe(edge_id)}`: `{safe(edge['origin_path'])}` → "
                         f"`{safe(edge['destination_path'])}` ({safe(edge['qualification'])}); coordinate, not hard-coedit proof.")
        lines.append("")
    lines += ["## Manual queue", ""]
    for unit in result["unresolved_queue"]:
        lines.append(f"- `{unit['unit_id']}` ({safe(', '.join(unit['file_candidates'])) or 'missing file'}): "
                     + safe("; ".join(unit["reasons"])))
    lines += ["", "## Limits and inherited uncertainty", "",
              f"- Upstream unresolved observations: {result['inherited']['unresolved_observation_count']}.",
              *("- " + safe(v) for v in result["limitations"]),
              *("- Inherited: " + safe(v) for v in result["inherited"]["limitations"]), ""]
    lines += ["- Backend warning: " + safe(v) for v in result["inherited"]["backend_warnings"]]
    lines.append("")
    return "\n".join(lines)


def positive(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("graph", "output", "report"):
        parser.add_argument("--" + name, required=True, type=Path)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--parts", type=positive)
    options.add_argument("--target-issues", type=positive)
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        source, output, report = args.graph.resolve(strict=True), args.output.resolve(), args.report.resolve()
        require(source.is_file() and output.suffix.lower() == ".json" and report.suffix.lower() == ".md",
                "expected graph input and JSON/Markdown outputs")
        require(output.parent.is_dir() and report.parent.is_dir(), "output parents must exist")
        graph_tool.collector.verify_output_input_separation(
            (output, report), (source, Path(__file__).resolve(), Path(graph_tool.__file__)))
        if output.exists():
            require(guards.read_json(output).get("kind") == "lint-work-lots", "refusing foreign JSON overwrite")
        if report.exists():
            require(report.read_bytes().startswith(b"# Proposed correction lots"), "refusing foreign report overwrite")
        with source.open("rb") as handle:
            raw = handle.read(MAX_GRAPH_BYTES + 1)
        require(len(raw) <= MAX_GRAPH_BYTES, "graph exceeds 256 MiB input bound")
        graph_hash = hashlib.sha256(raw).hexdigest()
        graph = guards.json_document(raw.decode("utf-8"))
        prepared = prepare(graph)
        read_seconds = time.monotonic() - started
        partition = optimize(prepared["weights"], prepared["adjacency"], args.parts, args.target_issues or 50)
        result = manifest(graph, prepared, partition, graph_hash, args.parts, args.target_issues or 50)
        result["timing"] = {"read_validate_seconds": read_seconds,
                            "optimization_seconds": partition["elapsed_seconds"],
                            "seconds_before_publication": time.monotonic() - started}
        guards.publish([(output, json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False,
                                           allow_nan=False) + "\n"), (report, render(result))],
                       [source, Path(__file__).resolve(), Path(graph_tool.__file__)], {source: graph_hash})
        print(f"{len(result['lots'])} proposed lots; {result['accounting']['assigned_units']} assigned + "
              f"{result['accounting']['queued_units']} queued = {result['accounting']['strict_units']} strict units; "
              f"cut {result['baseline']['weighted_cut']} -> {result['final']['weighted_cut']}; "
              f"{time.monotonic() - started:.3f}s")
        return 0
    except (guards.Invalid, graph_tool.collector.EvidenceError, OSError, ValueError, TypeError, KeyError) as exc:
        print("partition-workgraph: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
