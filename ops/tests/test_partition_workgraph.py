"""Offline partition fixtures; no native backend or real source inventory."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_lint_workgraph import Fixture


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("partition_tests_tool", ROOT / "ops/scripts/partition-workgraph.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class PartitionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        fixture = Fixture(self.base)
        fixture.create()
        self.graph = fixture.graph()
        self.input = self.base / "snapshot.json"
        self.output = self.base / "lots.json"
        self.report = self.base / "lots.md"

    def persist(self):
        self.input.write_text(json.dumps(self.graph), encoding="utf-8")

    def args(self):
        return ["--graph", str(self.input), "--output", str(self.output), "--report", str(self.report)]

    def run_cli(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return tool.main(self.args())

    def test_strict_provenance_and_context_no_fake_jobs(self):
        prepared = tool.prepare(self.graph)
        self.assertEqual(sum(prepared["weights"].values()), 4)
        self.assertEqual(len(prepared["units"]), 4)
        self.assertEqual(prepared["units"]["clippy:C1"]["diagnostic_keys"], ["clippy:C1", "sonar:S1"])
        self.assertNotIn("src/use.rs", prepared["weights"])
        partition = tool.optimize(prepared["weights"], prepared["adjacency"], parts=2)
        result = tool.manifest(self.graph, prepared, partition, "a" * 64, parts=2)
        self.assertEqual(result["accounting"]["original_records"], 5)
        self.assertEqual(result["accounting"]["raw_sonar_keys"], 3)
        context = next(f for f in result["files"] if f["path"] == "src/use.rs")
        self.assertIsNone(context["write_owner"])
        self.assertTrue(any("src/use.rs" in lot["readonly_context"] for lot in result["lots"]))
        self.assertTrue(all(lot["review_tasks"] for lot in result["lots"]))
        self.assertEqual(len(result["edge_registry"]), 1)

    def test_unresolved_dot_path_is_not_normalized(self):
        for row in self.graph["diagnostics"]:
            if row["key"] == "sonar:S2":
                row["files"] = ["src/../src/unlocated.rs"]
        for node in self.graph["work_graph"]["nodes"]:
            if node["path"] == "src/unlocated.rs":
                node.update(path="src/../src/unlocated.rs", source_status="unresolved_path")
        p = tool.prepare(self.graph)
        self.assertIsNone(p["units"]["sonar:S2"]["owner_path"])
        self.assertNotIn("src/../src/unlocated.rs", p["weights"])

    def test_conflicting_exact_alias_file_candidates_queue_both_provenances(self):
        next(r for r in self.graph["diagnostics"] if r["key"] == "sonar:S1")["files"] = ["src/local.rs"]
        for node in self.graph["work_graph"]["nodes"]:
            if node["path"] == "src/lib.rs":
                node["diagnostic_keys"].remove("sonar:S1")
            if node["path"] == "src/local.rs":
                node["diagnostic_keys"].append("sonar:S1")
        unit = tool.prepare(self.graph)["units"]["clippy:C1"]
        self.assertIsNone(unit["owner_path"])
        self.assertEqual(len(unit["diagnostic_keys"]), 2)

    def test_missing_file_and_multifile_units_queue(self):
        row = next(r for r in self.graph["diagnostics"] if r["key"] == "sonar:S2")
        row["files"] = []
        node = next(n for n in self.graph["work_graph"]["nodes"] if n["path"] == "src/unlocated.rs")
        node.update(path="unlocated:sonar:S2", source_status="unresolved_path")
        self.assertIsNone(tool.prepare(self.graph)["units"]["sonar:S2"]["owner_path"])
        row["files"] = ["src/lib.rs", "src/local.rs"]
        self.graph["work_graph"]["nodes"].remove(node)
        for n in self.graph["work_graph"]["nodes"]:
            if n["path"] in row["files"]:
                n["diagnostic_keys"].append("sonar:S2")
        self.assertIsNone(tool.prepare(self.graph)["units"]["sonar:S2"]["owner_path"])

    def test_duplicate_reverse_self_and_unverified_edges_do_not_inflate_affinity(self):
        edges = self.graph["work_graph"]["edges"]
        original = edges[0]
        original.update(origin_path="src/lib.rs", destination_path="src/local.rs")
        for identifier, a, b, q in (
            ("reverse", "src/local.rs", "src/lib.rs", "source_verified"),
            ("duplicate", "src/lib.rs", "src/local.rs", "source_verified"),
            ("self", "src/lib.rs", "src/lib.rs", "source_verified"),
            ("unverified", "src/local.rs", "src/unlocated.rs", "backend_observed"),
        ):
            edges.append({**original, "id": identifier, "origin_path": a, "destination_path": b, "qualification": q})
        prepared = tool.prepare(self.graph)
        self.assertEqual(prepared["affinity"]["affinity_pairs"], 1)
        self.assertEqual(prepared["affinity"]["duplicate_or_reverse_observations"], 2)
        self.assertEqual(len(prepared["edges"]), 5)

    def test_malformed_accounting_aliases_and_missing_records_fail(self):
        original = copy.deepcopy(self.graph)
        mutations = [
            lambda g: g["accounting"].update(strict_union=900),
            lambda g: g["inventory"]["matches"].append(copy.deepcopy(g["inventory"]["matches"][0])),
            lambda g: g["diagnostics"].pop(),
            lambda g: g["diagnostics"][0]["record"].update(message="forged"),
        ]
        for change in mutations:
            graph = copy.deepcopy(original)
            change(graph)
            with self.subTest(change=change), self.assertRaises(ValueError):
                tool.prepare(graph)

    def test_unsupported_hard_constraints_edges_and_approvals_fail(self):
        for name in ("hard_must_coedit", "constraints", "hard_edges", "hard_constraints"):
            graph = copy.deepcopy(self.graph)
            graph["work_graph"][name] = [{"id": "unsupported"}]
            with self.subTest(name=name), self.assertRaises(ValueError):
                tool.prepare(graph)
        self.graph["work_graph"]["edges"][0]["class"] = "hard"
        with self.assertRaises(ValueError):
            tool.prepare(self.graph)
        self.graph["work_graph"]["edges"][0]["class"] = "candidate_dependency"
        self.graph["work_graph"]["proposed_groups"][0]["approved"] = True
        with self.assertRaises(ValueError):
            tool.prepare(self.graph)

    def test_refinement_deterministic_strictly_improving_and_nonempty(self):
        weights = {"a": 10, "b": 10, "c": 10, "d": 10}
        adjacency = {"a": {"b": 1}, "b": {"a": 1}, "c": {"d": 1}, "d": {"c": 1}}
        one = tool.optimize(weights, adjacency, parts=2)
        two = tool.optimize(weights, adjacency, parts=2)
        self.assertEqual(one["owners"], two["owners"])
        self.assertEqual(one["steps"], two["steps"])
        self.assertLess(one["final"]["weighted_cut"], one["baseline"]["weighted_cut"])
        for step in one["steps"]:
            self.assertLess(tuple(step["score_after"]), tuple(step["score_before"]))
        self.assertTrue(all(one["final"]["loads"]))
        self.assertEqual(one["stop_reason"], "local_optimum")
        limited = tool.optimize(weights, adjacency, parts=2, max_improvements=1)
        self.assertEqual(limited["stop_reason"], "max_accepted_improvements")
        self.assertEqual(len(limited["steps"]), 1)

    def test_incremental_move_and_adjacent_swap_delta_matches_full_cut(self):
        import itertools
        weights = {p: 1 for p in "abcd"}
        adjacency = {"a": {"b": 1, "c": 1}, "b": {"a": 1, "d": 1},
                     "c": {"a": 1}, "d": {"b": 1}}
        for assignment in itertools.product(range(2), repeat=4):
            owners = dict(zip(weights, assignment))
            by_lot = tool.neighbor_weights(adjacency, owners)
            before = tool.metrics(weights, adjacency, owners, 2, 4)["weighted_cut"]
            for a, b in itertools.combinations(weights, 2):
                if owners[a] == owners[b]:
                    continue
                changed = dict(owners)
                changed[a], changed[b] = changed[b], changed[a]
                after = tool.metrics(weights, adjacency, changed, 2, 4)["weighted_cut"]
                self.assertEqual(after - before, tool.swap_cut_delta(a, b, owners, by_lot, adjacency))
            for a in weights:
                target = 1 - owners[a]
                changed = {**owners, a: target}
                after = tool.metrics(weights, adjacency, changed, 2, 4)["weighted_cut"]
                self.assertEqual(after - before, tool.move_cut_delta(a, target, owners, by_lot))

    def test_heavy_atom_default_target_and_zero_work(self):
        weights = {"a": 55, "b": 2, "c": 2}
        result = tool.optimize(weights, {p: {} for p in weights})
        self.assertEqual(result["parts"], 2)
        self.assertEqual(result["capacity"], 55)
        self.assertIn(55, result["final"]["loads"])
        self.assertEqual(tool.optimize({}, {})["parts"], 0)
        with self.assertRaises(ValueError):
            tool.optimize(weights, {p: {} for p in weights}, parts=4)
        self.assertEqual(tool.optimize({"a": 1}, {"a": {}}, target=1)["parts"], 1)

    def test_cli_determinism_and_mutually_exclusive_options(self):
        self.persist()
        self.assertEqual(self.run_cli(), 0)
        first = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(self.run_cli(), 0)
        second = json.loads(self.output.read_text(encoding="utf-8"))
        first.pop("timing")
        second.pop("timing")
        self.assertEqual(first, second)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            tool.main(self.args() + ["--parts", "2", "--target-issues", "50"])

    def test_input_output_and_hardlink_aliases_fail(self):
        self.persist()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(self.args() + ["--output", str(self.input)]), 2)
        os.link(self.input, self.output)
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual(json.loads(self.input.read_text())["kind"], "lint-workgraph")

    def test_input_bound_same_buffer_hash_and_publication_drift(self):
        self.persist()
        with mock.patch.object(tool, "MAX_GRAPH_BYTES", 8):
            self.assertEqual(self.run_cli(), 2)
        real_fsync = tool.guards.os.fsync
        def mutate(fd):
            real_fsync(fd)
            self.input.write_text(json.dumps({**self.graph, "replaced": True}), encoding="utf-8")
        with mock.patch.object(tool.guards.os, "fsync", side_effect=mutate):
            self.assertEqual(self.run_cli(), 2)
        self.assertFalse(self.output.exists())

    def test_atomic_failure_preserves_previous_manifest_and_cleans_staged_files(self):
        self.persist()
        self.assertEqual(self.run_cli(), 0)
        old = self.output.read_bytes()
        with mock.patch.object(tool.guards.os, "replace", side_effect=OSError("fixture atomic failure")):
            self.assertEqual(self.run_cli(), 2)
        self.assertEqual(self.output.read_bytes(), old)
        self.assertFalse(list(self.base.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
