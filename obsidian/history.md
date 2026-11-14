---
title: Project history
created: 2026-11-14
status: validated-awaiting-publication
---

# Project history

## The objective

Build a standalone script pipeline that turns diagnostics and source observations
into a dependency/work graph, allowing intelligent allocation of work among
workers without forcing a fixed worker count or arbitrary pairs of files.

## The prototype

The implementation began inside a Rust workspace and was exported from source
revision `c4bba486291edd63dabafd5b5235c2d1ba628fa0`.
It separated:

1. Clippy/Sonar diagnostic inventory and strict overlap accounting.
2. Direct read-only MCP collection, independent of OpenCode or an LLM.
3. Source-bound physical localization, distinct from reference closure.
4. Candidate file observations, distinct from mandatory joint edits.
5. A graph and tentative ownership groups for partition review.

The first localization grammar rejected real mixed Rust files. A bounded
range-local method was added and independently checked against nested items,
cfg attributes, misleading literals and incorrect parent identities.

## Verified prototype results

The historical bounded campaign retained 1,046 source records: 537 Clippy
diagnostics and 509 Sonar sites. With 426 exact cross-source matches, the strict
union was 620; that was not a count of distinct semantic defects.

Its graph contained 132 nodes: 131 diagnostic files plus one observed consumer.
It had 23 exact mappings, five distinct candidate cross-file boundaries,
four unresolved span observations and no approved hard co-edit constraints.
All 132 tentative groups required review. The three core suites passed
148 tests before extraction.

These figures describe that saved prototype run, not a fresh public example,
general coverage claim or independently dispatchable workload.

## Extraction decision

The user requested a new public `lint-workgraph` project, with this new Obsidian
vault. Existing source-project scripts remain provisionally in place; source
deletion was not authorized for this extraction.

Only curated implementation, tests, synthetic examples and English documentation
are transferred. Private captures, application sources, logs, old vault content
and source Git history are excluded. See [[provenance]].

## Verified extracted project

All five offline suites passed **194 tests** in the new checkout:
19 GitHub inventory, 24 overlap, 23 scanner, 73 collector and 55 planner tests.
The parent independently reran the complete suite normally and with site packages
disabled (`python -S`), both successful. No optional MCP package is needed for
these offline tests.

The synthetic example ran from a fresh output directory using the actual planner
CLI twice: four retained records, six nodes, three candidate edges, no hard edges,
one unknown mapping, and identical repeated plans. These are invented inputs,
not a real-project acquisition result.

An optional local-only replay against the prototype's private saved inputs also
preserved the actual graph and accounting. Those inputs/outputs remain excluded
from publication; explanatory private policy links were replaced with standalone
documentation references.

Explicit target-workspace tests cover separate tool/target commits, root
misidentification, stale evidence and traversal. The collector no longer embeds a
personal source path or assumes a particular Serena display project name.

The extraction does not solve [[reproduction-gap]]. The public-exposure gate and
actual publication reference remain to be verified.
