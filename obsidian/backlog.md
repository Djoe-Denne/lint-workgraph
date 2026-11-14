---
title: Remaining work
created: 2026-11-14
status: open
---

# Remaining work

## Backend direction after the POC

- [ ] For a Rust-focused successor, evaluate replacing both `rust-code-mcp` and
      Serena with a rust-analyzer-based backend.
- [ ] Alternatively, investigate a Sonar-based analysis library for broader
      language coverage; select a concrete library only after checking its API,
      licensing, supported languages and dependency/reference information.
- [ ] Compare either candidate against the current evidence, coordinate,
      identity and graph requirements before choosing or implementing a backend.

These are future directions requested for this quick POC, not existing features
or an assertion that either backend is a drop-in equivalent.

## First priority: real cold-start usability

- [ ] Define a minimal supported acquisition interface for Clippy and Sonar.
- [x] Replace manual final-stage seeds with automatic native discovery and
      explicit source/query budgets over the full inventory.
- [ ] Package and test independent source-binding preparation; current hashes
      alone must not manufacture historical equivalence.
- [ ] Provide a durable launcher for the supported real-project pipeline.
- [ ] Prove the flow from a fresh output directory without private artifacts.

## Broader useful graph coverage

- [x] Add a generic native-identity path independent of the legacy named origin
      profile, retaining unsupported cases and backend freshness warnings.
- [ ] Add explicit supported responses/versions for MCP adapters.
- [ ] Improve diagnostic-to-symbol coverage without erasing unsupported cases.
- [ ] Establish Sonar coordinate conventions through reproducible evidence.
- [ ] Expand observed neighborhoods while retaining coverage limits.

## Work allocation

- [x] Implement measured lot optimization using strict-unit workload proxies and
      verified distinct file-pair affinity; compare with the LPT baseline.
- [x] Keep exclusive file ownership separate from soft candidate dependency
      coupling and shared read-only context.
- [ ] Define scheduling/resource metadata without claiming dependency arrows are
      an execution DAG.
- [ ] Keep correction/dispatch outside the planner unless separately authorized.

## Project lifecycle

- [ ] Choose a software license explicitly.
- [ ] Decide when to retire provisional source-project copies after migration.
- [ ] Verify additional platforms before claiming cross-platform parity.

Extraction/publication validations belong in [[history]], not unchecked promises
of future functionality. See [[reproduction-gap]] and [[limitations]].
