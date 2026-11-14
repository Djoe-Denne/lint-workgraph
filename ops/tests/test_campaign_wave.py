"""Synthetic wave/capability tests; no native clients, workers or application sources."""

import contextlib
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("campaign_wave_tests_tool", ROOT / "ops/scripts/campaign-wave.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def fixture():
    lots, files, units = [], [], []
    for letter, weight in (("a", 3), ("b", 5), ("c", 2), ("d", 1), ("e", 1)):
        identifier, path = "lot-" + letter, "src/" + letter + ".rs"
        ids = [letter + str(i) for i in range(weight)]
        lots.append({"id": identifier, "workload": weight, "writable_files": [path],
                     "readonly_context": ["context.rs"], "strict_unit_ids": ids, "boundary_edge_ids": [],
                     "internal_edge_ids": [], "review_tasks": [{"kind": "source_review"}]})
        files.append({"path": path, "source_status": "verified_current", "write_owner": identifier})
        units.extend({"id": key, "lot_id": identifier, "owner_path": path} for key in ids)
    files.append({"path": "context.rs", "source_status": "verified_current", "write_owner": None})
    units.append({"id": "manual", "lot_id": None, "owner_path": None})
    graph = {"schema_version": 1, "kind": "lint-work-lots", "lots": lots, "files": files, "units": units,
             "unresolved_queue": [{"unit_id": "manual"}],
             "accounting": {"assigned_units": 12, "queued_units": 1, "strict_units": 13, "writable_files": 5},
             "inherited": {"graph_status": "partial", "coverage": {"freshness": "unknown"}},
             "limitations": ["Synthetic partial scope"], "edge_registry": [
                 {"id": "backend-ab", "origin_path": "src/a.rs", "destination_path": "src/b.rs",
                  "qualification": "backend_observed"},
                 {"id": "verified-bc", "origin_path": "src/b.rs", "destination_path": "src/c.rs",
                  "qualification": "source_verified"},
                 {"id": "context", "origin_path": "src/a.rs", "destination_path": "context.rs",
                  "qualification": "backend_observed"},
                 {"id": "self", "origin_path": "src/c.rs", "destination_path": "src/c.rs",
                  "qualification": "source_verified"},
             ]}
    rebind_edges(graph)
    return graph


def rebind_edges(graph):
    """Independent fixture authoring, not the production validator."""
    for lot in graph["lots"]:
        own = set(lot["writable_files"])
        lot["boundary_edge_ids"], lot["internal_edge_ids"] = [], []
        for edge in graph["edge_registry"]:
            paths = {edge["origin_path"], edge["destination_path"]}
            if not paths & own:
                continue
            other_claim = any(other["id"] != lot["id"] and paths & set(other["writable_files"])
                              for other in graph["lots"])
            key = "internal_edge_ids" if paths <= own and not other_claim else "boundary_edge_ids"
            lot[key].append(edge["id"])


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = fixture()
        self.hashes = {"lots": "a" * 64, "state": "b" * 64, "resolutions": "c" * 64}
        self.state = {"schema_version": 1, "kind": "lint-campaign-state",
                      "lots_sha256": self.hashes["lots"], "active": {}, "completed": {}}
        self.resolutions = {"schema_version": 1, "kind": "lint-reviewed-resolutions", "rows": []}

    def plan(self, cap=5):
        return tool.plan(self.manifest, self.state, self.resolutions, self.hashes, cap)

    def prepare_files(self):
        self.lots_path, self.state_path = self.root / "lots.json", self.root / "state.json"
        self.resolutions_path = self.root / "resolutions.json"
        self.output, self.csv = self.root / "wave.json", self.root / "accepted.csv"
        self.lots_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.state["lots_sha256"] = hashlib.sha256(self.lots_path.read_bytes()).hexdigest()
        self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        self.resolutions_path.write_text(json.dumps(self.resolutions), encoding="utf-8")

    def args(self):
        return ["--lots", str(self.lots_path), "--state", str(self.state_path),
                "--resolutions", str(self.resolutions_path), "--output", str(self.output), "--csv", str(self.csv)]

    def cli(self, extra=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return tool.main(self.args() + (extra or []))

    def test_all_qualifications_context_and_deterministic_degree_order(self):
        wave, _ = self.plan()
        self.assertEqual(wave["conflict_pair_count"], 2)
        self.assertEqual(wave["selected_lots"], ["lot-d", "lot-e", "lot-a", "lot-c"])
        self.assertEqual(wave["conflicts"][0]["edge_ids"], ["backend-ab"])
        self.assertEqual(wave["excluded"]["lot-b"]["reason"], "conflicts_with_selected")
        self.assertEqual(wave["manual_queue_count"], 1)
        self.assertFalse(wave["leases_reserved"])
        self.assertEqual(wave["execution"], "not_available_in_offline_helper")
        self.assertEqual(wave["coverage_review_gates"]["inherited"]["graph_status"], "partial")
        self.assertEqual(self.plan()[0], wave)
        self.assertEqual(self.plan(cap=1)[0]["selected_lots"], ["lot-d"])
        self.assertEqual(self.plan(cap=1)[0]["excluded"]["lot-e"]["reason"], "planning_cap")

    def test_active_neighbors_and_completed_release(self):
        self.state["active"] = {"lot-a": {"lease_id": "lease-a", "owner_ref": "synthetic-owner"}}
        wave, _ = self.plan()
        self.assertEqual(wave["excluded"]["lot-a"]["reason"], "active")
        self.assertEqual(wave["excluded"]["lot-b"]["lot_ids"], ["lot-a"])
        self.assertNotIn("lot-b", wave["selected_lots"])
        self.state["active"] = {}
        self.state["completed"] = {"lot-b": {"lead_acceptance_ref": "synthetic-lead-review",
                                            "integration_ref": "synthetic-integrated-change"}}
        wave, _ = self.plan()
        self.assertEqual(wave["selected_lots"], ["lot-a", "lot-c", "lot-d", "lot-e"])
        self.assertEqual(wave["excluded"]["lot-b"]["reason"], "completed")

    def test_stale_unknown_disjoint_and_author_only_completion_fail(self):
        original = copy.deepcopy(self.state)
        cases = [
            {"lots_sha256": "d" * 64},
            {"active": {"missing": {"lease_id": "x", "owner_ref": "owner"}}},
            {"completed": {"lot-a": {"author_finished": "not acceptance"}}},
            {"active": {"lot-a": {"lease_id": "x", "owner_ref": "owner"}},
             "completed": {"lot-a": {"lead_acceptance_ref": "lead", "integration_ref": "merged"}}},
            {"active": {"lot-a": {"lease_id": "same", "owner_ref": "owner"},
                        "lot-c": {"lease_id": "same", "owner_ref": "owner"}}},
        ]
        for changes in cases:
            self.state = {**original, **changes}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.plan()

    def test_empty_wave_explains_all_completed_or_active(self):
        self.state["completed"] = {lot["id"]: {"lead_acceptance_ref": "lead", "integration_ref": "merged"}
                                   for lot in self.manifest["lots"]}
        wave, _ = self.plan()
        self.assertEqual(wave["selected_lots"], [])
        self.assertIn("completed", wave["empty_wave_reason"])
        self.assertEqual(len(wave["excluded"]), 5)

    def test_overlap_conflicts_but_shared_readonly_context_does_not(self):
        self.manifest["lots"][3]["writable_files"].append("src/a.rs")
        rebind_edges(self.manifest)
        wave, _ = self.plan()
        pair = next(p for p in wave["conflicts"] if p["lots"] == ["lot-a", "lot-d"])
        self.assertEqual(pair["overlap_files"], ["src/a.rs"])
        selected = set(wave["selected_lots"])
        self.assertFalse({"lot-a", "lot-d"} <= selected)
        self.assertFalse(any(p["lots"] == ["lot-d", "lot-e"] for p in wave["conflicts"]))

    def test_missing_or_forged_boundary_ids_and_endpoints_fail_closed(self):
        original = copy.deepcopy(self.manifest)
        mutations = [
            lambda g: g["lots"][0]["boundary_edge_ids"].remove("backend-ab"),
            lambda g: g["lots"][0]["boundary_edge_ids"].append("unknown"),
            lambda g: g["lots"][0]["internal_edge_ids"].append("backend-ab"),
            lambda g: g["edge_registry"][0].update(destination_path="not-registered.rs"),
            lambda g: g["edge_registry"].append(copy.deepcopy(g["edge_registry"][0])),
        ]
        for change in mutations:
            self.manifest = copy.deepcopy(original)
            change(self.manifest)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.plan()

    def test_manifest_ids_workload_and_ownership_accounting_fail_closed(self):
        original = copy.deepcopy(self.manifest)
        mutations = [
            lambda g: g["lots"].append(copy.deepcopy(g["lots"][0])),
            lambda g: g["lots"][0].update(workload=True),
            lambda g: g["accounting"].update(assigned_units=99),
            lambda g: g["units"][0].update(lot_id=None, owner_path=None),
            lambda g: g["files"][0].update(write_owner="unknown"),
            lambda g: g["files"][0].update(source_status="unresolved_path"),
            lambda g: g["lots"][0]["readonly_context"].append("unknown.rs"),
            lambda g: g["unresolved_queue"].append({"unit_id": "manual"}),
        ]
        for change in mutations:
            self.manifest = copy.deepcopy(original)
            change(self.manifest)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.plan()

    def test_csv_exact_status_filter_order_and_multiline_verbatim_roundtrip(self):
        def row(identifier, status):
            return {"id": identifier, "status": status, "decision": 'Use "quoted", café',
                    "conditions": "first\nsecond\rthird\r\nfourth", "exceptions": 'except "x",\nnext',
                    "source_ref": "synthetic:source", "approval_ref": "synthetic:approval"}
        self.resolutions["rows"] = [row("z", "Accepted"), row("a", "Accepted"),
                                     *(row(status, status) for status in ("Proposed", "Superseded", "Rejected"))]
        wave, content = self.plan()
        parsed = list(csv.DictReader(io.StringIO(content, newline="")))
        self.assertEqual([r["id"] for r in parsed], ["a", "z"])
        self.assertEqual(parsed[0], row("a", "Accepted"))
        self.assertEqual(wave["csv_sha256"], hashlib.sha256(content.encode("utf-8")).hexdigest())
        self.assertEqual(wave["resolution_summary"]["excluded_status_counts"],
                         {"Proposed": 1, "Superseded": 1, "Rejected": 1})
        self.assertEqual(list(csv.reader(io.StringIO(content, newline="")))[0], list(tool.CSV_FIELDS))

    def test_bad_resolution_ids_status_refs_and_types_fail(self):
        valid = {"id": "x", "status": "Accepted", "decision": "synthetic", "conditions": "",
                 "exceptions": "", "source_ref": "source", "approval_ref": "approval"}
        for changes in ({"status": "accepted"}, {"approval_ref": " "}, {"source_ref": ""},
                        {"conditions": []}, {"id": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tool.resolution_csv({**self.resolutions, "rows": [{**valid, **changes}]})
        with self.assertRaises(ValueError):
            tool.resolution_csv({**self.resolutions, "rows": [valid, valid]})

    def test_wave_id_bound_to_hashes_csv_options_ids_not_paths_or_time(self):
        first = self.plan()[0]
        second, _ = tool.plan(self.manifest, self.state, self.resolutions, self.hashes, 5, "elsewhere.csv")
        self.assertEqual(first["wave_id"], second["wave_id"])
        changed = {**self.hashes, "resolutions": "e" * 64}
        self.assertNotEqual(first["wave_id"], tool.plan(self.manifest, self.state, self.resolutions, changed, 5)[0]["wave_id"])
        self.assertNotEqual(first["wave_id"], self.plan(cap=1)[0]["wave_id"])
        self.assertNotIn("timestamp", first)
        self.resolutions["rows"] = [{"id": "new", "status": "Accepted", "decision": "synthetic",
                                     "conditions": "", "exceptions": "", "source_ref": "s", "approval_ref": "a"}]
        self.assertNotEqual(first["wave_id"], self.plan()[0]["wave_id"])
        self.assertEqual(first["action_requests"][0]["common_snapshot"]["sha256"], first["csv_sha256"])

    def test_capability_simulations_missing_context_launch_and_present_native_tool(self):
        record = {"context_mode": {"available": True, "tool": "simulated-context-execution",
                                   "evidence_ref": "synthetic-run-evidence"},
                  "agent_launch": {"available": False, "tool": None, "evidence_ref": "synthetic-unavailable"},
                  "permissions_ref": "synthetic-permissions", "project_rules_ref": "synthetic-project"}
        self.assertEqual(tool.capability_status(record)["status"], "requests_only")
        record["agent_launch"].update(available=True, tool="simulated-native-tool")
        self.assertEqual(tool.capability_status(record)["status"], "approval_and_lease_required")
        record["context_mode"].update(available=False, tool=None)
        self.assertEqual(tool.capability_status(record)["status"], "BLOCKED")
        record["permissions_ref"] = ""
        with self.assertRaises(ValueError):
            tool.capability_status(record)

    def test_skill_frontmatter_relative_reference_and_no_native_runtime_claim(self):
        path = ROOT / ".agents/skills/lint-workgraph-campaign/SKILL.md"
        content = path.read_text(encoding="utf-8")
        header = content.split("---", 2)[1].strip().splitlines()
        self.assertEqual({line.split(":", 1)[0] for line in header}, {"name", "description"})
        self.assertIn("name: lint-workgraph-campaign", header)
        self.assertLessEqual(len(content.splitlines()), 120)
        self.assertTrue((path.parent / "references/host-adapter.md").is_file())
        self.assertIn("references/host-adapter.md", content)
        for phrase in ("BLOCKED", "Context Mode", "exclusive", "read-only", "target"):
            self.assertIn(phrase, content)
        adapter = (path.parent / "references/host-adapter.md").read_text(encoding="utf-8")
        for link in ("developers.openai.com/codex/build-skills.md", "pi-mono/main", "opencode.ai/docs/skills"):
            self.assertIn(link, adapter)

    def test_cli_default_plan_only_determinism_and_foreign_outputs(self):
        self.prepare_files()
        self.assertEqual(self.cli(), 0)
        wave = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(wave["options"]["max_workers"], 1)
        self.assertEqual(wave["selected_lots"], ["lot-d"])
        first = self.output.read_bytes()
        self.assertEqual(self.cli(), 0)
        self.assertEqual(first, self.output.read_bytes())
        self.csv.write_text("unrelated content", encoding="utf-8")
        self.assertEqual(self.cli(), 2)
        self.output.write_text('{"kind":"foreign"}', encoding="utf-8")
        self.assertEqual(self.cli(), 2)

    def test_input_output_csv_hardlink_and_script_aliases_fail(self):
        self.prepare_files()
        self.assertEqual(self.cli(["--output", str(self.lots_path)]), 2)
        self.assertEqual(self.cli(["--output", str(Path(tool.__file__))]), 2)
        self.assertEqual(self.cli(["--csv", str(self.output)]), 2)
        os.link(self.lots_path, self.output)
        self.assertEqual(self.cli(), 2)
        self.output.unlink()
        self.assertEqual(self.cli(), 0)
        self.csv.unlink()
        os.link(self.output, self.csv)
        self.assertEqual(self.cli(), 2)

    def test_same_buffer_bound_strict_json_and_input_drift(self):
        self.prepare_files()
        with mock.patch.object(tool, "MAX_INPUT_BYTES", 8):
            self.assertEqual(self.cli(), 2)
        real_fsync = tool.guards.os.fsync
        def drift(fd):
            real_fsync(fd)
            self.resolutions_path.write_text(json.dumps({**self.resolutions, "changed": True}), encoding="utf-8")
        with mock.patch.object(tool.guards.os, "fsync", side_effect=drift):
            self.assertEqual(self.cli(), 2)
        self.assertFalse(self.output.exists())
        self.resolutions_path.write_text('{"kind":"x","kind":"y"}', encoding="utf-8")
        self.assertEqual(self.cli(), 2)

    def test_atomic_failure_preserves_pair_and_removes_staged_files(self):
        self.prepare_files()
        self.assertEqual(self.cli(), 0)
        previous = self.output.read_bytes(), self.csv.read_bytes()
        with mock.patch.object(tool.guards.os, "replace", side_effect=OSError("synthetic replacement failure")):
            self.assertEqual(self.cli(), 2)
        self.assertEqual(previous, (self.output.read_bytes(), self.csv.read_bytes()))
        self.assertFalse(list(self.root.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
