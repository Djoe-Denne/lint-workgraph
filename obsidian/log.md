---
title: Vault log
created: 2026-11-14
status: active
---

# Vault log

- 2026-11-14 — Initialized a new project vault with linked architecture, history,
  provenance, limitations, reproduction-gap and backlog notes. No existing vault,
  conversation history or private campaign data was imported.
- 2026-11-14 — Extracted project validation passed: 194 offline tests normally
  and with site packages disabled; the self-contained synthetic graph example
  passed deterministic replay. See [[history]].
- 2026-11-14 — Independent public-exposure/portability review passed. Added the
  requested quick-POC header and proposed rust-analyzer/Sonar backend directions,
  explicitly not implemented or validated.
- 2026-11-14 — Created and pushed the public
  [Djoe-Denne/lint-workgraph](https://github.com/Djoe-Denne/lint-workgraph)
  repository. Verified PUBLIC visibility, default branch `master` and the initial
  remote commit `e1bccc17d4c04cb77e28fb3daa8b0a02bfd4dff6`. See [[history]].
- 2026-11-14 — Added user-requested simple local/transverse rule routing. All 77
  observed rule types classified without source/dependency lookup: strict union
  328 local and 292 transverse. See [[history]].
- 2026-11-14 — Generalized the final dependency command to the whole real
  inventory using the existing native graph: 256 files, 517 candidate edges and
  289 cross-file boundaries. All transverse records attempted; coverage remains
  partial. Reused the completed capture for final graph/report publication.
