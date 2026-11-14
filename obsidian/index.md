---
title: lint-workgraph knowledge vault
created: 2026-11-14
status: active
---

# lint-workgraph

> [!summary]
> A quick POC, not a production-ready platform. For a Rust-focused successor,
> replace the current rust-code-mcp and Serena integrations with a
> rust-analyzer-based backend. A Sonar-based analysis library is an alternative
> to investigate for broader language coverage. These are proposed directions,
> not implemented or validated replacements; no Sonar library is selected.

An evidence-backed dependency/work graph for allocating diagnostic work among
workers. This vault records the project's history, design, limitations and next
steps; it is not a source of automatic correction approvals.

## Start here

- [[history]] — what was built and why it was extracted.
- [[architecture]] — pipeline stages, graph semantics and trust boundaries.
- [[limitations]] — what the current implementation cannot establish.
- [[reproduction-gap]] — why a real audit cannot yet be rebuilt from nothing.
- [[backlog]] — the remaining work, in priority order.
- [[provenance]] — public-export and source-provenance rules.
- [[log]] — vault activity.

> [!important]
> The tool produces a representation for ownership and partition review.
> An absent edge is not proof that two correction tasks are independent.

The repository README and contracts describe executable interfaces. This vault
is explanatory knowledge, not a replacement for the code and validated inputs.
