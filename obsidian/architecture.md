---
title: Pipeline architecture
created: 2026-11-14
status: current-design
---

# Pipeline architecture

The code is an ordinary Python CLI pipeline. It does not require an agent host.

This is a quick POC using `rust-code-mcp` and Serena. The proposed Rust-focused
successor would replace both MCP integrations with a rust-analyzer-based backend.
A Sonar-based analysis library is an unselected alternative for broader language
coverage. Neither direction has been implemented or validated; equivalent graph
evidence and coverage remain evaluation criteria. See [[backlog]].

## Stages

1. **Input inventory.** Read captured Clippy JSONL and complete Sonar pages.
   Keep original issue provenance, strict aliases and uncertain matches.
2. **Source and MCP evidence.** Select an explicit target workspace, capture
   source hashes, and call only curated read-only tools on existing local MCP
   servers. The tool checkout and analyzed Rust checkout are separate.
3. **Physical localization.** Replay source coordinates, function extents and
   captured symbol witnesses. Exact physical location is not semantic-reference
   completeness.
4. **Dependency observations.** Preserve verified file endpoints and unresolved
   observations with query/hash provenance. Do not invent consumer identities.
5. **Work graph.** Retain diagnostic files, observed consumers, qualified hard
   constraints, candidate edges and tentative ownership groups.

## The two edge classes

- `hard_must_coedit`: an independently reviewed and evidence-qualified required
  file set. Only these constraints union file ownership groups.
- `candidate_dependency`: a dependency/impact observation to review when
  partitioning work. It does not force joint edits.

The current file-observation arrow runs from a queried declaration/provider to
an observed consumer: **impact direction**, not `depends_on` or execution order.
Repeated usage sites and distinct file boundaries have different counts.

## Artifact order

Raw captures, source/context and origin proofs precede the snapshot. Normalized
evidence binds that snapshot. Optional observations bind finalized snapshot and
evidence hashes. The planner binds its input artifacts.

Observations must not be hashed back into the snapshot they reference; that
would create a circular hash dependency.

## Trust and safety boundaries

Explicit target-root selection, reported MCP root checks, source/hash replay,
bounded queries, root-confined references and output alias checks protect the
evidence workflow. Unknown language/index coverage remains explicit.
No index rebuild, project activation, corrective edit or worker dispatch is
performed.

See [[limitations]], [[reproduction-gap]] and [[backlog]].
