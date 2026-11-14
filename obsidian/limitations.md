---
title: Current limitations
created: 2026-11-14
status: known-limitations
---

# Current limitations

## Cold-start reconstruction is incomplete

There is no complete durable sequence that starts from an arbitrary untouched
Rust project, acquires Clippy/Sonar data, prepares every collection/binding input,
and emits the graph. See [[reproduction-gap]].

The final dependency stage is now runnable over the complete supplied inventory
with automatic native discovery. It no longer requires a manual seed/source
plan. Upstream acquisition and independent historical equivalence remain separate.

## Coverage and identity

- Pagination completeness describes a particular query, not all references.
- Private items, macros, cfg/features, traits and tests can be missing or only
  partially represented by an index.
- The source-range method supports a bounded lexical subset, not all Rust syntax.
- Unsupported rewriting/cfg/generated ancestry remains unknown.
- Sonar coordinate conventions require explicit verification for exact mapping.
- A native span mismatch is retained, not repaired by guessed offsets.

## Source-specific live origin profile

The legacy `produce --observations` live file-origin profile is tied to the compatibility target
`apparatus_contracts::runtime::validate_runtime_uid` and its expected default
crate/module layout. It is not a general Rust name resolver.
Explicit workspace portability does not remove this profile limitation.

The new `lint-workgraph.py` command is not bound to that legacy profile. It uses
the native graph's identities and locations, with separate current-source and
coverage checks. Unsupported cases remain visible rather than guessed.

## Partitioning

Tentative ownership groups are not certified independent correction lots.
Candidate dependencies do not force unions; absent observations do not establish
independence. There is no fixed worker count, globally optimal partition,
automatic correction strategy or agent dispatch.

## Operational and legal scope

Live collection requires already running compatible local MCP servers.
Server installation/startup/configuration is not automated.
The implementation was verified on Windows; unsupported path or response
formats must fail explicitly rather than weaken root checks.

No project software license has been selected. Public GitHub visibility is not
a permissive license grant.

See [[backlog]] and [[provenance]].
