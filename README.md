# sec-investigator

**Constrained-autonomy security investigation agent** — a LangGraph-powered state machine that turns "alert → evidence → risk verdict → structured report" into a deterministic, observable, replayable pipeline.

## Why

- **Constrained autonomy**: the agent never freewheels. It operates inside a typed graph with explicit state contracts and code-level policy gates.
- **Human-in-the-loop**: critical findings pause at an approval gate — no auto-remediation.
- **Fully offline demo**: `DATA_SOURCE=fake` injects synthetic fixtures via `httpx.MockTransport`. No VPN, no enterprise endpoints needed.
- **Parallel forensics**: multi-asset targets fan out via `Send()` — machine and security checks run concurrently per asset.

## Quick start

```bash
uv sync                        # Python ≥3.12
cp .env.example .env           # add your LLM API key
uv run sec-investigator        # FastAPI on :18230
```

Open <http://localhost:18230> and pick a demo target:

| Target | Scenario |
|--------|----------|
| `api2.xs2027.cn` | 5xx source-station failure (critical → approval → report) |
| `game.ali213.net` | 4xx crawler flood |
| `kk331dsdi32onew.liu6t.cn` | Source-station overload |

```bash
uv run pytest -q               # 551 tests, fully offline
cd web && npm run build        # frontend production build
```

<!-- TODO: 在此替换为你本地实跑的 hero 截图 -->

## Architecture

Three layers, `runtime` never imports `surfaces`:

```
START → asset_resolution → supervisor
   ├─→ log_detective (ES + RAG)
   ├─→ dispatch_machine_checks → Send(machine_check per asset) → machine_rollup
   ├─→ dispatch_security_checks → Send(security_guard per asset) → security_rollup
   ├─→ approval_gate (HITL interrupt on critical)
   └─→ reporter → END
```

- **Deterministic routing**: supervisor picks the next worker in code, not LLM free choice.
- **Code-level thresholds**: all risk thresholds live in `EvidencePolicy` — never in prompts.
- **Deterministic evidence**: tool outputs are parsed by `EvidenceCollector` and override whatever the LLM recalls.
- **Model-agnostic**: `build_model(profile)` — hosted APIs, OpenAI-compatible local endpoints, or future local models.

## Package map

| Package | One-liner |
|---------|-----------|
| `src/runtime/` | LangGraph integration, state schema, event protocol, checkpoints, LLM abstraction |
| `src/security/` | Adapters, tools, policies, playbooks, schemas, RAG |
| `src/surfaces/` | Thin FastAPI surface + SSE stream + hosted SPA |
| `web/` | React 19 + Vite + Tailwind v4 + shadcn/ui dashboard |
| `tests/` | Unit + integration + replay suites (all offline) |

Full interface inventory → [docs/REFERENCE.md](docs/REFERENCE.md)

## What works

- ✅ Critical finding → HITL approval gate → resume → structured report
- ✅ Parallel multi-asset forensics with per-asset sub-track visualization
- ✅ Subgraph tool events bubble to top-level SSE stream
- ✅ Dark SOC console UI with collapsible trace tree (Langfuse-style)
- ✅ 3-tier reporter fallback (LLM structured output → json_mode → regex-JSON → deterministic report)

## Known limitations

- GLM analysis text may disagree slightly with deterministic error-rate numbers (e.g. 68.8% vs 70.0%) — report uses the `error_rate` field as authoritative
- Mobile layout is not polished (desktop-first at 1440px)
- `DATA_SOURCE=real` requires internal network access and credentials

## CI

![CI status](https://img.shields.io/badge/CI-pending-yellow)

## License

Internal project — not yet open-sourced.
