"""Offline routing tests: no source exploration, MCP or runtime."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/diagnostic-scope.py"
SPEC = importlib.util.spec_from_file_location("diagnostic_scope", SCRIPT)
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)


def inventory():
    return {
        "schema_version": 1,
        "clippy": [
            {"id": "C1", "rule": "clippy::missing_errors_doc"},
            {"id": "C2", "rule": "clippy::needless_pass_by_value"},
            {"id": "C3", "rule": "clippy::future_unknown"},
        ],
        "sonar": [
            {"id": "S1", "rule": "external_clippy:missing_errors_doc", "issue_keys": ["a", "b"]},
            {"id": "S2", "rule": "rust:S9334", "issue_keys": ["c"]},
        ],
        "matches": [{"clippy_id": "C1", "sonar_id": "S1"}],
        "counts": {"clippy_unique": 3, "sonar_unique_sites": 2, "sonar_raw_keys": 3,
                   "exact_intersection": 1, "strict_union": 4},
    }


class RoutingTests(unittest.TestCase):
    def test_every_known_rule_has_one_binary_route(self):
        for rule in scope.KNOWN_RULES:
            with self.subTest(rule=rule):
                result = scope.classify(rule)
                self.assertTrue(result["known_rule"])
                self.assertIn(result["scope"], ("local", "transverse"))
                self.assertEqual(result["needs_dependency_analysis"], result["scope"] == "transverse")

    def test_all_documentation_rules_are_local(self):
        for rule in scope.FAMILIES["documentation"]:
            self.assertEqual(scope.classify("clippy::" + rule)["scope"], "local")

    def test_mechanical_exceptions_are_explicit(self):
        for name in scope.LOCAL_MECHANICAL:
            self.assertIn("clippy::" + name, scope.KNOWN_RULES)
            self.assertEqual(scope.classify("clippy::" + name)["scope"], "local")

    def test_risky_mechanical_rules_are_not_blanket_local(self):
        for name in ("wildcard_imports", "enum_glob_use", "unicode_not_nfc",
                     "used_underscore_binding", "items_after_statements", "needless_borrow"):
            self.assertEqual(scope.classify("clippy::" + name)["scope"], "transverse")

    def test_api_runtime_structure_and_native_rules_are_transverse(self):
        for family in ("api_types_annotations", "runtime_ownership", "structure"):
            for name in scope.FAMILIES[family]:
                self.assertEqual(scope.classify("clippy::" + name)["scope"], "transverse")
        for rule in scope.KNOWN_RULES:
            if rule.startswith("rust:"):
                self.assertEqual(scope.classify(rule)["scope"], "transverse")

    def test_unknown_and_near_names_do_not_match_local_exceptions(self):
        for rule in ("clippy::future_doc_rule", "rust:S0000", "other::doc_markdown",
                     "clippy::doc_markdown_extra", " clippy::doc_markdown"):
            result = scope.classify(rule)
            self.assertFalse(result["known_rule"])
            self.assertEqual(result["scope"], "transverse")

    def test_normalizes_only_exact_external_clippy_prefix(self):
        self.assertEqual(scope.classify("external_clippy:doc_markdown"), scope.classify("clippy::doc_markdown"))

    def test_accounts_for_sites_raw_keys_and_exact_aliases_separately(self):
        data = inventory()
        before = deepcopy(data)
        result = scope.route_inventory(data)
        self.assertEqual(data, before)
        self.assertEqual(result["summary"]["retained_records"], 5)
        self.assertEqual(result["summary"]["clippy"], {"local": 1, "transverse": 2})
        self.assertEqual(result["summary"]["sonar_sites"], {"local": 1, "transverse": 1})
        self.assertEqual(result["summary"]["sonar_issue_keys"], {"local": 2, "transverse": 1})
        self.assertEqual(result["summary"]["strict_union"], {"local": 1, "transverse": 3})
        self.assertEqual(result["summary"]["unknown_rule_records"], 1)
        self.assertFalse(any("must_coedit" in r for r in result["diagnostics"]))

    def test_empty_inventory_is_valid(self):
        data = {"schema_version": 1, "clippy": [], "sonar": [], "matches": [],
                "counts": {k: 0 for k in inventory()["counts"]}}
        self.assertEqual(scope.route_inventory(data)["summary"]["retained_records"], 0)

    def test_rejects_invalid_records_and_accounting(self):
        cases = [
            lambda x: x.update(schema_version=True),
            lambda x: x.update(clippy={}),
            lambda x: x["clippy"][0].update(rule=None),
            lambda x: x["clippy"][0].update(id=""),
            lambda x: x["clippy"].append(deepcopy(x["clippy"][0])),
            lambda x: x["sonar"][0].update(issue_keys=[]),
            lambda x: x["sonar"][1].update(issue_keys=["a"]),
            lambda x: x["sonar"][0].update(issue_keys=["a", "a"]),
            lambda x: x["matches"].append(deepcopy(x["matches"][0])),
            lambda x: x["matches"][0].update(clippy_id="missing"),
            lambda x: x["matches"][0].update(clippy_id="C2"),
            lambda x: x["counts"].update(strict_union=99),
        ]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                data = inventory()
                mutation(data)
                with self.assertRaises(ValueError):
                    scope.route_inventory(data)

    def test_cli_catalog_and_determinism(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(scope.main(["--catalog"]), 0)
        self.assertEqual(len(json.loads(stream.getvalue())["rules"]), len(scope.KNOWN_RULES))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = root / "in.json", root / "out.json"
            source.write_text(json.dumps(inventory()), encoding="utf-8")
            args = ["--inventory", str(source), "--output", str(output)]
            self.assertEqual(scope.main(args), 0)
            first = output.read_bytes()
            self.assertEqual(scope.main(args), 0)
            self.assertEqual(first, output.read_bytes())
            self.assertEqual(len(json.loads(first)["inventory_sha256"]), 64)

    def test_cli_preserves_inputs_and_previous_outputs_on_failure(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stderr(io.StringIO()):
            root = Path(folder)
            source, output = root / "in.json", root / "out.json"
            source.write_text(json.dumps(inventory()), encoding="utf-8")
            before = source.read_bytes()
            self.assertEqual(scope.main(["--inventory", str(source), "--output", str(source)]), 2)
            self.assertEqual(source.read_bytes(), before)
            alias = root / "hardlink.json"
            os.link(source, alias)
            self.assertEqual(scope.main(["--inventory", str(source), "--output", str(alias)]), 2)
            output.write_text("preserved", encoding="utf-8")
            with patch.object(scope.os, "replace", side_effect=OSError("synthetic failure")):
                self.assertEqual(scope.main(["--inventory", str(source), "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "preserved")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["hardlink.json", "in.json", "out.json"])
            source.write_text("invalid JSON", encoding="utf-8")
            self.assertEqual(scope.main(["--inventory", str(source), "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "preserved")


if __name__ == "__main__":
    unittest.main()
