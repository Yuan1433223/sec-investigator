# AGENTS.md

## Scope

This file governs work inside `kks-next`.

`kks-next` is the only active product workspace for the next-generation KKS system.

This repo is expected to be:

- the long-term KKS codebase
- built on released LangGraph packages
- independent from local framework source trees

## Workspace assumptions

The development model for `kks-next` is:

- `LangGraph` is consumed as a package dependency
- the root workspace contains only:
  - `kks-next`
  - `KKShieldHelper-main`
- `KKShieldHelper-main` is the only donor/reference repo expected to sit beside this repo

Do not make this repo depend on any other sibling source tree being present.

## Core architecture

`kks-next` should be built around three layers:

1. `kks_runtime`
2. `kks_security`
3. `kks_surfaces`

### `kks_runtime`

Responsibilities:

- LangGraph runtime integration
- session lifecycle
- state schema
- event protocol
- checkpointing
- streaming
- retries/timeouts
- approvals and HITL
- artifact emission
- model runtime abstraction

### `kks_security`

Responsibilities:

- security-domain tools
- ES/Prometheus/WAF/GF adapters
- collectors
- playbooks
- policies
- report generation
- schemas
- RAG and domain retrieval

### `kks_surfaces`

Responsibilities:

- FastAPI surface
- webhook adapters
- Feishu delivery
- web UI
- future operator interfaces

Surface code must remain thin. No core business logic belongs here.

## Runtime graph rule

Maintain one primary investigation graph.

The current intended shape is:

1. `asset_resolution`
2. `supervisor`
3. target-scoped worker or asset-scoped dispatch
4. asset fan-out via `Send`
5. rollup back into top-level findings
6. approval/report exit

Use:

- `inspection_scope` for resolved assets
- `active_asset` for per-slice execution
- `asset_findings` for per-asset evidence
- top-level `findings` for rolled-up session conclusions

Do not let parallel asset workers race on the same top-level finding key.
Asset-scoped writes must merge into `asset_findings` first, then roll up.

## LangGraph usage rules

Use LangGraph as a runtime dependency, not as an embedded codebase.

Allowed:

- `uv add langgraph==1.1.9`
- `uv add langgraph-checkpoint-postgres`
- `uv add langgraph-checkpoint-sqlite`
- normal imports such as `from langgraph.graph import StateGraph`

Disallowed:

- copying framework code into this repo
- depending on local `langgraph-1.1.9` source tree
- modifying LangGraph internals from inside product code

If framework bugs are encountered:

1. attempt an app-layer workaround
2. isolate a minimal reproduction
3. only then consider a separate fork/patch strategy

## Model architecture rule

Treat the model as a generic compute unit.

Business code should request a capability/profile, not directly bind to a vendor SDK.

Expected model profiles include:

- `fast_classifier`
- `tool_reasoner`
- `structured_extractor`
- `report_writer`
- `long_context_analyst`
- `local_offline_model`

The system must support:

- hosted API models
- OpenAI-compatible local endpoints
- future locally trained/fine-tuned models

without forcing business logic rewrites.

## Engineering priorities

Priority order:

1. clean architecture boundaries
2. deterministic state and artifact contracts
3. safe tool execution
4. domain correctness
5. observability and replayability
6. UX polish

When tradeoffs appear, prefer:

- explicit schemas over implicit dicts
- runtime events over UI coupling to graph internals
- code-level policy over giant prompts
- one runtime path over multiple parallel agent stacks

## Hard rules

1. Do not recreate `Guard / ReAct / Plan` as separate long-term runtime silos.
2. Do not couple UI logic to LangGraph node names.
3. Do not hide critical evidence thresholds only in prompts.
4. Do not create import-time singletons for graphs, model clients, or persistent stores.
5. Do not place HTTP/webhook/Feishu logic inside graph node business code.
6. Do not route a target to a worker node whose tools cannot process that target type.
7. Do not write asset-parallel worker outputs directly into shared top-level finding keys.

## Adapter and resource lifecycle policy

All adapters that hold external connections (`AsyncElasticsearch`, `httpx.AsyncClient`,
Prometheus client, Milvus/Mongo connection, etc.) must follow this pattern:

- implement `close()` / `aclose()` and expose `__aenter__` / `__aexit__`
- tool factories own the adapter instance via closure scope (lazy-init on first use,
  cached for the factory lifetime, never create a new client per tool call)
- long-lived runtime sessions (FastAPI request, background task, graph invocation)
  must close owned clients on exit, use `async with` or explicit `aclose()` in a
  `finally` block
- do not instantiate adapters at module level, they are not constants

This rule exists because unbounded connection creation is a silent failure mode that
becomes visible only under load or in long-running sessions.

## Donor code policy

Primary donor source: `KKShieldHelper-main`.

Migrate from it selectively:

- collectors
- adapters
- report schemas
- domain helpers
- playbook logic

Do not transplant legacy graph wiring as architecture.

## Testing policy

Required test focus:

- adapter correctness
- collector correctness
- state schema validation
- artifact schema validation
- report generation correctness
- replay tests for representative incidents
- graph fan-out and rollup correctness
- cross-model evaluation for key model profiles

Avoid spending major effort preserving legacy graph wiring behavior unless it protects domain semantics.

## Documentation policy

Keep these files current:

- `AGENTS.md`
- `todo.md`

Architecture documents should reflect the actual codebase, not donor-repo history.

## Short directive

Build the future KKS here.

Use LangGraph as a dependency, KKS legacy code as a donor, and keep the architecture clean enough that the next rewrite is unnecessary.
