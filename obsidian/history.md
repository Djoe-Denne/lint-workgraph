---
title: Project history
created: 2026-11-14
status: published
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

## Public publication

Published on 2026-11-14:
[Djoe-Denne/lint-workgraph](https://github.com/Djoe-Denne/lint-workgraph).
GitHub visibility was verified as **PUBLIC**, with default branch `master`.
The first published commit is
`e1bccc17d4c04cb77e28fb3daa8b0a02bfd4dff6`; the remote branch matched that local
commit after the initial push.

The exact curated public candidate passed independent exposure/portability
security review. A later four-file documentation delta added the user-requested
quick-POC summary and backend directions; its full diff and staged hashes were
rechecked before publication. No real captures, private environment or original
application implementation were included.

The README and vault now identify this as a quick POC. A Rust-focused successor
should evaluate replacing both MCP integrations with a rust-analyzer-based
backend; a Sonar-based analysis library is an alternative to investigate for
broader language coverage. Neither replacement is implemented or validated, and
no specific Sonar library has been selected.

The extraction and publication do not solve [[reproduction-gap]]. License
selection, broader live origin support and platform/server validation remain
open in [[backlog]] and [[limitations]].

## Simplified locality policy

The user subsequently chose to avoid signature/body reasoning for first-pass
routing: all rules are transverse unless manifestly local. The new standalone
`diagnostic-scope.py` implements explicit documentation/mechanical local exceptions
and a conservative default for all other known or unknown rules.

Applied to the saved inventory, all 77 observed rule types were recognized.
All 1,046 records were retained; the strict union of 620 routes to 328 local
and 292 transverse. The original 1,312 Sonar keys route to 644 local and
668 transverse. No dependency queries or fixes were performed for this routing.
This does not turn the 292 candidates into proven transverse corrections or
hard co-edit groups.

## Whole-inventory dependency command

The final command was generalized to use the existing native Rust graph, without
manual seeds or the legacy one-symbol origin profile. Real collection processed
all 1,046 records: 584 local skips and 462 transverse attempts (336 query-served,
126 unresolved localization). No records remained pending or budget-stopped.

The completed native capture contains 9,348 observations: 5,156 source-verified,
2,792 backend-observed and 1,400 unresolved. Its final file graph has 256 nodes,
517 candidate coupling edges and 289 distinct cross-file boundaries, with all
records retained and zero consumer validation issues.

Measured successful stages: native collection 110.93 seconds; subsequent
validation/assembly/publication 144.27 seconds using the same completed capture,
without recollecting. The collector and actual final-command assembly functions
were exercised on real data; a second live unified CLI run was not performed.
The callable CLI wiring is covered by synthetic tests.

An inventory read/hash race and a quadratic raw/source alias check were corrected
with regressions. Partial backend coverage, stale-snapshot warnings and unresolved
native endpoints remain explicit. No index rebuild, source corrections, hard
co-edit unions or correction-worker dispatch occurred.

## Correction-lot selection and optimization

Research compared balanced graph partitioning with community detection. METIS
is an established native fit, but its current PyPI release has no official
Windows wheel. For this small POC, the implementation avoids adding a native
toolchain or environment and uses LPT followed by bounded deterministic
move/swap refinement. Research links and the precise objective are in the
partitioning guide and contract; this is not a METIS reimplementation.

On the actual saved graph, 620 strict units became 598 assigned units plus
22 manual-path units. The 131 verified editable files have exclusive owners;
120 context-only nodes have none. Default target 50 produced 12 proposed lots,
loads 47–59 and capacity 60. Across 87 eligible verified affinity pairs, the
cross-lot cut decreased from 82 to 36, with zero overload.

Thirty-three improvements reached a local move/swap optimum. Parent real CLI
repeat completed in 0.764 seconds, with identical non-timing output and unchanged
graph input. All 271 offline tests passed. Independent correctness review checked
gain calculations on 150 small graphs and reconciled the real manifest.

Lots retain directed boundary witnesses, read-only context and review tasks.
No sources were corrected, agents dispatched or global optimality claimed.
