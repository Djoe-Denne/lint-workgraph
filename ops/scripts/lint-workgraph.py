#!/usr/bin/env python3
"""Collect direct native neighborhoods for a complete inventory and report ownership risks."""

import argparse
import asyncio
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The collector's ordinary CLI imports this sibling by its public module name.
# Register the same trusted file for importlib-based embedding and stdlib tests.
source_ranges = sibling("clippy_source_ranges", "clippy_source_ranges.py")
collector = sibling("_workgraph_collector", "mcp-code-evidence.py")
policy = sibling("_workgraph_scope", "diagnostic-scope.py")
planner = sibling("_workgraph_guards", "clippy-constraint-plan.py")
Error = planner.Invalid
require, fields, text = planner.require, planner.fields, planner.text
read_json, digest = planner.read_json, planner.digest
OUTCOMES = {
    "skipped_local", "queried", "reused_query", "unresolved_localization", "unavailable_backend",
    "source_invalid", "not_attempted_budget", "not_attempted_deadline",
}
PAGED = {"crate_dependency_metric": "metrics", "who_uses": "usages",
         "calls_from": "call_sites", "who_imports": "bindings"}
RELATIONS = {"who_uses", "calls_from", "who_imports"}
SCOPE = "direct_incoming_outgoing_imports_selected_transverse_items"
DEFAULTS = {"timeout": 1800, "max_queries": 20000, "max_pages": 128, "page_size": 100,
            "hydration_batch_size": 400, "max_items": 100000, "max_dependencies": 500000}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def array(value, label):
    require(isinstance(value, list), label + " must be an array")
    return value


def strings(value, label):
    require(all(isinstance(x, str) and x.strip() for x in array(value, label)), label + " must contain strings")
    return value


def seconds(value, label):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, label + " must be finite/nonnegative")


def refs(value, queries):
    values = strings(value, "query references")
    require(values and len(values) == len(set(values)) and set(values) <= queries.keys(),
            "query references must be nonempty, unique and resolve")
    return values


def same_path(value, expected, label):
    require(isinstance(value, str) and Path(value).is_absolute()
            and Path(value).resolve() == expected, label + " authority mismatch")


def inventory_records(inventory):
    """Preserve raw records and conservative identities; routing is not a fix policy."""
    routing = policy.route_inventory(inventory)
    records = {}
    for namespace in ("clippy", "sonar"):
        for row in inventory[namespace]:
            key = namespace + ":" + row["id"]
            records[key] = row
            require(isinstance(row.get("message"), str), "diagnostic message must be a string")
            if namespace == "clippy":
                array(row.get("primary_spans"), "primary spans")
                require(array(row.get("provenance"), "Clippy provenance"), "Clippy provenance missing")
            else:
                text(row.get("file"), "Sonar file")
    for name in ("unmerged_hints", "ambiguous_exact_matches", "limitations"):
        array(inventory.get(name), "inventory " + name)
    for match in inventory["matches"]:
        clippy, sonar = records["clippy:" + match["clippy_id"]], records["sonar:" + match["sonar_id"]]
        require(len(clippy["primary_spans"]) == 1 and sonar.get("range") is not None
                and clippy["rule"] == sonar["rule"] and clippy["message"] == sonar["message"]
                and clippy["primary_spans"][0] == {"file": sonar["file"], "range": sonar["range"]},
                "exact alias does not match strict file/range/message identity")
        for key, expected in (("sonar_issue_keys", sonar["issue_keys"]),
                              ("clippy_provenance", clippy["provenance"])):
            require(key not in match or match[key] == expected, "exact alias provenance mismatch")
    for hint in inventory["unmerged_hints"]:
        require("clippy:" + str(hint.get("clippy_id")) in records
                and "sonar:" + str(hint.get("sonar_id")) in records, "unknown uncertain alias endpoint")
    for hint in inventory["ambiguous_exact_matches"]:
        require(isinstance(hint, dict) and all(
            isinstance(hint.get(namespace + "_ids"), list)
            and all(namespace + ":" + str(identifier) in records for identifier in hint[namespace + "_ids"])
            for namespace in ("clippy", "sonar")), "unknown ambiguous alias endpoint")
    return records, routing


def raw_diagnostic_files(key, record):
    spans = record["primary_spans"] if key.startswith("clippy:") else [record]
    result = []
    for span in spans:
        fields(span, ["file", "range"], "diagnostic location")
        result.append(text(span["file"], "diagnostic file"))
    return result


def verify_corpus_separation(raw_paths, source_paths):
    """Linear identity check; callers retain source/run-root confinement."""
    source_names, source_ids = set(), set()
    for path in source_paths:
        resolved = Path(path).resolve()
        info = resolved.stat()
        source_names.add(resolved)
        source_ids.add((info.st_dev, info.st_ino))
    raw_names, raw_ids = set(), set()
    for path in raw_paths:
        resolved = Path(path).resolve()
        info = resolved.stat()
        identity = (info.st_dev, info.st_ino)
        require(resolved not in source_names and identity not in source_ids,
                "raw artifact aliases a source path/inode")
        require(resolved not in raw_names and identity not in raw_ids,
                "raw artifact paths alias each other")
        raw_names.add(resolved)
        raw_ids.add(identity)


def validate_capture(capture, workspace, artifacts, inventory, inventory_hash, target_head):
    """Validate the generic artifact without manufacturing any legacy proof."""
    fields(capture, ["schema_version", "kind", "status", "workspace", "artifact_root", "orientation",
                     "inventory_sha256", "captured_at", "target_head", "source_files", "backend", "queries",
                     "items", "diagnostics", "dependencies", "limits", "timing", "limitations"], "native capture")
    require(type(capture["schema_version"]) is int and capture["schema_version"] == 1
            and capture["kind"] == "lint-native-dependency-capture", "unsupported native capture schema")
    require(capture["status"] in ("complete", "partial"), "failed/pending capture cannot be accepted")
    same_path(capture["workspace"], workspace, "target workspace")
    same_path(capture["artifact_root"], artifacts, "run artifact root")
    require(capture["orientation"] == "consumer_to_provider", "native orientation mismatch")
    require(capture["inventory_sha256"] == inventory_hash, "inventory hash mismatch")
    require(capture["target_head"] == target_head, "capture target HEAD mismatch")
    planner.timestamp(capture["captured_at"])
    records, routing = inventory_records(inventory)
    strings(capture["limitations"], "capture limitations")
    require(isinstance(capture["limits"], dict), "capture limits must be an object")
    timing = fields(capture["timing"], ["total_seconds", "stages", "requests", "reused_queries"], "capture timing")
    seconds(timing["total_seconds"], "capture total duration")
    require(isinstance(timing["stages"], dict), "timing stages must be an object")
    for value in timing["stages"].values():
        seconds(value, "capture stage duration")
    for name in ("requests", "reused_queries"):
        require(planner.number(timing[name]), "invalid capture timing counter")
    expected, issues, source_data, source_checks, artifact_bytes = {}, [], {}, {}, {}
    identities = {}

    def source(raw):
        name, path = collector.source_path(workspace, raw)
        identity = (path.stat().st_dev, path.stat().st_ino)
        require(identity not in identities or identities[identity] == name, "source filesystem alias")
        identities[identity] = name
        return name, path

    def artifact(ref):
        fields(ref, ["path", "sha256"], "raw artifact reference")
        path = collector.native_artifact_path(artifacts, ref["path"])
        require(path.stat().st_size <= collector.MAX_RESULT_BYTES, "raw artifact exceeds result byte budget")
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == planner.sha(ref["sha256"]),
                "raw artifact hash mismatch: " + ref["path"])
        expected[path] = ref["sha256"]
        artifact_bytes[path] = data
        return path

    for entry in array(capture["source_files"], "source files"):
        fields(entry, ["path", "sha256", "before_sha256", "after_sha256", "status"], "source binding")
        raw = text(entry["path"], "source path")
        require(not raw.startswith(("/", "\\")) and ":" not in raw and "\\" not in raw
                and all(p not in ("", ".", "..") for p in raw.split("/")), "invalid source binding path")
        require(entry["status"] in ("verified", "changed", "missing"), "invalid source binding status")
        require(raw not in source_checks, "duplicate source binding")
        for name in ("sha256", "before_sha256", "after_sha256"):
            if entry[name] is not None:
                planner.sha(entry[name])
        check = {"path": raw, "status": "missing", "current_sha256": None, "reasons": []}
        try:
            name, path = source(raw)
            require(name == raw, "noncanonical source binding")
            require(path.stat().st_size <= collector.MAX_RESULT_BYTES
                    and sum(len(v) for v in source_data.values()) + path.stat().st_size <= collector.MAX_SOURCE_BYTES,
                    "captured source byte budget exceeded")
            data = path.read_bytes()
            current = hashlib.sha256(data).hexdigest()
            expected[path] = current
            source_data[name] = data
            stable = (entry["status"] == "verified" and entry["sha256"] is not None
                      and entry["sha256"] == entry["before_sha256"] == entry["after_sha256"] == current)
            check.update(status="verified_current" if stable else "changed_or_unverified", current_sha256=current)
            if not stable:
                check["reasons"].append("Capture before/after binding and current hash do not establish stability")
        except collector.SourcePathError as exc:
            require(exc.status not in ("outside_root", "ambiguous"), "unsafe source binding: " + str(exc))
            check["reasons"].append(str(exc))
        except OSError as exc:
            check["reasons"].append(type(exc).__name__)
        source_checks[raw] = check

    backend = fields(capture["backend"], ["server_ref", "catalogue_ref", "workspace_evidence",
                                         "snapshot_ids", "warnings", "coverage", "scope", "context_refs"], "backend")
    require(backend["scope"] == SCOPE, "unsupported dependency scope")
    workspace_evidence = fields(backend["workspace_evidence"], ["status", "requested_workspace"], "backend workspace")
    same_path(workspace_evidence["requested_workspace"], workspace, "requested backend workspace")
    require(workspace_evidence["status"] == "requested_directory_only",
            "unsupported claim of independently verified backend workspace")
    strings(backend["snapshot_ids"], "backend snapshots")
    strings(backend["warnings"], "backend warnings")
    require(isinstance(backend["coverage"], dict), "backend coverage must be an object")
    catalogue = []
    for name in ("server_ref", "catalogue_ref"):
        if backend[name] is not None:
            path = artifact(backend[name])
            if name == "catalogue_ref":
                catalogue = planner.json_document(artifact_bytes[path].decode("utf-8"))
                require(isinstance(catalogue, list), "unsupported captured native catalogue")
    queries, payloads, rows, node_witnesses, sequences = {}, {}, {}, defaultdict(list), defaultdict(list)
    for query in array(capture["queries"], "queries"):
        fields(query, ["id", "tool", "arguments", "artifact", "artifact_sha256", "status",
                       "pagination", "limitations", "duration_seconds", "reused_count"], "query")
        identifier = text(query["id"], "query id")
        require(identifier not in queries, "duplicate query id")
        suffix = query["tool"].removeprefix("rust-code-mcp_1mcp_")
        require(query["tool"] == "rust-code-mcp_1mcp_" + suffix and suffix in collector.NATIVE_TOOLS,
                "unsupported generic query tool")
        require(isinstance(query["arguments"], dict), "query arguments must be an object")
        require(query["arguments"].get("directory") == str(workspace), "query requested another workspace")
        require(query["status"] in ("ok", "partial", "error", "unavailable", "unsupported", "timeout"),
                "nonterminal query status")
        if query["status"] in ("ok", "partial"):
            advertised = [t for t in catalogue if isinstance(t, dict) and t.get("name") == query["tool"]]
            require(len(advertised) == 1, "successful query lacks an unambiguous captured catalogue tool")
            schema = advertised[0].get("inputSchema", {})
            require(isinstance(schema, dict) and isinstance(schema.get("properties"), dict)
                    and set(query["arguments"]) <= schema["properties"].keys()
                    and set(schema.get("required", [])) <= query["arguments"].keys(),
                    "captured query arguments differ from advertised schema")
        strings(query["limitations"], "query limitations")
        seconds(query["duration_seconds"], "query duration")
        require(planner.number(query["reused_count"]), "invalid query reuse count")
        page = fields(query["pagination"], ["status", "pages", "returned", "total", "reason"], "query pagination")
        require(page["status"] in ("complete", "partial", "unknown", "not_applicable")
                and planner.number(page["pages"]) and planner.number(page["returned"])
                and (page["total"] is None or planner.number(page["total"]))
                and isinstance(page["reason"], str), "invalid query pagination")
        path = artifact({"path": query["artifact"], "sha256": query["artifact_sha256"]})
        queries[identifier] = query
        try:
            payload = collector.decode_wire(planner.json_document(artifact_bytes[path].decode("utf-8")))
            payloads[identifier] = payload
        except (collector.EvidenceError, Error) as exc:
            issues.append({"id": identifier, "reason": "Raw response undecodable: " + str(exc)})
            continue
        if (suffix == "build_codemap" and isinstance(payload, dict)
                and isinstance(payload.get("snapshot_id"), str) and payload["snapshot_id"]
                and isinstance(payload.get("nodes"), list) and isinstance(payload.get("edges"), list)):
            for node in payload.get("nodes", []) if isinstance(payload.get("nodes"), list) else []:
                if isinstance(node, dict):
                    node_witnesses[canonical([payload.get("snapshot_id"), node.get("id")])].append((identifier, node))
            rows[identifier] = {canonical(row) for row in payload.get("edges", [])
                                if isinstance(row, dict)}
        elif suffix in PAGED:
            values = payload.get(PAGED[suffix]) if isinstance(payload, dict) else None
            if not isinstance(values, list):
                issues.append({"id": identifier, "reason": "Unsupported native page envelope"})
                continue
            rows[identifier] = {canonical(row) for row in values if isinstance(row, dict)}
            key = canonical([query["tool"], {k: v for k, v in query["arguments"].items()
                                             if k not in ("offset", "limit")}])
            sequences[key].append(query)
    strings(backend["context_refs"], "backend context refs")
    require(set(backend["context_refs"]) <= queries.keys(), "unknown backend context query")
    invalid_pages = set()
    for sequence in sequences.values():
        sequence.sort(key=lambda q: q["arguments"].get("offset", -1))
        offset, total, seen = 0, None, set()
        bad = []
        for query in sequence:
            identifier = query["id"]
            payload, args = payloads[identifier], query["arguments"]
            suffix = query["tool"].removeprefix("rust-code-mcp_1mcp_")
            values = payload[PAGED[suffix]]
            selector_key = "caller" if suffix == "calls_from" else "target" if suffix != "crate_dependency_metric" else None
            valid = (planner.number(payload.get("offset")) and planner.number(payload.get("limit"), 1)
                     and planner.number(payload.get("returned_match_count"))
                     and planner.number(payload.get("total_match_count"))
                     and payload["offset"] == args.get("offset") == offset
                     and payload["limit"] == args.get("limit") and payload.get("summary") is False
                     and len(values) == payload["returned_match_count"] <= payload["limit"]
                     and offset + len(values) <= payload["total_match_count"]
                     and (total is None or payload["total_match_count"] == total)
                     and (not selector_key or payload.get(selector_key) == args.get(selector_key)))
            keys = [canonical(row) for row in values]
            valid = valid and all(isinstance(row, dict) for row in values) and len(set(keys)) == len(keys)
            valid = valid and not seen.intersection(keys)
            if not valid:
                bad.append(identifier)
            total = payload.get("total_match_count")
            seen.update(keys)
            offset += len(values)
        if any(q["pagination"]["status"] == "complete" and
               (q["pagination"]["returned"] != offset or q["pagination"]["total"] != total
                or q["pagination"]["pages"] != len(sequence) or offset != total) for q in sequence):
            bad.extend(q["id"] for q in sequence)
        if bad:
            invalid_pages.update(q["id"] for q in sequence)
            issues.append({"id": sequence[0]["id"], "reason": "Native pagination gaps/repeats/count/total mismatch"})

    items, item_checks, parsed = {}, {}, {}
    for item in array(capture["items"], "native items"):
        fields(item, ["id", "native_id", "selector", "kind", "visibility", "path", "range", "location_status",
                      "source_sha256", "snapshot_id", "native", "evidence_refs", "reasons"], "native item")
        identifier = text(item["id"], "item id")
        require(identifier not in items, "duplicate item id")
        text(item["selector"], "native selector")
        refs(item["evidence_refs"], queries)
        strings(item["reasons"], "item reasons")
        text(item["kind"], "native kind")
        require(item["visibility"] is None or isinstance(item["visibility"], str), "invalid native visibility")
        require(item["location_status"] in ("verified", "candidate", "unknown"), "invalid item location status")
        require(item["path"] is None or isinstance(item["path"], str), "invalid item path")
        if item["source_sha256"] is not None:
            planner.sha(item["source_sha256"])
        if item["range"] is not None:
            extent = fields(item["range"], ["start_byte", "end_byte", "start_line", "end_line", "column_unit"],
                            "native range")
            require(planner.number(extent["start_byte"]) and planner.number(extent["end_byte"], 1)
                    and extent["start_byte"] < extent["end_byte"]
                    and planner.number(extent["start_line"], 1) and planner.number(extent["end_line"], 1)
                    and extent["start_line"] <= extent["end_line"] and extent["column_unit"] == "utf8_byte",
                    "invalid native normalized range")
        fields(item["native"], ["file", "span", "line"], "original native location")
        items[identifier] = item
        checked = {"status": "unresolved", "path": None, "reasons": []}
        try:
            require(item["native_id"] is not None and isinstance(item["native_id"], list)
                    and item["native_id"] and all(planner.number(x) and x <= 255 for x in item["native_id"]),
                    "native ID missing/invalid")
            require(isinstance(item["snapshot_id"], str) and item["snapshot_id"], "native snapshot identity missing")
            witnesses = node_witnesses[canonical([item["snapshot_id"], item["native_id"]])]
            identities_ = {canonical([n.get("qualified_name"), n.get("item_kind") or n.get("kind"),
                                      n.get("file"), n.get("span"), n.get("line")]) for _, n in witnesses}
            require(len(identities_) == 1, "missing/conflicting native ID witnesses in this snapshot")
            matches = [(q, node) for q, node in witnesses
                       if q in item["evidence_refs"] and node.get("qualified_name") == item["selector"]
                       and queries[q]["status"] in ("ok", "partial")
                       and (node.get("item_kind") or node.get("kind")) == item["kind"]
                       and {k: node.get(k) for k in ("file", "span", "line")} == item["native"]]
            require(matches, "native item has no matching raw hydration witness")
            name, _ = source(item["native"]["file"])
            checked.update(path=name, status="backend_observed")
            declared_name, _ = source(item["path"])
            require(name == declared_name, "native/current file mismatch")
            require(source_checks.get(name, {}).get("status") == "verified_current"
                    and item["source_sha256"] == source_checks[name]["current_sha256"],
                    "current source binding not verified")
            if name not in parsed:
                decoded = source_data[name].decode("utf-8")
                structure = collector.source_ranges._structure(decoded)
                parsed[name] = (structure, collector.source_ranges._declarations(decoded, structure))
            projected = collector.native_location(source_data[name], matches[0][1], parsed[name])
            require(projected == item["range"] and item["location_status"] == "verified",
                    "current native declaration/range not verified")
            checked["status"] = "source_verified"
        except (collector.EvidenceError, Error, UnicodeError, KeyError) as exc:
            checked["reasons"].append(str(exc))
        if item["location_status"] == "verified" and checked["status"] != "source_verified":
            issues.append({"id": identifier, "reason": "Claimed current native projection failed consumer replay"})
        item_checks[identifier] = checked
    diagnostics, query_served = {}, defaultdict(list)
    routes = {d["diagnostic_key"]: d["scope"] for d in routing["diagnostics"]}
    for diagnostic in array(capture["diagnostics"], "capture diagnostics"):
        fields(diagnostic, ["diagnostic_key", "route", "files", "item_ids", "query_ids", "attempt_outcome",
                            "localization_status", "reasons"], "capture diagnostic")
        key = diagnostic["diagnostic_key"]
        require(key in records and key not in diagnostics, "unknown/duplicate capture diagnostic")
        require(diagnostic["route"] == routes[key], "capture route differs from existing scope policy")
        strings(diagnostic["files"], "diagnostic files")
        strings(diagnostic["item_ids"], "diagnostic items")
        strings(diagnostic["query_ids"], "diagnostic queries")
        strings(diagnostic["reasons"], "diagnostic reasons")
        require(set(diagnostic["item_ids"]) <= items.keys() and set(diagnostic["query_ids"]) <= queries.keys(),
                "unresolved diagnostic item/query reference")
        expected_files = set()
        for raw in raw_diagnostic_files(key, records[key]):
            try:
                name, _ = collector.source_path(workspace, raw)
            except (collector.SourcePathError, OSError):
                name = raw.replace("\\", "/")
            expected_files.add(name)
        require(set(diagnostic["files"]) == expected_files, "capture diagnostic files differ from inventory")
        require(all(items[i]["path"] in expected_files for i in diagnostic["item_ids"]),
                "diagnostic assigned an item outside its inventory files")
        outcome = diagnostic["attempt_outcome"]
        require(outcome in OUTCOMES and ((routes[key] == "local") == (outcome == "skipped_local")),
                "invalid terminal diagnostic outcome")
        require(diagnostic["localization_status"] in ("unknown", "candidate", "source_invalid", "stale", "exact"),
                "invalid diagnostic localization")
        if diagnostic["localization_status"] == "exact":
            issues.append({"id": key, "reason": "No generic historical attribution proof; exact claim retained as candidate"})
        if outcome in ("queried", "reused_query"):
            selected = {items[i]["selector"] for i in diagnostic["item_ids"]}
            require(any(queries[q]["tool"].removeprefix("rust-code-mcp_1mcp_") in RELATIONS
                        and (queries[q]["arguments"].get("caller") or queries[q]["arguments"].get("target"))
                        in selected for q in diagnostic["query_ids"]),
                    "claimed queried record has no relation query for its selected scope")
        for identifier in diagnostic["query_ids"]:
            query_served[identifier].append(key)
        diagnostics[key] = diagnostic
    require(diagnostics.keys() == records.keys(), "capture must retain every inventory diagnostic exactly once")

    dependencies = {}
    for dependency in array(capture["dependencies"], "native dependencies"):
        fields(dependency, ["id", "kind", "origin_item_id", "destination_item_id", "origin_path", "destination_path",
                            "native_origin", "native_destination", "native", "evidence_refs",
                            "qualification", "reasons"], "native dependency")
        identifier = text(dependency["id"], "dependency id")
        require(identifier not in dependencies, "duplicate dependency id")
        text(dependency["kind"], "dependency kind")
        reference_ids = refs(dependency["evidence_refs"], queries)
        strings(dependency["reasons"], "dependency reasons")
        require(dependency["qualification"] in ("source_verified", "backend_observed", "unresolved"),
                "invalid dependency qualification")
        for field in ("origin_item_id", "destination_item_id"):
            require(dependency[field] is None or dependency[field] in items, "unknown dependency item endpoint")
        checked = {"record": dependency, "origin_path": None, "destination_path": None,
                   "qualification": "unresolved", "reasons": []}
        witnesses = [q for q in reference_ids if canonical(dependency["native"]) in rows.get(q, set())]
        if not witnesses:
            checked["reasons"].append("Dependency lacks a matching raw relation witness")
        identity_ok, site_ok = False, False
        for q in witnesses:
            query = queries[q]
            suffix = query["tool"].removeprefix("rust-code-mcp_1mcp_")
            row, args, payload = dependency["native"], query["arguments"], payloads[q]
            origin, destination = dependency["native_origin"], dependency["native_destination"]
            if not isinstance(origin, dict) or not isinstance(destination, dict):
                continue
            if suffix == "who_uses":
                identity_ok |= (isinstance(args.get("target"), str) and bool(args["target"])
                                and payload.get("target") == args.get("target") == destination.get("selector")
                                and origin.get("selector") == row.get("consumer_function"))
            elif suffix == "calls_from":
                identity_ok |= (isinstance(args.get("caller"), str) and bool(args["caller"])
                                and payload.get("caller") == args.get("caller") == row.get("caller_qualified_name")
                                == origin.get("selector") and row.get("callee_qualified_name") ==
                                destination.get("selector"))
            elif suffix == "who_imports":
                identity_ok |= (isinstance(args.get("target"), str) and bool(args["target"])
                                and isinstance(row.get("from_module"), str) and bool(row["from_module"])
                                and payload.get("target") == args.get("target") == row.get("target")
                                == destination.get("selector") and row.get("from_module") == origin.get("selector"))
                site_ok = True
            elif suffix == "build_codemap":
                identity_ok |= (isinstance(row.get("from"), list) and bool(row["from"])
                                and isinstance(row.get("to"), list) and bool(row["to"])
                                and row.get("from") == origin.get("id") and row.get("to") == destination.get("id"))
                site_ok = True
        for side in ("origin", "destination"):
            item_id = dependency[side + "_item_id"]
            endpoint = dependency["native_" + side]
            if item_id is not None and isinstance(endpoint, dict):
                if endpoint.get("selector") is not None and endpoint["selector"] != items[item_id]["selector"]:
                    identity_ok = False
                    checked["reasons"].append("Native selector/item endpoint mismatch")
                if endpoint.get("id") is not None and endpoint["id"] != items[item_id]["native_id"]:
                    identity_ok = False
                    checked["reasons"].append("Native ID/item endpoint mismatch")
        raw_row_file = None
        if any(queries[q]["tool"].endswith(("_who_uses", "_calls_from")) for q in witnesses):
            raw_row_file = dependency["native"].get("file")
        for side in ("origin", "destination"):
            item_id = dependency[side + "_item_id"]
            item = items[item_id] if item_id else None
            # A normalized file claim alone is not a backend file witness.
            # Site-bearing incoming/outgoing rows can establish an origin file
            # even if the native caller item is unlocated.
            raw = raw_row_file if side == "origin" and raw_row_file else (
                item_checks[item_id]["path"] if item_id else None)
            if raw is not None:
                try:
                    name, path = source(raw)
                    declared = dependency[side + "_path"]
                    if declared is not None:
                        declared_name, _ = source(declared)
                        if declared_name != name:
                            identity_ok = False
                            checked["reasons"].append("Declared endpoint file differs from raw witness")
                    checked[side + "_path"] = name
                    if name not in source_data:
                        if (path.stat().st_size <= collector.MAX_RESULT_BYTES and
                                sum(len(v) for v in source_data.values()) + path.stat().st_size <=
                                collector.MAX_SOURCE_BYTES):
                            data = path.read_bytes()
                            source_data[name] = data
                            expected[path] = hashlib.sha256(data).hexdigest()
                        else:
                            checked["reasons"].append("Current source read budget exhausted")
                    if item and item_checks[item_id]["path"] not in (None, name):
                        identity_ok = False
                        checked["reasons"].append("Dependency/native item file disagreement")
                except (collector.SourcePathError, OSError) as exc:
                    checked["reasons"].append(str(exc))
        row = dependency["native"]
        if isinstance(row, dict) and any(queries[q]["tool"].endswith(("_who_uses", "_calls_from")) for q in witnesses):
            try:
                path, _ = source(row["file"])
                start, end = row.get("start"), row.get("end")
                name = dependency["native_destination"].get("selector", "").rsplit("::", 1)[-1]
                data = source_data[path]
                site_ok = (path == checked["origin_path"] and planner.number(start) and planner.number(end)
                           and 0 <= start < end <= len(data) and data[start:end].decode("utf-8") == name)
            except (KeyError, UnicodeError, collector.SourcePathError, OSError):
                site_ok = False
        paths_known = checked["origin_path"] is not None and checked["destination_path"] is not None
        if witnesses and identity_ok and paths_known:
            checked["qualification"] = "backend_observed"
            origins = dependency["origin_item_id"]
            destination = dependency["destination_item_id"]
            origin_ok = (origins is not None and item_checks[origins]["status"] == "source_verified"
                         or origins is None and any(queries[q]["tool"].endswith("_who_uses") for q in witnesses))
            current = (site_ok and origin_ok and destination is not None
                       and item_checks[destination]["status"] == "source_verified"
                       and all(source_checks.get(checked[side + "_path"], {}).get("status") == "verified_current"
                               for side in ("origin", "destination"))
                       and not set(witnesses) & invalid_pages
                       and all(queries[q]["status"] in ("ok", "partial") for q in witnesses))
            if current and dependency["qualification"] == "source_verified":
                checked["qualification"] = "source_verified"
            else:
                checked["reasons"].append("Current endpoints/site/sequence do not establish source-verified qualification")
        else:
            checked["reasons"].append("Native relation identity or root-confined endpoint file unresolved")
        dependencies[identifier] = checked
    verify_corpus_separation(tuple(artifact_bytes), tuple(workspace / name for name in source_data))
    return {"capture": capture, "records": records, "routing": routing, "sources": source_checks,
            "items": items, "item_checks": item_checks, "queries": queries,
            "query_served": query_served, "diagnostics": diagnostics, "dependencies": dependencies,
            "issues": issues, "expected_hashes": expected,
            "received_page_count": sum(
                q["tool"].removeprefix("rust-code-mcp_1mcp_") in PAGED and isinstance(payloads.get(q["id"]), dict)
                and isinstance(payloads[q["id"]].get(PAGED[q["tool"].removeprefix("rust-code-mcp_1mcp_")]), list)
                for q in queries.values())}


def assemble(model, workspace, artifacts, inventory):
    capture, records = model["capture"], model["records"]
    nodes, unresolved, edges = {}, [], {}

    def node(raw, key=None, item_id=None):
        path, status = raw, "unresolved_path"
        try:
            path, _ = collector.source_path(workspace, raw)
            status = model["sources"].get(path, {}).get("status", "backend_observed_current_unchecked")
        except (collector.SourcePathError, OSError):
            pass
        entry = nodes.setdefault(path, {"path": path, "diagnostic_keys": set(), "item_ids": set(),
                                        "source_status": status, "raw_paths": set()})
        entry["raw_paths"].add(raw)
        if key:
            entry["diagnostic_keys"].add(key)
        if item_id:
            entry["item_ids"].add(item_id)
        return path

    diagnostic_rows = []
    for key, record in sorted(records.items()):
        captured = model["diagnostics"][key]
        paths = raw_diagnostic_files(key, record)
        files = sorted({node(path.replace("\\", "/"), key=key) for path in paths})
        if not files:
            files = [node("unlocated:" + key, key=key)]
        outcome = captured["attempt_outcome"]
        if outcome not in ("skipped_local", "queried", "reused_query"):
            unresolved.append({"id": "diagnostic:" + key, "files": files, "reasons": captured["reasons"],
                               "kind": "diagnostic_outcome", "outcome": outcome})
        diagnostic_rows.append({"key": key, "record": record, "files": files, **{
            k: captured[k] for k in ("route", "item_ids", "query_ids", "attempt_outcome", "reasons")},
            "localization_status": "candidate" if captured["localization_status"] == "exact" else
            captured["localization_status"],
            "historical_attribution": "not_established_by_generic_capture"})
    relevant_items = {i for d in model["diagnostics"].values() for i in d["item_ids"]}
    relevant_items.update(i for d in model["dependencies"].values()
                          for i in (d["record"]["origin_item_id"], d["record"]["destination_item_id"]) if i)
    for item_id, checked in model["item_checks"].items():
        if checked["path"] in nodes:
            node(checked["path"], item_id=item_id)
        if checked["status"] != "source_verified":
            relevant = item_id in relevant_items
            unresolved.append({"id": "item:" + item_id, "files": [checked["path"]] if checked["path"] else [],
                               "kind": "native_item", "reasons": checked["reasons"], "relevant_to_selected_scope": relevant})
    for identifier, checked in sorted(model["dependencies"].items()):
        record = checked["record"]
        for path in (checked["origin_path"], checked["destination_path"]):
            if path is not None:
                node(path)
        if checked["qualification"] == "unresolved":
            unresolved.append({"id": "dependency:" + identifier,
                               "files": [p for p in (checked["origin_path"], checked["destination_path"]) if p],
                               "kind": "native_endpoint", "reasons": checked["reasons"], "record": record})
            continue
        origin, destination = node(checked["origin_path"]), node(checked["destination_path"])
        identity = (origin, destination, record["kind"], checked["qualification"])
        edge = edges.setdefault(identity, {"origin_path": origin, "destination_path": destination,
                                          "class": "candidate_dependency", "kind": record["kind"],
                                          "qualification": checked["qualification"],
                                          "relationship_scope": "native_direct_dependency",
                                          "dependency_ids": [], "evidence_refs": set(), "reasons": set()})
        edge["dependency_ids"].append(identifier)
        edge["evidence_refs"].update(record["evidence_refs"])
        edge["reasons"].update(record["reasons"] + checked["reasons"])
    for item_id, checked in model["item_checks"].items():
        if checked["path"] in nodes:
            node(checked["path"], item_id=item_id)
    edge_rows = []
    for i, (_, edge) in enumerate(sorted(edges.items()), 1):
        edge_rows.append({"id": f"edge-{i:06d}", **{k: sorted(v) if isinstance(v, set) else v
                                                 for k, v in edge.items()}})
    node_rows = [{**n, "diagnostic_keys": sorted(n["diagnostic_keys"]), "item_ids": sorted(n["item_ids"]),
                  "raw_paths": sorted(n["raw_paths"])} for _, n in sorted(nodes.items())]
    groups = []
    for index, n in enumerate(node_rows, 1):
        boundary = [e["id"] for e in edge_rows if e["origin_path"] != e["destination_path"]
                    and n["path"] in (e["origin_path"], e["destination_path"])]
        unknown = [u["id"] for u in unresolved if u.get("relevant_to_selected_scope", True)
                   and (n["path"] in u["files"] or not u["files"])]
        groups.append({"id": f"group-{index:06d}", "files": [n["path"]], "constraint_ids": [],
                       "diagnostic_keys": n["diagnostic_keys"], "boundary_edge_ids": boundary,
                       "unresolved_ids": sorted(set(unknown)), "readiness": "review_required",
                       "edge_status": "observed" if any(n["path"] in (e["origin_path"], e["destination_path"])
                                                     for e in edge_rows) else "not_observed"})
    outcomes = Counter(row["attempt_outcome"] for row in diagnostic_rows)
    transverse = [row for row in diagnostic_rows if row["route"] == "transverse"]
    served_keys = {row["key"] for row in transverse if any(
        q in model["queries"] and model["queries"][q]["tool"].removeprefix(
        "rust-code-mcp_1mcp_") in RELATIONS and model["queries"][q]["status"] in ("ok", "partial")
        for q in row["query_ids"])}
    served = len(served_keys)
    stopped = sum(outcomes[o] for o in ("not_attempted_budget", "not_attempted_deadline"))
    status = "partial" if (capture["status"] != "complete" or model["issues"] or stopped or
                           any(c["status"] != "verified_current" for c in model["sources"].values())) else "complete"
    if any(row["attempt_outcome"] not in ("queried", "reused_query") for row in transverse):
        status = "partial"
    summary = {"retained_records": len(records), **inventory["counts"],
               "observed_rule_types": len(model["routing"]["rules"]),
               "routes": model["routing"]["summary"], "terminal_outcomes": dict(sorted(outcomes.items())),
               "transverse_records": len(transverse), "transverse_attempted": len(transverse) - stopped,
               "transverse_query_served": served,
               "transverse_unresolved": sum(row["key"] not in served_keys and
                                           not row["attempt_outcome"].startswith("not_attempted") for row in transverse),
               "transverse_stopped_with_partial_queries": sum(row["key"] in served_keys and
                   row["attempt_outcome"].startswith("not_attempted") for row in transverse),
               "not_attempted": stopped, "query_records": len(model["queries"]),
               "query_pages": model["received_page_count"],
               "backend_tool_requests_reported": capture["timing"]["requests"],
               "backend_reuse_reported": capture["timing"]["reused_queries"],
               "backend_cache_hits_reported": capture["timing"].get("cache_hits"),
               "query_reuse_assignments": sum(max(0, len(v) - 1) for v in model["query_served"].values()),
               "native_dependency_observations": len(model["dependencies"]),
               "native_item_qualifications": dict(sorted(Counter(
                   i["status"] for i in model["item_checks"].values()).items())),
               "unlocated_item_records": sum(i["status"] == "unresolved" for i in model["item_checks"].values()),
               "unexpanded_index_item_total": None,
               "dependency_qualifications": dict(sorted(Counter(
                   d["qualification"] for d in model["dependencies"].values()).items())),
               "item_kind_counts": dict(sorted(Counter(str(i["kind"]) for i in model["items"].values()).items())),
               "item_visibility_counts": dict(sorted(Counter(str(i["visibility"]) for i in model["items"].values()).items())),
               "semantic_defect_count": None}
    return {
        "schema_version": 1, "kind": "lint-workgraph", "status": status, "workspace": str(workspace),
        "target_head": capture["target_head"], "artifact_root": str(artifacts),
        "inventory": inventory, "accounting": summary, "routing": model["routing"],
        "diagnostics": diagnostic_rows, "native_capture": capture,
        "source_checks": list(model["sources"].values()), "item_checks": model["item_checks"],
        "native_dependencies": list(model["dependencies"].values()), "validation_issues": model["issues"],
        "queries": [{**q, "served_diagnostic_keys": sorted(model["query_served"].get(q["id"], []))}
                    for q in model["queries"].values()],
        "work_graph": {"nodes": node_rows, "edges": edge_rows, "proposed_groups": groups,
                       "unresolved_observations": unresolved, "global_independence": "unproven",
                       "coverage": {"scope": SCOPE, "orientation": "consumer_to_provider",
                                    "backend": capture["backend"], "files": len(node_rows),
                                    "hard_edges": 0, "candidate_edges": len(edge_rows),
                                    "unique_cross_file_boundaries": len({tuple(sorted(
                                        (e["origin_path"], e["destination_path"]))) for e in edge_rows
                                        if e["origin_path"] != e["destination_path"]}),
                                    "edge_absence": "not_observed", "unattempted_records": stopped}},
        "limitations": ["Direct incoming/outgoing/import scopes selected from the full inventory; not recursive closure.",
                        "Rule routing selects queries; local is not correction approval or certified independence.",
                        "Current endpoint checks do not establish historical diagnostic equivalence or global freshness.",
                        "Native candidate edges never create hard unions or authorize correction dispatch.",
                        *capture["limitations"]],
    }


def report(result):
    def safe(value):
        return str(value).replace("\r", " ").replace("\n", " ").replace("`", "'").replace("<", "&lt;")
    a, graph = result["accounting"], result["work_graph"]
    lines = ["# Full-inventory dependency work graph", "",
             f"- Status: **{result['status']}**; artifacts: `{safe(result['artifact_root'])}`.",
             f"- Workspace: `{safe(result['workspace'])}`; target HEAD: `{result['target_head']}`.",
             f"- Retained records: {a['retained_records']}; strict union: {a['strict_union']}; "
             f"Sonar source keys: {a['sonar_raw_keys']}. Semantic defect count: unknown.",
             f"- Observed rule types: {a['observed_rule_types']}; routing strict union: "
             + safe(canonical(a["routes"]["strict_union"])) + "; raw Sonar keys by route: "
             + safe(canonical(a["routes"]["sonar_issue_keys"])) + ".",
             f"- Local skips: {a['terminal_outcomes'].get('skipped_local', 0)}; transverse: {a['transverse_records']}; "
             f"attempted: {a['transverse_attempted']}; query-served: {a['transverse_query_served']}; "
             f"unresolved: {a['transverse_unresolved']}; not attempted: {a['not_attempted']}.",
             f"- Query records: {a['query_records']}; received paginated responses: {a['query_pages']}; "
             f"reported tool requests: {a['backend_tool_requests_reported']}; "
             f"shared diagnostic assignments: {a['query_reuse_assignments']}.",
             f"- Stopped records that had some successful queries: {a['transverse_stopped_with_partial_queries']} "
             "(query-served and stopped counts can overlap; the remaining item scope was not completed).",
             f"- Native observations: {a['native_dependency_observations']}; qualifications: "
             + safe(canonical(a["dependency_qualifications"])) + ".",
             f"- File nodes/groups: {len(graph['nodes'])}; candidate coupling edges: {len(graph['edges'])}; "
             f"unique cross-file boundaries: {graph['coverage']['unique_cross_file_boundaries']}; hard unions: 0.",
             "- Arrows are native **consumer → provider**, not legacy provider-impact arrows or execution order.",
             "- Scope: direct incoming/outgoing/import dependencies of selected transverse scopes, "
             "not recursive whole-workspace closure.",
             "- Singleton groups are tentative file ownership units, not independent or dispatchable lots.",
             "- No edge means not_observed, not independent.", "", "## Timing and backend coverage", ""]
    lines.append("- Timing: " + safe(canonical(result.get("timing", {}))))
    lines.append("- Completed publication/total timing: `command-manifest.json` in the run artifact directory.")
    lines.append("- Backend coverage: " + safe(canonical(result["native_capture"]["backend"]["coverage"])))
    for warning in result["native_capture"]["backend"]["warnings"]:
        lines.append("- Backend warning (not a current-endpoint verdict): " + safe(warning))
    lines += ["", "## Boundary review tasks", ""]
    for edge in graph["edges"]:
        lines.append(f"- `{edge['id']}`: `{safe(edge['origin_path'])}` → `{safe(edge['destination_path'])}` "
                     f"({safe(edge['kind'])}, {edge['qualification']}); "
                     f"native observations {safe(', '.join(edge['dependency_ids']))}; queries "
                     f"{safe(', '.join(edge['evidence_refs']))}. Review the specific correction; do not hard-union.")
    lines += ["", "## Tentative ownership groups", ""]
    for group in graph["proposed_groups"]:
        lines.append(f"- `{group['id']}`: `{safe(group['files'][0])}`; {group['readiness']}; "
                     f"diagnostics {safe(', '.join(group['diagnostic_keys'])) or 'none'}; boundaries "
                     f"{safe(', '.join(group['boundary_edge_ids'])) or 'not_observed'}; unresolved "
                     f"{safe(', '.join(group['unresolved_ids'])) or 'none recorded'}.")
    lines += ["", "## Unresolved native endpoints and work", ""]
    for item in graph["unresolved_observations"]:
        lines.append(f"- `{safe(item['id'])}`: {safe('; '.join(item['reasons'])) or item['kind']}.")
    lines += ["", "## Per-record attempt coverage", ""]
    for row in result["diagnostics"]:
        lines.append(f"- `{safe(row['key'])}` ({safe(row['record']['rule'])}): {row['route']}, "
                     f"{row['attempt_outcome']}, {row['localization_status']}; files "
                     f"{safe(', '.join(row['files']))}; queries {safe(', '.join(row['query_ids'])) or 'none'}.")
    lines += ["", "## Limits", "", *("- " + safe(v) for v in result["limitations"]), ""]
    return "\n".join(lines)


def preflight(args):
    workspace = collector.validate_workspace(args.workspace)
    inventory = Path(args.inventory).resolve(strict=True)
    output, markdown = Path(args.output).resolve(), Path(args.report).resolve()
    artifacts = Path(args.artifacts).absolute() if args.artifacts else output.with_name(output.stem + ".artifacts")
    require(not artifacts.exists() and not artifacts.is_symlink(), "run artifact directory must be fresh")
    for path in (artifacts, *artifacts.parents):
        require(not path.is_symlink() and not (hasattr(path, "is_junction") and path.is_junction()),
                "artifact directory alias")
    artifacts = artifacts.resolve()
    require(all(p.parent.is_dir() for p in (output, markdown, artifacts)), "output/artifact parents must exist")
    require(output.suffix.lower() == ".json" and markdown.suffix.lower() == ".md", "outputs must be JSON and Markdown")
    require(output != markdown and all(not p.is_relative_to(artifacts) for p in (workspace, inventory, output, markdown)),
            "artifacts must not contain workspace/inputs/outputs")
    collector.verify_output_input_separation((output, markdown), (inventory, Path(__file__).resolve(),
                                                                Path(collector.__file__), Path(policy.__file__)))
    if output.exists():
        require(output.is_file() and read_json(output).get("kind") == "lint-workgraph",
                "refusing to replace a non-workgraph JSON file")
    if markdown.exists():
        require(markdown.is_file() and markdown.read_bytes().startswith(b"# Full-inventory dependency work graph"),
                "refusing to replace a non-workgraph report")
    collector.validate_url(args.url)
    return workspace, inventory, output, markdown, artifacts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "inventory", "output", "report"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--url", default=collector.DEFAULT_URL)
    parser.add_argument("--artifacts", help="New run directory; default <output-stem>.artifacts")
    for name, default in DEFAULTS.items():
        parser.add_argument("--" + name.replace("_", "-"), type=float if name == "timeout" else int, default=default)
    args = parser.parse_args(argv)
    started, stages, owned, artifacts = time.monotonic(), {}, False, None
    inventory_hash, workspace = None, None
    try:
        workspace, inventory_path, output, markdown, artifacts = preflight(args)
        inventory, inventory_hash = collector.read_native_inventory(inventory_path)
        inventory_records(inventory)
        target_head = collector.git_head(workspace)
        stages["preflight_seconds"] = time.monotonic() - started
        at = time.monotonic()
        capture = asyncio.run(collector.collect_native_dependencies(
            workspace, inventory_path, artifacts, url=args.url,
            protected_paths=(output, markdown),
            **{name: getattr(args, name) for name in DEFAULTS}))
        owned = True
        stages["collection_seconds"] = time.monotonic() - at
        require(artifacts.is_dir() and not artifacts.is_symlink() and artifacts.resolve() == artifacts,
                "run artifact authority changed")
        capture_path = collector.native_artifact_path(artifacts, "native-capture.json")
        capture_bytes = capture_path.read_bytes()
        capture_hash = hashlib.sha256(capture_bytes).hexdigest()
        require(canonical(planner.json_document(capture_bytes.decode("utf-8"))) == canonical(capture),
                "returned/persisted capture mismatch")
        at = time.monotonic()
        model = validate_capture(capture, workspace, artifacts, inventory, inventory_hash, target_head)
        stages["validation_seconds"] = time.monotonic() - at
        at = time.monotonic()
        result = assemble(model, workspace, artifacts, inventory)
        stages["assembly_seconds"] = time.monotonic() - at
        result["input_hashes"] = {"inventory": inventory_hash, "native_capture": capture_hash}
        try:
            result["tool_head"] = collector.git_head(Path(__file__).resolve().parents[2])
        except (collector.EvidenceError, OSError):
            result["tool_head"] = None
        result["tool_revision_scope"] = "tool HEAD metadata only; not authority for the target or a clean-tree claim"
        result["timing"] = {**stages, "total_seconds_before_publication": time.monotonic() - started,
                            "capture": capture["timing"], "completion_ref": "command-manifest.json"}
        expected = {inventory_path: inventory_hash, capture_path: capture_hash, **model["expected_hashes"]}
        protected = list(expected) + [Path(__file__).resolve(), Path(collector.__file__), Path(policy.__file__)]
        collector.verify_output_input_separation((output, markdown), protected)
        for source in model["sources"]:
            try:
                _, path = collector.source_path(workspace, source)
            except collector.SourcePathError:
                continue
            require(not path.is_relative_to(artifacts), "source aliases run-artifact root")
        at = time.monotonic()
        planner.publish([(output, json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"),
                         (markdown, report(result))], protected, expected)
        stages["publication_seconds"] = time.monotonic() - at
        stages["total_seconds"] = time.monotonic() - started
        exit_code = (3 if result["accounting"]["not_attempted"] else
                     4 if result["accounting"]["transverse_records"] and not result["work_graph"]["edges"] else 0)
        collector.atomic_json(artifacts / "command-manifest.json", {
            "schema_version": 1, "kind": "lint-workgraph-run", "status": result["status"], "exit_code": exit_code,
            "workspace": str(workspace), "inventory_sha256": inventory_hash, "timing": stages,
            "output": {"path": str(output), "sha256": digest(output)},
            "report": {"path": str(markdown), "sha256": digest(markdown)},
        })
        print(f"{result['status']}: {len(result['diagnostics'])} records; "
              f"{len(result['work_graph']['edges'])} candidate file edges; artifacts={artifacts}")
        return exit_code
    except Exception as exc:
        # Collector owns failures before return; never overwrite a directory a
        # concurrent invocation might have created after our preflight.
        if owned and artifacts is not None and artifacts.is_dir() and not artifacts.is_symlink() \
                and artifacts.resolve() == artifacts:
            try:
                collector.atomic_json(artifacts / "command-manifest.json", {
                    "schema_version": 1, "kind": "lint-workgraph-run", "status": "failed",
                    "error": str(exc), "error_type": type(exc).__name__,
                    "workspace": str(workspace), "inventory_sha256": inventory_hash,
                    "timing": {**stages, "total_seconds": time.monotonic() - started},
                })
            except OSError:
                pass
        print(f"lint-workgraph: {type(exc).__name__}: {exc}; artifacts={artifacts}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
