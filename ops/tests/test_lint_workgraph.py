"""Whole-inventory command tests; all native sessions/captures are synthetic."""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("final_workgraph", ROOT / "ops/scripts/lint-workgraph.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class Fixture:
    def __init__(self, base):
        self.workspace = base / "unrelated-target"
        self.workspace.mkdir()
        self.artifacts = base / "graph.artifacts"
        self.inventory_path, self.output, self.report = base / "inventory.json", base / "graph.json", base / "graph.md"
        self.write(self.workspace / ".git/HEAD", "a" * 40)
        self.write(self.workspace / "src/lib.rs", "fn helper() {}\n")
        self.write(self.workspace / "src/use.rs", "fn consumer() { helper(); }\n")
        self.write(self.workspace / "src/local.rs", "/// Literal documentation.\nfn local() {}\n")
        self.write(self.workspace / "src/unlocated.rs", "// No native declaration was indexed.\n")
        self.inventory = {
            "schema_version": 1,
            "clippy": [self.record("C1", "clippy::unused_async", "src/lib.rs", "first"),
                       self.record("C2", "clippy::too_many_lines", "src/lib.rs", "second"),
                       self.record("C3", "clippy::doc_markdown", "src/local.rs", "local")],
            "sonar": [
                {"id": "S1", "rule": "clippy::unused_async", "message": "first", "file": "src/lib.rs",
                 "range": [1, 0, 1, 5], "issue_keys": ["issue-1", "issue-2"]},
                {"id": "S2", "rule": "native:unknown", "message": "missing coordinates",
                 "file": "src/unlocated.rs", "range": None, "issue_keys": ["issue-3"]}],
            "matches": [{"clippy_id": "C1", "sonar_id": "S1"}],
            "unmerged_hints": [{"clippy_id": "C2", "sonar_id": "S2", "type": "uncertain"}],
            "ambiguous_exact_matches": [], "limitations": ["Synthetic exact identities only."],
            "counts": {"clippy_unique": 3, "sonar_unique_sites": 2, "sonar_raw_keys": 3,
                       "exact_intersection": 1, "strict_union": 4},
        }
        self.write(self.inventory_path, self.inventory)
        self.capture = None

    @staticmethod
    def record(identifier, rule, path, message):
        return {"id": identifier, "rule": rule, "message": message,
                "primary_spans": [{"file": path, "range": [1, 0, 1, 5]}],
                "provenance": [{"input": "synthetic.jsonl", "row": 1, "level": "warning"}]}

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n"
        path.write_bytes(raw.encode("utf-8"))

    def ref(self, relative, value):
        self.write(self.artifacts / relative, value)
        return {"path": relative, "sha256": tool.digest(self.artifacts / relative)}

    def query(self, identifier, suffix, arguments, payload, count=0):
        ref = self.ref(identifier + ".json", {"isError": False, "content": [
            {"type": "text", "text": json.dumps(payload)}], "structuredContent": None})
        paged = suffix in tool.PAGED
        return {"id": identifier, "tool": "rust-code-mcp_1mcp_" + suffix,
                "arguments": {"directory": str(self.workspace), **arguments},
                "artifact": ref["path"], "artifact_sha256": ref["sha256"], "status": "ok",
                "pagination": {"status": "complete" if paged else "not_applicable", "pages": 1,
                               "returned": count, "total": count if paged else None,
                               "reason": "captured indexed scope only"},
                "limitations": [], "duration_seconds": 0.01, "reused_count": 0}

    def create(self):
        self.artifacts.mkdir()
        server = self.ref("server.json", {"name": "invented-native-server"})
        catalog = self.ref("catalogue.json", [
            {"name": "rust-code-mcp_1mcp_" + suffix,
             "inputSchema": {"properties": {name: {} for name in names}, "required": ["directory"]}}
            for suffix, names in (
                ("build_codemap", ("directory", "seed_qualified_names", "depth", "max_nodes")),
                ("who_uses", ("directory", "target", "offset", "limit", "summary")),
                ("calls_from", ("directory", "caller", "offset", "limit", "summary")),
                ("who_imports", ("directory", "target", "offset", "limit", "summary")),
            )])
        native_nodes, items = [], []
        for identifier, name, file in (("ni1", "helper", "src/lib.rs"), ("ni2", "consumer", "src/use.rs")):
            data = (self.workspace / file).read_bytes()
            node = {"id": [len(items) + 1], "qualified_name": "aster::" + name,
                    "item_kind": "Function", "file": file, "span": [0, data.index(b"}") + 1], "line": 1}
            native_nodes.append(node)
            items.append({"id": identifier, "native_id": node["id"], "selector": node["qualified_name"],
                          "kind": "Function", "visibility": "private", "path": file,
                          "range": tool.collector.native_location(data, node), "location_status": "verified",
                          "source_sha256": hashlib.sha256(data).hexdigest(), "snapshot_id": "old-native-snapshot",
                          "native": {k: node[k] for k in ("file", "span", "line")},
                          "evidence_refs": ["hydrate"], "reasons": []})
        hydration = self.query("hydrate", "build_codemap", {"seed_qualified_names": ["aster::helper", "aster::consumer"],
                               "depth": 0, "max_nodes": 500}, {"snapshot_id": "old-native-snapshot",
                               "nodes": native_nodes, "edges": [], "diagnostics": ["Backend snapshot age warning"]}, 2)
        data = (self.workspace / "src/use.rs").read_bytes()
        start = data.index(b"helper")
        row = {"file": "src/use.rs", "start": start, "end": start + 6, "category": "Other",
               "consumer_module": "aster", "consumer_function": "aster::consumer"}
        args = {"target": "aster::helper", "offset": 0, "limit": 100, "summary": False}
        incoming = self.query("uses", "who_uses", args, {"target": "aster::helper", "offset": 0, "limit": 100,
                             "summary": False, "returned_match_count": 1, "total_match_count": 1, "usages": [row]}, 1)
        outgoing = self.query("out", "calls_from", {"caller": "aster::helper", "offset": 0, "limit": 100,
                             "summary": False}, {"caller": "aster::helper", "offset": 0, "limit": 100,
                             "summary": False, "returned_match_count": 0, "total_match_count": 0, "call_sites": []})
        imports = self.query("imports", "who_imports", args, {"target": "aster::helper", "offset": 0, "limit": 100,
                            "summary": False, "returned_match_count": 0, "total_match_count": 0, "bindings": []})
        routing = tool.policy.route_inventory(self.inventory)
        diagnostics = []
        for route in routing["diagnostics"]:
            key = route["diagnostic_key"]
            local, unlocated = route["scope"] == "local", key == "sonar:S2"
            diagnostics.append({
                "diagnostic_key": key, "route": route["scope"],
                "files": ["src/local.rs" if local else "src/unlocated.rs" if unlocated else "src/lib.rs"],
                "item_ids": [] if local or unlocated else ["ni1"],
                "query_ids": [] if local or unlocated else ["hydrate", "uses", "out", "imports"],
                "attempt_outcome": "skipped_local" if local else "unresolved_localization" if unlocated else
                "queried" if key == "clippy:C1" else "reused_query",
                "localization_status": "unknown" if local or unlocated else "candidate",
                "reasons": ["Missing indexed native location"] if unlocated else [],
            })
        sources = [{"path": p.relative_to(self.workspace).as_posix(), "sha256": tool.digest(p),
                    "before_sha256": tool.digest(p), "after_sha256": tool.digest(p), "status": "verified"}
                   for p in sorted(self.workspace.rglob("*.rs"))]
        self.capture = {
            "schema_version": 1, "kind": "lint-native-dependency-capture", "status": "partial",
            "workspace": str(self.workspace), "artifact_root": str(self.artifacts),
            "orientation": "consumer_to_provider", "inventory_sha256": tool.digest(self.inventory_path),
            "captured_at": "2026-11-14T00:00:00Z", "target_head": "a" * 40, "source_files": sources,
            "backend": {"server_ref": server, "catalogue_ref": catalog,
                        "workspace_evidence": {"status": "requested_directory_only",
                                               "requested_workspace": str(self.workspace)},
                        "snapshot_ids": ["old-native-snapshot"], "warnings": ["Backend snapshot age warning"],
                        "coverage": {k: "unknown" for k in tool.planner.COVERAGE},
                        "scope": tool.SCOPE, "context_refs": []},
            "queries": [hydration, incoming, outgoing, imports], "items": items, "diagnostics": diagnostics,
            "dependencies": [{
                "id": "dep1", "kind": "Uses", "origin_item_id": "ni2", "destination_item_id": "ni1",
                "origin_path": "src/use.rs", "destination_path": "src/lib.rs",
                "native_origin": {"selector": "aster::consumer", "file": "src/use.rs",
                                  "module": "aster", "span": [start, start + 6]},
                "native_destination": {"selector": "aster::helper"}, "native": row,
                "evidence_refs": ["uses"], "qualification": "source_verified", "reasons": [],
                "snapshot_ids": ["old-native-snapshot"]}],
            "limits": {**tool.DEFAULTS, "pending_diagnostics": 0},
            "timing": {"total_seconds": 0.1, "stages": {"discovery": 0.02},
                       "requests": 4, "query_records": 4, "cache_hits": 0, "reused_queries": 8},
            "limitations": ["Direct indexed scope, unknown macros/features/tests; no historical binding."],
        }
        self.persist()
        return self.capture

    def persist(self):
        self.write(self.artifacts / "native-capture.json", self.capture)
        self.write(self.artifacts / "run-manifest.json", {"kind": "lint-native-capture-run",
                                                        "status": self.capture["status"]})

    def model(self):
        self.persist()
        return tool.validate_capture(self.capture, self.workspace, self.artifacts, self.inventory,
                                     tool.digest(self.inventory_path), "a" * 40)

    def graph(self):
        return tool.assemble(self.model(), self.workspace, self.artifacts, self.inventory)

    def args(self):
        return ["--workspace", str(self.workspace), "--inventory", str(self.inventory_path),
                "--output", str(self.output), "--report", str(self.report)]

    def patch_raw(self, query_id, modify):
        query = next(q for q in self.capture["queries"] if q["id"] == query_id)
        path = self.artifacts / query["artifact"]
        raw = tool.read_json(path)
        payload = json.loads(raw["content"][0]["text"])
        modify(payload)
        raw["content"][0]["text"] = json.dumps(payload)
        self.write(path, raw)
        query["artifact_sha256"] = tool.digest(path)


class WorkgraphTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="final-graph-", dir=ROOT / ".tmp")
        self.addCleanup(self.directory.cleanup)
        self.f = Fixture(Path(self.directory.name))

    def test_generic_inventory_graph_keeps_all_routes_provenance_and_outside_endpoint(self):
        self.f.create()
        graph = self.f.graph()
        self.assertEqual(graph["accounting"]["retained_records"], 5)
        self.assertEqual(graph["accounting"]["strict_union"], 4)
        self.assertEqual(graph["accounting"]["sonar_raw_keys"], 3)
        self.assertEqual(graph["accounting"]["transverse_attempted"], 4)
        self.assertEqual(graph["accounting"]["transverse_query_served"], 3)
        self.assertEqual(graph["accounting"]["terminal_outcomes"]["skipped_local"], 1)
        self.assertIsNone(graph["accounting"]["semantic_defect_count"])
        nodes = {n["path"]: n for n in graph["work_graph"]["nodes"]}
        self.assertEqual(set(nodes), {"src/lib.rs", "src/local.rs", "src/unlocated.rs", "src/use.rs"})
        self.assertEqual(nodes["src/use.rs"]["diagnostic_keys"], [])
        self.assertEqual(len(graph["work_graph"]["proposed_groups"]), 4)
        edge = graph["work_graph"]["edges"][0]
        self.assertEqual((edge["origin_path"], edge["destination_path"]), ("src/use.rs", "src/lib.rs"))
        self.assertEqual(edge["qualification"], "source_verified")
        self.assertEqual(graph["native_capture"]["backend"]["warnings"], ["Backend snapshot age warning"])
        self.assertEqual(graph["work_graph"]["coverage"]["hard_edges"], 0)
        self.assertEqual(graph["work_graph"]["global_independence"], "unproven")
        self.assertEqual(next(q for q in graph["queries"] if q["id"] == "uses")["served_diagnostic_keys"],
                         ["clippy:C1", "clippy:C2", "sonar:S1"])
        self.assertIn("not recursive whole-workspace closure", tool.report(graph))

    def test_outgoing_native_edge_keeps_consumer_provider_direction_and_no_hard_union(self):
        self.f.create()
        self.f.write(self.f.workspace / "src/lib.rs", "fn helper() { consumer(); }\n")
        data = (self.f.workspace / "src/lib.rs").read_bytes()
        node = {"id": [1], "qualified_name": "aster::helper", "item_kind": "Function",
                "file": "src/lib.rs", "span": [0, data.index(b"}") + 1], "line": 1}
        self.f.patch_raw("hydrate", lambda p: p["nodes"].__setitem__(0, node))
        item = self.f.capture["items"][0]
        item.update(native={k: node[k] for k in ("file", "span", "line")},
                    range=tool.collector.native_location(data, node), source_sha256=tool.digest(self.f.workspace / "src/lib.rs"))
        for source in self.f.capture["source_files"]:
            if source["path"] == "src/lib.rs":
                source.update(sha256=item["source_sha256"], before_sha256=item["source_sha256"],
                              after_sha256=item["source_sha256"])
        start = data.index(b"consumer")
        row = {"file": "src/lib.rs", "start": start, "end": start + 8,
               "caller_qualified_name": "aster::helper", "callee_qualified_name": "aster::consumer",
               "category": "Other"}
        self.f.patch_raw("out", lambda p: p.update(call_sites=[row], returned_match_count=1, total_match_count=1))
        self.f.capture["queries"][2]["pagination"].update(returned=1, total=1)
        self.f.capture["dependencies"].append({
            "id": "dep2", "kind": "CallsFrom", "origin_item_id": "ni1", "destination_item_id": "ni2",
            "origin_path": "src/lib.rs", "destination_path": "src/use.rs",
            "native_origin": {"selector": "aster::helper", "file": "src/lib.rs", "span": [start, start + 8]},
            "native_destination": {"selector": "aster::consumer"}, "native": row, "evidence_refs": ["out"],
            "qualification": "source_verified", "reasons": [], "snapshot_ids": ["old-native-snapshot"]})
        result = self.f.graph()
        edges = result["work_graph"]["edges"]
        self.assertEqual(len(edges), 2)
        self.assertTrue(any(e["origin_path"] == "src/lib.rs" and e["destination_path"] == "src/use.rs"
                            and e["qualification"] == "source_verified" for e in edges))
        self.assertEqual(result["work_graph"]["coverage"]["hard_edges"], 0)
        self.assertEqual(len(result["work_graph"]["proposed_groups"]), 4)

    def test_importer_file_requires_hydrated_module_not_directory_inference(self):
        self.f.create()
        file = "src/not_the_module_name.rs"
        self.f.write(self.f.workspace / file, "mod consumer_mod {}\n")
        data = (self.f.workspace / file).read_bytes()
        native = {"id": [3], "qualified_name": "aster::consumer_mod", "item_kind": "Module",
                  "file": file, "span": [0, data.index(b"}") + 1], "line": 1}
        self.f.patch_raw("hydrate", lambda p: p["nodes"].append(native))
        hashed = tool.digest(self.f.workspace / file)
        self.f.capture["source_files"].append({"path": file, "sha256": hashed, "before_sha256": hashed,
                                                "after_sha256": hashed, "status": "verified"})
        self.f.capture["items"].append({
            "id": "ni3", "native_id": [3], "selector": "aster::consumer_mod", "kind": "Module",
            "visibility": "private", "path": file, "range": tool.collector.native_location(data, native),
            "location_status": "verified", "source_sha256": hashed, "snapshot_id": "old-native-snapshot",
            "native": {k: native[k] for k in ("file", "span", "line")}, "evidence_refs": ["hydrate"], "reasons": []})
        row = {"from_module": "aster::consumer_mod", "target": "aster::helper"}
        self.f.patch_raw("imports", lambda p: p.update(bindings=[row], returned_match_count=1, total_match_count=1))
        self.f.capture["queries"][3]["pagination"].update(returned=1, total=1)
        self.f.capture["dependencies"].append({
            "id": "dep2", "kind": "Imports", "origin_item_id": "ni3", "destination_item_id": "ni1",
            "origin_path": file, "destination_path": "src/lib.rs", "native_origin": {"selector": "aster::consumer_mod"},
            "native_destination": {"selector": "aster::helper"}, "native": row, "evidence_refs": ["imports"],
            "qualification": "source_verified", "reasons": [], "snapshot_ids": ["old-native-snapshot"]})
        result = self.f.graph()
        self.assertTrue(any(e["origin_path"] == file and e["qualification"] == "source_verified"
                            for e in result["work_graph"]["edges"]))

    def test_cli_calls_one_frozen_adapter_with_full_inventory_and_protected_outputs(self):
        calls = []

        async def collect(workspace, inventory, artifacts, **kwargs):
            calls.append((workspace, inventory, artifacts, kwargs))
            return self.f.create()

        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "collect_native_dependencies", side_effect=collect), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 0)
        self.assertEqual(len(calls), 1)
        workspace, inventory, artifacts, kwargs = calls[0]
        self.assertEqual((workspace, inventory, artifacts),
                         (self.f.workspace, self.f.inventory_path, self.f.artifacts))
        self.assertEqual(kwargs["protected_paths"], (self.f.output, self.f.report))
        self.assertEqual(set(kwargs), {"url", "protected_paths", *tool.DEFAULTS})
        self.assertNotIn("seeds", kwargs)
        result = tool.read_json(self.f.output)
        self.assertEqual(result["status"], "partial")
        self.assertNotEqual(result["target_head"], result["tool_head"])
        manifest = tool.read_json(self.f.artifacts / "command-manifest.json")
        self.assertGreaterEqual(manifest["timing"]["publication_seconds"], 0)
        self.assertGreaterEqual(manifest["timing"]["total_seconds"], manifest["timing"]["collection_seconds"])
        self.assertEqual(manifest["output"]["sha256"], tool.digest(self.f.output))

    def test_unknown_rule_is_transverse_not_a_sample(self):
        self.f.inventory["clippy"][1]["rule"] = "unrecognized:new"
        self.f.write(self.f.inventory_path, self.f.inventory)
        self.f.create()
        graph = self.f.graph()
        row = next(r for r in graph["diagnostics"] if r["key"] == "clippy:C2")
        self.assertEqual(row["route"], "transverse")
        self.assertEqual(row["attempt_outcome"], "reused_query")

    def test_native_items_all_kinds_and_unlocated_items_are_preserved(self):
        self.f.create()
        for i, kind in enumerate(("Method", "Struct", "Trait", "Module", "unknown"), 3):
            self.f.capture["items"].append({
                "id": "ni" + str(i), "native_id": None, "selector": "aster::missing_" + str(i), "kind": kind,
                "visibility": "private", "path": None, "range": None, "location_status": "unknown",
                "source_sha256": None, "snapshot_id": None, "native": {"file": None, "span": None, "line": None},
                "evidence_refs": ["hydrate"], "reasons": ["Missing/ambiguous native location"],
            })
        result = self.f.graph()
        self.assertEqual(len(result["native_capture"]["items"]), 7)
        for kind in ("Function", "Method", "Struct", "Trait", "Module", "unknown"):
            self.assertIn(kind, result["accounting"]["item_kind_counts"])
        self.assertEqual(len(result["work_graph"]["nodes"]), 4)

    def test_current_private_method_struct_trait_module_projection_uses_native_witnesses(self):
        self.f.create()
        query = self.f.capture["queries"][0]
        raw = tool.read_json(self.f.artifacts / query["artifact"])
        payload = json.loads(raw["content"][0]["text"])
        cases = [
            ("Method", "aster::Thing::go", "struct Thing;\nimpl Thing {\n    fn go(&self) {}\n}\n", b"fn go"),
            ("Struct", "aster::Data", "struct Data;\n", b"struct"),
            ("Trait", "aster::Capability", "trait Capability {}\n", b"trait"),
            ("Module", "aster::area", "mod area {}\n", b"mod"),
        ]
        for i, (kind, selector, code, marker) in enumerate(cases, 3):
            file = "src/kind_" + str(i) + ".rs"
            self.f.write(self.f.workspace / file, code)
            data = (self.f.workspace / file).read_bytes()
            start = data.index(marker)
            end = data.index(b"}", start) + 1 if b"}" in data[start:] else data.index(b";", start) + 1
            native = {"id": [i], "qualified_name": selector, "item_kind": kind, "file": file,
                      "span": [start, end], "line": data[:start].count(b"\n") + 1}
            payload["nodes"].append(native)
            self.f.capture["items"].append({
                "id": "ni" + str(i), "native_id": [i], "selector": selector, "kind": kind,
                "visibility": "private", "path": file, "range": tool.collector.native_location(data, native),
                "location_status": "verified", "source_sha256": tool.digest(self.f.workspace / file),
                "snapshot_id": "old-native-snapshot", "native": {k: native[k] for k in ("file", "span", "line")},
                "evidence_refs": ["hydrate"], "reasons": [],
            })
            hashed = tool.digest(self.f.workspace / file)
            self.f.capture["source_files"].append({"path": file, "sha256": hashed, "before_sha256": hashed,
                                                    "after_sha256": hashed, "status": "verified"})
        raw["content"][0]["text"] = json.dumps(payload)
        self.f.write(self.f.artifacts / query["artifact"], raw)
        query["artifact_sha256"] = tool.digest(self.f.artifacts / query["artifact"])
        result = self.f.graph()
        self.assertTrue(all(result["item_checks"]["ni" + str(i)]["status"] == "source_verified"
                            for i in range(3, 7)))
        # Hydration is context, not an unsolicited whole-workspace file expansion.
        self.assertEqual(len(result["work_graph"]["nodes"]), 4)

    def test_current_source_failure_preserves_backend_observed_edge_and_age_warning(self):
        self.f.create()
        self.f.write(self.f.workspace / "src/use.rs", "fn changed() { helper(); }\n")
        result = self.f.graph()
        edge = result["work_graph"]["edges"][0]
        self.assertEqual(edge["qualification"], "backend_observed")
        self.assertEqual(result["item_checks"]["ni2"]["status"], "backend_observed")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["native_capture"]["backend"]["warnings"], ["Backend snapshot age warning"])

    def test_unknown_endpoint_is_queued_without_discarding_native_fact(self):
        self.f.create()
        dep = self.f.capture["dependencies"][0]
        dep.update(destination_item_id=None, destination_path=None, qualification="unresolved")
        result = self.f.graph()
        self.assertEqual(result["work_graph"]["edges"], [])
        self.assertEqual(len(result["native_dependencies"]), 1)
        self.assertTrue(any(u["id"] == "dependency:dep1" for u in result["work_graph"]["unresolved_observations"]))

    def test_forged_current_projection_does_not_become_source_verified(self):
        self.f.create()
        self.f.capture["items"][1]["range"]["end_byte"] -= 1
        result = self.f.graph()
        self.assertEqual(result["work_graph"]["edges"][0]["qualification"], "backend_observed")
        self.assertEqual(result["item_checks"]["ni2"]["status"], "backend_observed")

    def test_normalized_file_claim_without_native_file_witness_cannot_create_file_edge(self):
        self.f.create()
        self.f.patch_raw("hydrate", lambda p: p["nodes"][0].update(file=None))
        self.f.capture["items"][0]["native"]["file"] = None
        result = self.f.graph()
        self.assertEqual(result["work_graph"]["edges"], [])
        self.assertEqual(result["item_checks"]["ni1"]["status"], "unresolved")
        self.assertEqual(len(result["native_dependencies"]), 1)

    def test_missing_primary_locations_keep_named_unlocated_record_node(self):
        self.f.inventory["clippy"][1]["primary_spans"] = []
        self.f.write(self.f.inventory_path, self.f.inventory)
        self.f.create()
        row = next(d for d in self.f.capture["diagnostics"] if d["diagnostic_key"] == "clippy:C2")
        row.update(files=[], item_ids=[], query_ids=[], attempt_outcome="unresolved_localization",
                   localization_status="unknown", reasons=["No primary source file"])
        result = self.f.graph()
        self.assertEqual(len(result["diagnostics"]), 5)
        self.assertTrue(any(n["path"] == "unlocated:clippy:C2" for n in result["work_graph"]["nodes"]))

    def test_native_exact_diagnostic_claim_without_historical_binding_is_not_upgraded(self):
        self.f.create()
        self.f.capture["diagnostics"][0]["localization_status"] = "exact"
        result = self.f.graph()
        row = next(d for d in result["diagnostics"] if d["key"] == "clippy:C1")
        self.assertEqual(row["localization_status"], "candidate")
        self.assertTrue(result["validation_issues"])

    def test_forged_dependency_or_selector_lacks_authority(self):
        self.f.create()
        original = copy.deepcopy(self.f.capture["dependencies"][0])
        self.f.capture["dependencies"][0]["native"]["start"] += 1
        self.assertEqual(self.f.graph()["work_graph"]["edges"], [])
        self.f.capture["dependencies"][0] = copy.deepcopy(original)
        self.f.capture["dependencies"][0]["native_destination"]["selector"] = "aster::other"
        self.assertEqual(self.f.graph()["work_graph"]["edges"], [])

    def test_pagination_gap_repeat_and_total_drift_cannot_be_complete_current_evidence(self):
        self.f.create()
        for modify in (
            lambda p: p.update(offset=1),
            lambda p: p.update(total_match_count=2),
            lambda p: p["usages"].append(copy.deepcopy(p["usages"][0])),
        ):
            with self.subTest(modify=modify):
                original = (self.f.artifacts / "uses.json").read_bytes()
                self.f.patch_raw("uses", modify)
                result = self.f.graph()
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["work_graph"]["edges"][0]["qualification"], "backend_observed")
                self.assertTrue(result["validation_issues"])
                (self.f.artifacts / "uses.json").write_bytes(original)
                self.f.capture["queries"][1]["artifact_sha256"] = tool.digest(self.f.artifacts / "uses.json")

    def test_wrong_workspace_artifact_authority_or_orientation_is_fatal(self):
        self.f.create()
        for key, value in (("workspace", str(self.f.workspace.parent)), ("artifact_root", str(self.f.workspace)),
                           ("orientation", "provider_to_consumer"), ("inventory_sha256", "0" * 64)):
            with self.subTest(key=key):
                original = self.f.capture[key]
                self.f.capture[key] = value
                with self.assertRaises(tool.Error):
                    self.f.model()
                self.f.capture[key] = original

    def test_raw_artifact_hash_or_escape_is_fatal(self):
        self.f.create()
        original = self.f.capture["queries"][1]["artifact"]
        self.f.capture["queries"][1]["artifact"] = "../inventory.json"
        with self.assertRaises(tool.collector.EvidenceError):
            self.f.model()
        self.f.capture["queries"][1]["artifact"] = original
        self.f.write(self.f.artifacts / original, {"changed": True})
        with self.assertRaises(tool.Error):
            self.f.model()

    def test_missing_or_duplicated_diagnostics_and_route_file_reassignment_reject(self):
        self.f.create()
        original = copy.deepcopy(self.f.capture["diagnostics"])
        for modify in (
            lambda rows: rows.pop(),
            lambda rows: rows.append(copy.deepcopy(rows[0])),
            lambda rows: rows[0].update(route="local"),
            lambda rows: rows[0].update(files=["src/use.rs"]),
            lambda rows: rows[0].update(item_ids=["ni2"]),
        ):
            with self.subTest(modify=modify):
                self.f.capture["diagnostics"] = copy.deepcopy(original)
                modify(self.f.capture["diagnostics"])
                with self.assertRaises(tool.Error):
                    self.f.model()

    def test_local_record_file_can_be_a_dependency_without_dedicated_local_query(self):
        self.f.inventory["clippy"][2]["primary_spans"][0]["file"] = "src/use.rs"
        self.f.write(self.f.inventory_path, self.f.inventory)
        self.f.create()
        next(d for d in self.f.capture["diagnostics"] if d["diagnostic_key"] == "clippy:C3")["files"] = ["src/use.rs"]
        result = self.f.graph()
        local = next(d for d in result["diagnostics"] if d["key"] == "clippy:C3")
        self.assertEqual(local["attempt_outcome"], "skipped_local")
        self.assertEqual(local["query_ids"], [])
        self.assertTrue(any(e["origin_path"] == "src/use.rs" for e in result["work_graph"]["edges"]))

    def test_missing_ranges_and_outside_paths_remain_in_inventory_graph(self):
        self.f.inventory["sonar"][1]["file"] = "../unknown.rs"
        self.f.write(self.f.inventory_path, self.f.inventory)
        self.f.create()
        next(d for d in self.f.capture["diagnostics"] if d["diagnostic_key"] == "sonar:S2")["files"] = ["../unknown.rs"]
        result = self.f.graph()
        self.assertTrue(any(n["path"] == "../unknown.rs" and n["source_status"] == "unresolved_path"
                            for n in result["work_graph"]["nodes"]))
        self.assertEqual(len(result["diagnostics"]), 5)

    def test_budget_and_deadline_stops_are_nonzero_with_all_records_preserved(self):
        for outcome in ("not_attempted_budget", "not_attempted_deadline"):
            with self.subTest(outcome=outcome):
                # Separate output paths make each invocation an independent fresh run.
                self.f.artifacts = self.f.artifacts.with_name(outcome + ".artifacts")
                self.f.output = self.f.output.with_name(outcome + ".json")
                self.f.report = self.f.report.with_name(outcome + ".md")

                async def collect(*args, **kwargs):
                    self.f.create()
                    self.f.capture["diagnostics"][0]["attempt_outcome"] = outcome
                    self.f.persist()
                    return self.f.capture

                with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                        mock.patch.object(tool.collector, "collect_native_dependencies", side_effect=collect), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(tool.main(self.f.args() + ["--artifacts", str(self.f.artifacts)]), 3)
                result = tool.read_json(self.f.output)
                self.assertEqual(len(result["diagnostics"]), 5)
                self.assertEqual(result["accounting"]["not_attempted"], 1)
                self.assertGreaterEqual(result["accounting"]["transverse_unresolved"], 0)

    def test_initial_inventory_replacement_cannot_bind_old_local_route_to_new_hash(self):
        reader = tool.collector.read_native_inventory
        original_hash = tool.digest(self.f.inventory_path)

        def replace_after_read(path):
            parsed, hashed = reader(path)
            replacement = copy.deepcopy(parsed)
            replacement["clippy"][2]["rule"] = "clippy::too_many_lines"
            self.f.write(path, replacement)
            self.f.inventory = replacement
            return parsed, hashed

        async def collect(*args, **kwargs):
            return self.f.create()

        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "read_native_inventory", side_effect=replace_after_read), \
                mock.patch.object(tool.collector, "collect_native_dependencies", side_effect=collect), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 2)
        self.assertFalse(self.f.output.exists())
        manifest = tool.read_json(self.f.artifacts / "command-manifest.json")
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["inventory_sha256"], original_hash)

    def test_final_inventory_drift_preserves_existing_accepted_graph(self):
        self.f.write(self.f.output, {"kind": "lint-workgraph", "previous": True})
        before = self.f.output.read_bytes()

        async def collect(*args, **kwargs):
            self.f.create()
            self.f.write(self.f.inventory_path, {**self.f.inventory, "changed": True})
            return self.f.capture

        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "collect_native_dependencies", side_effect=collect), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 2)
        self.assertEqual(self.f.output.read_bytes(), before)
        self.assertTrue((self.f.artifacts / "native-capture.json").exists())

    def test_artifact_root_existing_or_output_input_alias_fails_before_collection(self):
        self.f.artifacts.mkdir()
        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "collect_native_dependencies") as collect, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 2)
            self.assertEqual(tool.main(self.f.args() + ["--artifacts", str(self.f.artifacts.with_name("fresh")),
                                                      "--output", str(self.f.inventory_path)]), 2)
            collect.assert_not_called()

    def test_hardlink_output_input_alias_and_source_alias_are_not_merged(self):
        os.link(self.f.inventory_path, self.f.output)
        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "collect_native_dependencies") as collect, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 2)
            collect.assert_not_called()
        self.f.create()
        os.link(self.f.workspace / "src/lib.rs", self.f.workspace / "src/alias.rs")
        source = copy.deepcopy(self.f.capture["source_files"][0])
        source["path"] = "src/alias.rs"
        self.f.capture["source_files"].append(source)
        with self.assertRaises(tool.Error):
            self.f.model()

    def test_no_usable_file_boundaries_returns_explicit_nonzero_after_saving_all_records(self):
        async def collect(*args, **kwargs):
            self.f.create()
            self.f.capture["dependencies"][0].update(destination_item_id=None, destination_path=None,
                                                     qualification="unresolved")
            self.f.persist()
            return self.f.capture

        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "collect_native_dependencies", side_effect=collect), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 4)
        result = tool.read_json(self.f.output)
        self.assertEqual(len(result["diagnostics"]), 5)
        self.assertEqual(result["work_graph"]["edges"], [])

    def test_source_change_during_output_staging_does_not_publish_old_projection(self):
        async def collect(*args, **kwargs):
            return self.f.create()

        real_fsync = tool.planner.os.fsync

        def mutate_source(fd):
            real_fsync(fd)
            self.f.write(self.f.workspace / "src/use.rs", "// changed after validation\n")

        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "collect_native_dependencies", side_effect=collect), \
                mock.patch.object(tool.planner.os, "fsync", side_effect=mutate_source), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 2)
        self.assertFalse(self.f.output.exists())
        self.assertTrue((self.f.artifacts / "native-capture.json").exists())

    def test_unsupported_raw_query_is_not_an_empty_success(self):
        self.f.create()
        query = self.f.capture["queries"][1]
        self.f.write(self.f.artifacts / query["artifact"], {"isError": True, "content": [], "structuredContent": None})
        query["artifact_sha256"] = tool.digest(self.f.artifacts / query["artifact"])
        result = self.f.graph()
        self.assertEqual(len(result["diagnostics"]), 5)
        self.assertEqual(result["work_graph"]["edges"], [])
        self.assertTrue(result["validation_issues"])

    def test_atomic_publication_failure_keeps_old_output_and_failure_evidence(self):
        self.f.write(self.f.output, {"kind": "lint-workgraph", "old": True})
        before = self.f.output.read_bytes()

        async def collect(*args, **kwargs):
            return self.f.create()

        with mock.patch.object(tool.collector, "validate_workspace", return_value=self.f.workspace), \
                mock.patch.object(tool.collector, "collect_native_dependencies", side_effect=collect), \
                mock.patch.object(tool.planner.os, "replace", side_effect=OSError("synthetic replace failure")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(self.f.args()), 2)
        self.assertEqual(self.f.output.read_bytes(), before)
        self.assertTrue((self.f.artifacts / "native-capture.json").exists())
        self.assertFalse(list(self.f.output.parent.glob(".graph.json*.tmp")))

    def test_pure_assembly_is_deterministic_and_does_not_claim_recursive_or_independent(self):
        self.f.create()
        first, second = self.f.graph(), self.f.graph()
        self.assertEqual(tool.canonical(first), tool.canonical(second))
        self.assertEqual(tool.report(first), tool.report(second))
        self.assertTrue(all(g["readiness"] == "review_required" for g in first["work_graph"]["proposed_groups"]))
        self.assertEqual(first["work_graph"]["coverage"]["edge_absence"], "not_observed")

    def test_corpus_alias_check_has_linear_filesystem_operations(self):
        raw = [self.f.artifacts / f"raw-{i}.json" for i in range(320)]
        sources = [self.f.workspace / "src" / f"source-{i}.rs" for i in range(20)]
        identities = {path: i for i, path in enumerate(raw + sources, 1)}
        with mock.patch.object(Path, "exists", return_value=True), \
                mock.patch.object(Path, "resolve", autospec=True, side_effect=lambda path: path) as resolve, \
                mock.patch.object(Path, "stat", autospec=True,
                                  side_effect=lambda path: SimpleNamespace(st_dev=1, st_ino=identities[path])) as stat, \
                mock.patch.object(Path, "samefile", return_value=False) as samefile:
            tool.verify_corpus_separation(raw, sources)
        operations = resolve.call_count + stat.call_count + samefile.call_count
        self.assertLessEqual(operations, 2 * (len(raw) + len(sources)))
        self.assertEqual(samefile.call_count, 0)

    def test_corpus_raw_source_and_raw_raw_hardlinks_and_duplicate_paths_reject(self):
        self.f.artifacts.mkdir()
        raw = self.f.artifacts / "one.json"
        self.f.write(raw, "raw bytes")
        source = self.f.workspace / "src/lib.rs"
        source_alias = self.f.artifacts / "source-alias.json"
        os.link(source, source_alias)
        with self.assertRaises((tool.Error, tool.collector.EvidenceError)):
            tool.verify_corpus_separation([raw, source_alias], [source])
        raw_alias = self.f.artifacts / "two.json"
        os.link(raw, raw_alias)
        with self.assertRaises((tool.Error, tool.collector.EvidenceError)):
            tool.verify_corpus_separation([raw, raw_alias], [source])
        with self.assertRaises((tool.Error, tool.collector.EvidenceError)):
            tool.verify_corpus_separation([raw, raw], [source])


if __name__ == "__main__":
    unittest.main()
