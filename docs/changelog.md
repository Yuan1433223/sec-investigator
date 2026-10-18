# Changelog

## M6 — Web frontend (2026-04-30)
- React 19 + Vite + TS SPA: pipeline rail, SSE event timeline, findings panel, report card, approval dialog
- FastAPI static hosting of `web/dist`; Vite proxy for dev
- `POST /investigation/resume` for HITL resume

## M5 — LLM compatibility (2026-04-30)
- Zhipu GLM OpenAI-compatible endpoint integration
- `with_structured_output(method="function_calling")` fix across 5 nodes
- Verified end-to-end with GLM

## M4 — Fake data source (2026-04-30)
- `DATA_SOURCE=fake/real` seam via `httpx.MockTransport`
- Synthetic fixtures from 3 real incidents (`docs/incidents.md`)
- `tests/unit/test_fake_source.py` locks tool contract
- Fully offline suite (~6s)

## M3 — Documentation cleanup (2026-09-23)
- Merged AGENTS.md + CLAUDE.md → single AGENTS.md
- Merged REVIEW.md + REVIEW2.md → single REVIEW.md (now archived)
- Extracted `docs/incidents.md` from context.md
- Added root README.md + architecture.svg

## M2 — Empty directory cleanup (2026-09-23)
- Removed dead packages: `executor`, `sessions`, `resources`, `reports`

## M1 — Renaming (2026-09-23)
- `kks_runtime → runtime`, `kks_security → security`, `kks_surfaces → surfaces`
- Project renamed to `sec-investigator`
- Brand cleanup: removed enterprise identifiers

---

## A0 — Critical→approval→report closed loop (2026-10-02)
- Deterministic evidence extraction (`policies/extraction.py`)
- Loop protection in tool tracing (`max_repeated=4`)
- Reporter 3-tier fallback + empty-shell detection + deterministic report
- Removed `current_time` from log_detective / security_guard
- NoneType fallback in structured extractor

## A1 — Subgraph event bubbling + asset swimlanes (2026-10-02)
- `subgraphs=True` in SSE stream → tool events reach top level
- `_unwrap()` pure function for namespace normalization
- Frontend: lane columns + per-asset sub-tracks
- AG-UI adapter layer (`web/src/lib/agui.ts`)

## A2 — Dark SOC console UI (2026-10-02)
- Tailwind v4 + shadcn/ui (Radix primitives)
- Dark token system (zinc-950 base, emerald accent)
- Collapsible trace tree (Langfuse-style: lane = trace root, tool card = span)
- Fixed extractAsset IPv4 extraction
