# AGENTS.md

## Scope

`sec-investigator` — constrained-autonomy security investigation agent built on LangGraph 1.1.9.

Three layers: `runtime` / `security` / `surfaces`. `runtime` never imports `surfaces`.

## Build & test

```bash
uv sync
uv run pytest -q          # 551 tests, fully offline
cd web && npm run build    # frontend (tsc strict + vite)
uv run sec-investigator    # dev server on :18230
```

External endpoints must always be mocked in tests. `DATA_SOURCE=fake` (default) injects `httpx.MockTransport` — no VPN, no enterprise systems.

## Code map

```
src/runtime/        # LangGraph graph, state, events, checkpoints, LLM profiles
src/security/       # Adapters, tools, policies, schemas, playbooks, RAG
src/surfaces/       # Thin FastAPI + SSE stream + hosted SPA
web/                # React 19 + Vite + Tailwind v4 + shadcn/ui
tests/              # unit / integration / replay (all offline)
docs/REFERENCE.md   # Full interface inventory — read this before changing APIs
```

## Main investigation graph

```
START → asset_resolution → supervisor
   ├─→ log_detective (ES + RAG)
   ├─→ dispatch_machine_checks → Send(machine_check per asset) → machine_rollup
   ├─→ dispatch_security_checks → Send(security_guard per asset) → security_rollup
   ├─→ approval_gate (HITL interrupt on critical)
   └─→ reporter → END
```

- `inspection_scope` = resolved assets, `active_asset` = per-slice execution
- `asset_findings` = per-asset evidence, `findings` = rolled-up session conclusions
- Asset workers write to `asset_findings` first, then roll up — never race on top-level keys

## Hard rules

1. **No module-level singletons** for graphs, model clients, adapters, or tool lists. Use lazy-init factories with closure-held clients.
2. **Code-level policy over prompts** — risk thresholds live in `EvidencePolicy`, not in LLM prompts.
3. **Deterministic evidence** — tool outputs are parsed by `EvidenceCollector` and override LLM-recalled numeric fields.
4. **LangGraph as dependency** — never copy framework code. If a bug hits, work around at app layer.
5. **Model-agnostic** — `build_model(profile)` abstraction, no vendor SDK imports in business code.
6. **Thin surfaces** — no business logic in HTTP/webhook/Feishu handlers.
7. **No UI coupling to node names** — frontend maps SSE events via AG-UI adapter (`web/src/lib/agui.ts`).

## Adapter lifecycle

All adapters holding external connections must:
- implement `aclose()` and be owned by the tool factory via closure scope
- lazy-init on first use, cached for factory lifetime — never a new client per call
- never be instantiated at module level

## Data-source seam

`Settings.data_source` = `fake` (default) or `real`. When changing an adapter, route client construction through `security/fake/client.build_async_client()` so fake mode keeps working.

## Documentation

- `docs/REFERENCE.md` — full package/config/state/event/tool inventory
- `docs/changelog.md` — historical M1–M6 progress
- `todo.md` — active backlog

## Short directive

Build a constrained-autonomy security investigation runtime. Use LangGraph as a dependency, keep architecture clean enough that the next rewrite is unnecessary.
