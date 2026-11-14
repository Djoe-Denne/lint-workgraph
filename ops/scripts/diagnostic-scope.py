#!/usr/bin/env python3
"""Route known diagnostic rules: explicitly local exceptions, transverse otherwise."""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


POLICY_VERSION = 1
FAMILIES = {
    "documentation": """
        missing_errors_doc missing_panics_doc doc_markdown doc_lazy_continuation
        too_long_first_doc_paragraph
    """.split(),
    "mechanical": """
        manual_assert_eq assert_is_empty unreadable_literal wildcard_imports
        ignored_unit_patterns use_self manual_let_else unnecessary_option_map_or_else
        unnecessary_result_map_or_else option_if_let_else needless_borrow
        format_push_string items_after_statements single_match_else enum_glob_use
        redundant_closure_for_method_calls useless_let_if_seq unicode_not_nfc
        literal_string_with_formatting_args match_wildcard_for_single_variants
        semicolon_if_nothing_returned used_underscore_binding default_trait_access
        unnested_or_patterns needless_continue manual_string_new redundant_closure
        format_in_format_args if_not_else format_collect items_after_test_module
        manual_repeat_n clone_on_copy manual_contains single_char_add_str
        uninlined_format_args needless_raw_string_hashes
    """.split(),
    "structure": """
        too_many_lines too_many_arguments inconsistent_struct_constructor
        struct_excessive_bools similar_names
    """.split(),
    "runtime_ownership": """
        significant_drop_tightening significant_drop_in_scrutinee cast_possible_wrap
        cast_sign_loss assigning_clones large_futures large_enum_variant expect_used
        missing_const_for_thread_local missing_fields_in_debug needless_collect
        match_wild_err_arm iter_with_drain field_reassign_with_default redundant_clone
        or_fun_call suspicious_operation_groupings
    """.split(),
    "api_types_annotations": """
        needless_pass_by_value struct_field_names missing_const_for_fn
        must_use_candidate derive_partial_eq_without_eq elidable_lifetime_names
        trivially_copy_pass_by_ref unused_async_trait_impl option_option
        result_large_err redundant_pub_crate
    """.split(),
}
KNOWN_RULES = {
    "clippy::" + rule: family
    for family, rules in FAMILIES.items() for rule in rules
}
KNOWN_RULES.update({
    "rust:S2208": "mechanical", "rust:S1612": "mechanical",
    "rust:S9045": "mechanical", "rust:S3776": "structure",
    "rust:S107": "structure", "rust:S7493": "runtime_ownership",
    "rust:S2737": "runtime_ownership", "rust:S9334": "qualification",
})
# This is a routing policy, not automatic fix approval or an independence proof.
# Imports, naming, item movement and uncertain rewrites stay transverse even
# when the earlier triage called their family "mechanical".
LOCAL_MECHANICAL = set("""
    manual_assert_eq assert_is_empty unreadable_literal ignored_unit_patterns
    manual_let_else unnecessary_option_map_or_else unnecessary_result_map_or_else
    option_if_let_else format_push_string single_match_else
    redundant_closure_for_method_calls useless_let_if_seq
    match_wildcard_for_single_variants semicolon_if_nothing_returned
    unnested_or_patterns needless_continue manual_string_new redundant_closure
    format_in_format_args if_not_else format_collect manual_repeat_n clone_on_copy
    manual_contains single_char_add_str uninlined_format_args needless_raw_string_hashes
""".split())
LOCAL_MECHANICAL_RULES = {"clippy::" + name for name in LOCAL_MECHANICAL}


def classify(rule):
    if not isinstance(rule, str) or not rule.strip():
        raise ValueError("rule must be a nonempty string")
    if rule.startswith("external_clippy:"):
        rule = "clippy::" + rule[len("external_clippy:"):]
    family = KNOWN_RULES.get(rule, "unknown")
    if family == "documentation":
        scope, reason = "local", "documentation_only"
    elif rule in LOCAL_MECHANICAL_RULES:
        scope, reason = "local", "local_mechanical_rewrite"
    else:
        scope, reason = "transverse", "conservative_default"
    return {
        "rule": rule, "family": family, "scope": scope,
        "reason": reason, "known_rule": rule in KNOWN_RULES,
        "needs_dependency_analysis": scope == "transverse",
    }


def counts(values):
    result = Counter(values)
    return {scope: result[scope] for scope in ("local", "transverse")}


def route_inventory(data):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("expected overlap inventory schema_version 1")
    rows, by_id, issue_keys, per_rule = [], {}, set(), {}
    for source in ("clippy", "sonar"):
        records = data.get(source)
        if not isinstance(records, list):
            raise ValueError(f"{source} must be an array")
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
                raise ValueError("record requires a nonempty id")
            key = f"{source}:{record['id']}"
            if key in by_id:
                raise ValueError(f"duplicate diagnostic {key}")
            routed = dict(classify(record.get("rule")), diagnostic_key=key, source=source)
            if source == "sonar":
                keys = record.get("issue_keys")
                if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k for k in keys):
                    raise ValueError("Sonar site requires nonempty issue_keys")
                if len(set(keys)) != len(keys) or issue_keys.intersection(keys):
                    raise ValueError("duplicate Sonar issue key")
                issue_keys.update(keys)
                routed["sonar_issue_key_count"] = len(keys)
            rows.append(routed)
            by_id[key] = routed
            per_rule[routed["rule"]] = classify(routed["rule"])
    matches = data.get("matches")
    if not isinstance(matches, list):
        raise ValueError("matches must be an array")
    matched_c, matched_s = set(), set()
    for match in matches:
        if not isinstance(match, dict):
            raise ValueError("match must be an object")
        c, s = "clippy:" + str(match.get("clippy_id")), "sonar:" + str(match.get("sonar_id"))
        if c not in by_id or s not in by_id or c in matched_c or s in matched_s:
            raise ValueError("match endpoints must exist and be one-to-one")
        if by_id[c]["rule"] != by_id[s]["rule"]:
            raise ValueError("exact alias rules must agree")
        matched_c.add(c)
        matched_s.add(s)
    expected = {
        "clippy_unique": sum(r["source"] == "clippy" for r in rows),
        "sonar_unique_sites": sum(r["source"] == "sonar" for r in rows),
        "sonar_raw_keys": len(issue_keys),
        "exact_intersection": len(matches),
        "strict_union": len(rows) - len(matches),
    }
    declared = data.get("counts")
    if not isinstance(declared, dict) or any(
            type(declared.get(k)) is not int or declared[k] != v for k, v in expected.items()):
        raise ValueError("inventory counts disagree with records and exact aliases")
    summary = {
        "clippy": counts(r["scope"] for r in rows if r["source"] == "clippy"),
        "sonar_sites": counts(r["scope"] for r in rows if r["source"] == "sonar"),
        "sonar_issue_keys": counts(
            r["scope"] for r in rows if r["source"] == "sonar"
            for _ in range(r["sonar_issue_key_count"])),
        "strict_union": counts(r["scope"] for r in rows if r["diagnostic_key"] not in matched_s),
        "retained_records": len(rows),
        "unknown_rule_records": sum(not r["known_rule"] for r in rows),
    }
    return {
        "schema_version": 1, "kind": "diagnostic-scope-routing",
        "policy_version": POLICY_VERSION, "default_scope": "transverse",
        "summary": summary, "diagnostics": sorted(rows, key=lambda r: r["diagnostic_key"]),
        "rules": [per_rule[k] for k in sorted(per_rule)],
        "limitations": [
            "Rule-based routing only; no source, signature or dependency analysis.",
            "Local means skip dependency lookup for the intended local correction.",
            "Transverse means investigate, not proven cross-file impact or must-coedit.",
            "No fix approval, hard union, independent worker certification or dispatch.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", help="Existing Clippy/Sonar overlap inventory")
    mode.add_argument("--catalog", action="store_true", help="List all known rule routes")
    parser.add_argument("--output", help="JSON output; default stdout")
    args = parser.parse_args(argv)
    temporary = None
    try:
        output = Path(args.output).resolve() if args.output else None
        if args.inventory:
            source = Path(args.inventory).resolve()
            if output and (output == source or (output.exists() and os.path.samefile(output, source))):
                raise ValueError("output must not overwrite the inventory")
            raw = source.read_bytes()
            result = route_inventory(json.loads(raw.decode("utf-8-sig")))
            result["inventory_sha256"] = hashlib.sha256(raw).hexdigest()
        else:
            result = {"policy_version": POLICY_VERSION, "default_scope": "transverse",
                      "rules": [classify(k) for k in sorted(KNOWN_RULES)]}
        rendered = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if output:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                             prefix=output.name + ".", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                stream.write(rendered)
            os.replace(temporary, output)
            temporary = None
        else:
            sys.stdout.write(rendered)
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"diagnostic-scope: {exc}", file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            os.unlink(temporary)


if __name__ == "__main__":
    sys.exit(main())
