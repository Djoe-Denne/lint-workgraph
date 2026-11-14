---
title: Cold-start reproduction gap
created: 2026-11-14
status: open
---

# Cold-start reproduction gap

> [!warning]
> Replaying saved evidence is not the same as rebuilding a real analysis after
> deleting every generated artifact.

## What exists

The inventory processors, direct MCP collector, source-range verifier and offline
graph planner are reusable code. The public repository also provides tests and a
clearly synthetic offline example.

The final `lint-workgraph.py` command now automatically discovers native graph
scopes and processes the whole supplied overlap inventory. This stage was
verified on the complete real inventory, with no manual seeds or source-specific
origin profile. It does not acquire fresh Clippy/Sonar data.

Given the required inputs, the planner can produce a new graph without OpenCode,
an LLM or live MCP calls. Live collection remains a separate step.

## What the original campaign prepared outside the reusable pipeline

- Successful Clippy production/test JSONL captures and their execution context.
- Complete Sonar API page exports.
- A selected source-file/symbol/target collection plan (legacy path; no longer
  needed by the new final whole-inventory command).
- Independent source-binding/equivalence metadata for historical diagnostics.
- Optional source-reviewed coordinate or correction-policy contexts.

Some original preparation was performed through temporary scripts and local
artifacts. Those private runtime files are not the public implementation and are
not silently copied here.

## Preparation logic to preserve for a future command

The original source-binding preparation retrieved real historical file bytes
with `git show <diagnostic-revision>:<canonical-path>` and compared them with the
current participant bytes. For files in a submodule it used the historical
gitlink and that submodule's object database. Only exact byte equality was
admitted to the binding; a separate hashed comparison proof retained the result.
The binding referenced the inventory hash, current target HEAD, matching file
hashes and independent proof. It did not invent old hashes from current content.

The original, now legacy collection plan selected existing physical diagnostic paths and
explicit named symbol/target query seeds. Lexical names were hints for queries,
not verified mappings or mandatory co-edit links. Additional consumers/context
were prehashed before the final bounded capture.

These are design notes for a tested preparation interface, not claims that
an acquisition or binding command already exists in this repository.

## Required next acceptance test

Use a fresh output directory and no prior generated evidence:

1. Acquire a declared diagnostic snapshot and record its real configuration.
2. Produce and validate the overlap inventory.
3. Prepare the collection plan without private manual setup.
4. Establish independent diagnostic/source binding.
5. Collect bounded source/dependency observations through existing MCP servers.
6. Export the graph and tentative groups.
7. Retain commands, provenance and explicit partial/failure states.

The same graph format should be reproducible. Identical historical counts require
equivalent sources, tool versions, features and external diagnostic data; new
queries are not necessarily byte-identical captures.

A synthetic example proves packaging and deterministic offline mechanics only.
It does not close this real-project acquisition gap.

See [[architecture]], [[limitations]] and [[backlog]].
