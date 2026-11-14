# GitHub lint issue inventory

`ops/scripts/github-lint-inventory.py` extracts explicitly advertised lint rules
and paths from issue titles, bodies and labels. It excludes pull requests and
closed issues, deduplicates issue numbers and retains observation provenance.

Offline, using a saved REST array or `gh --paginate --slurp` array of pages:

```powershell
python -B ops/scripts/github-lint-inventory.py --input <saved-issues.json> --output <new-inventory.json>
```

Optional live mode uses `--repo <owner/repository>` instead of `--input`. It
requires the caller's already authenticated `gh` and makes explicit GET
requests only. Offline mode cannot establish page completeness; live pagination
does not prove an immutable repository snapshot.

Output includes source digest, counts, per-issue rules/paths/areas, evidence and
completeness limitations. A rule/path mention is not a physical diagnostic
mapping or impact proof. This issue inventory is **not** the Clippy/Sonar overlap
schema accepted by the constraint planner.

Python 3.11+ suffices offline. Run its offline tests with:

```powershell
python -B -m unittest discover -s ops/tests -p test_github_lint_inventory.py
```

Review saved issue text for secrets before sharing. Use distinct input/output
paths: this small inventory writer is not the planner's guarded artifact
publisher. See [IO contract](../contracts/io.md).
