#!/usr/bin/env python3
"""Build invented test artifacts, then exercise the real offline planner CLI."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def demonstrate(directory):
    # This intentionally reuses the curated TEST builder, not a supported API.
    spec = importlib.util.spec_from_file_location(
        "offline_example_fixture", ROOT / "ops/tests/test_clippy_constraint_plan.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    fixture = fixtures.Fixture(directory)
    fixture.observation_fixture(["a.rs", "b.rs", "consumer.rs"], omitted_consumer=True)
    unknown = next(m for m in fixture.evidence["mappings"] if m["diagnostic_key"] == "clippy:C000004")
    unknown.update(status="unknown", symbols=[], evidence_refs=[], reasons=["Synthetic unavailable symbol"])
    fixture.save()
    command = [
        sys.executable, "-B", str(ROOT / "ops/scripts/clippy-constraint-plan.py"),
        "--inventory", str(fixture.inventory_path), "--snapshot", str(fixture.snapshot_path),
        "--evidence", str(fixture.evidence_path), "--observations", str(directory / "observations.json"),
        "--output", str(directory / "plan.json"), "--report", str(directory / "plan.md"),
    ]
    subprocess.run(command, check=True)
    first = (directory / "plan.json").read_bytes()
    subprocess.run(command, check=True)
    if first != (directory / "plan.json").read_bytes():
        raise AssertionError("Identical bound inputs must produce identical plan bytes")
    plan = json.loads(first)
    coverage = plan["work_graph"]["coverage"]
    assert plan["confirmed_multi_file_components"] == 0
    assert coverage["hard_edges"] == 0 and coverage["candidate_edges"] == 3
    assert plan["mapping_status_counts"]["unknown"] >= 1
    assert plan["accounting"]["input_diagnostic_records"] == plan["accounting"]["retained_diagnostic_records"]
    assert plan["global_independence"] == "unproven"
    print(json.dumps({
        "synthetic_only": True, "retained_records": plan["accounting"]["retained_diagnostic_records"],
        "nodes": coverage["files"], "candidate_edges": coverage["candidate_edges"],
        "hard_edges": coverage["hard_edges"], "unknown_mappings": plan["mapping_status_counts"]["unknown"],
        "global_independence": plan["global_independence"], "repeat_plan_bytes_identical": True,
    }, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="Keep outputs in a NEW directory; default is temporary")
    args = parser.parse_args()
    if args.directory:
        directory = args.directory.resolve()
        directory.mkdir(parents=False, exist_ok=False)
        demonstrate(directory)
    else:
        with tempfile.TemporaryDirectory(prefix="lint-workgraph-example-") as directory:
            demonstrate(Path(directory).resolve())


if __name__ == "__main__":
    main()
