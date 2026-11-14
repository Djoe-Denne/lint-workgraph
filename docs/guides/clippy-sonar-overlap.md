# Strict Clippy/Sonar overlap

Supply saved Cargo JSONL for every relevant lane and a complete saved Sonar issue
response or array of pages. Each Cargo file must include successful
`build-finished` accounting. Sonar paging totals and issue-key consistency are
validated. This script invokes neither Cargo nor Sonar.

```powershell
python -B ops/scripts/clippy-sonar-overlap.py --clippy <lane.jsonl> --sonar <pages.json> --output <overlap.json>
```

Repeat `--clippy` for additional lanes. Output is deterministic inventory schema
version 1 with both diagnostic sets, raw-key/source accounting, exact aliases,
ambiguous matches, unmerged hints and strict-union arithmetic.

Exact aliases require unique endpoints, matching rule, full physical span and
message. Only `external_clippy:` is mapped to `clippy::`. Different ranges,
messages, case or ambiguous multi-primary situations remain distinct. Near
matches are hints, not silently merged defects. The strict union is an identity
count, not a semantic defect count or safety measure.

Only separators are normalized; roots/revisions/coordinate units are not
guessed. Historical input equivalence must be supplied separately for exact
source localization. See [IO contract](../contracts/io.md) and
[MCP evidence](mcp-code-evidence.md).

```powershell
python -B -m unittest discover -s ops/tests -p test_clippy_sonar_overlap.py
```
