# AGENTS.md

## Scope

This file governs work inside `sec-investigator`.

`sec-investigator` is a constrained-autonomy security investigation agent:
a unified, state-driven investigation runtime built on LangGraph, layered as
`runtime` / `security` / `surfaces`.

- built on released LangGraph packages
- independent from local framework source trees
- `KKShieldHelper-main` is the only donor/reference repo expected to sit beside it

Do not make this repo depend on any other sibling source tree being present.

## Core architecture

Three layers:

1. **`runtime`** — LangGraph integration, session lifecycle, state schema, event
   protocol, checkpointing, streaming, retries/timeouts, approvals (HITL),
   artifact emission, model-runtime abstraction.
2. **`security`** — security-domain tools; ES/Prometheus/WAF/GF adapters;
   collectors; playbooks; policies; report generation; schemas; RAG/domain retrieval.
3. **`surfaces`** — FastAPI surface, webhook adapters, Feishu delivery, web UI.
   Surface code must remain thin. No core business logic belongs here.

## Runtime graph rule

Maintain one primary investigation graph:

```
START
  → asset_resolution
  → supervisor
     → log_detective
     → dispatch_machine_checks → Send(machine_check per asset) → machine_rollup
     → dispatch_security_checks → Send(security_guard per asset) → security_rollup
     → approval_gate
     → reporter → END
```

Use:
- `inspection_scope` for resolved assets
- `active_asset` for per-slice execution
- `asset_findings` for per-asset evidence
- top-level `findings` for rolled-up session conclusions

Do not let parallel asset workers race on the same top-level finding key.
Asset-scoped writes must merge into `asset_findings` first, then roll up.

## LangGraph usage rules

Use LangGraph as a runtime dependency, not as an embedded codebase.

Allowed: `uv add langgraph==1.1.9`, checkpoint packages, normal imports
(`from langgraph.graph import StateGraph`).

Disallowed: copying framework code into this repo; depending on local framework
source trees; modifying LangGraph internals from product code. If framework bugs
are hit, attempt an app-layer workaround, then isolate a minimal reproduction.

## Model architecture rule

Treat the model as a generic compute unit. Business code requests a
capability/profile, not a vendor SDK. Expected profiles: `fast_classifier`,
`tool_reasoner`, `structured_extractor`, `report_writer`, `long_context_analyst`,
`local_offline_model`. Must support hosted APIs, OpenAI-compatible local
endpoints, and future locally trained models without rewriting business logic.

## Engineering priorities

1. clean architecture boundaries
2. deterministic state and artifact contracts
3. safe tool execution
4. domain correctness
5. observability and replayability
6. UX polish

When tradeoffs appear, prefer: explicit schemas over implicit dicts; runtime
events over UI coupling to graph internals; code-level policy over giant
prompts; one runtime path over multiple parallel agent stacks.

## Hard rules

1. Do not recreate `Guard / ReAct / Plan` as separate long-term runtime silos.
2. Do not couple UI logic to LangGraph node names.
3. Do not hide critical evidence thresholds only in prompts.
4. Do not create import-time singletons for graphs, model clients, or persistent stores.
5. Do not place HTTP/webhook/Feishu logic inside graph node business code.
6. Do not route a target to a worker node whose tools cannot process that target
   type. Worker eligibility must be determined from validated capabilities, not
   just target presence.

## Adapter and resource lifecycle policy

All adapters holding external connections (`AsyncElasticsearch`, `httpx.AsyncClient`,
Prometheus client, Milvus/Mongo connection, etc.) must:
- implement `close()`/`aclose()` and expose `__aenter__`/`__aexit__`
- be owned by the tool factory via closure scope (lazy-init on first use, cached
  for factory lifetime — never a new client per tool call)
- be closed by long-lived runtime sessions on exit (use `async with` or explicit
  `aclose()` in a `finally` block)
- never be instantiated at module level

Unbounded connection creation is a silent failure mode under load.

## Donor code policy

Primary donor source: `KKShieldHelper-main`. Migrate from it selectively
(collectors, adapters, report schemas, domain helpers, playbook logic).
Do not transplant legacy graph wiring as architecture.

## Testing policy

Required focus: adapter correctness; collector correctness; state schema
validation; artifact schema validation; report generation correctness; replay
tests for representative incidents; graph fan-out and rollup correctness;
cross-model evaluation for key model profiles.

External data sources must be mocked (respx / fixtures) so the suite runs fully
offline and fast. Do not let tests reach real ES/Prometheus/WAF/GF endpoints.

## Documentation policy

Keep current: `AGENTS.md`, `todo.md`. Architecture docs reflect the actual
codebase, not donor-repo history.

## Short directive

Build a constrained-autonomy security investigation runtime.
Use LangGraph as a dependency, KKS legacy code as a donor, and keep the
architecture clean enough that the next rewrite is unnecessary.
