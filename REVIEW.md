# Architecture & State Review

> Last updated: 2026-09-23. Holds `sec-investigator` to a foundation-grade
> standard, not only an enterprise-delivery standard.

## Executive Summary

`sec-investigator` is directionally strong and now structurally healthy:

- Clean three-layer split: `runtime` / `security` / `surfaces`
- Typed state, event, finding, artifact, and report contracts
- Model-profile abstraction — no vendor lock-in in business code
- Deterministic, capability-driven supervisor routing (code decides, LLM writes task only)
- Code-level evidence thresholds (`EvidencePolicy`), no hard thresholds in prompts
- Asset fan-out via `Send`, `asset_findings` reducer, rollup back into top-level findings
- Full event stream: `ToolCallEvent / ToolResultEvent / ArtifactEvent / FinalEvent`
- HITL gate wired: `EvidencePolicy.requires_approval` → `approval_gate_node`
- 485 tests, fully offline and fast (~6s suite)

The project is a credible foundation candidate, not yet a foundation. That
distinction is healthy and should not be resolved by lowering the standard.

## What Is Solid (do not revisit)

| Area | Evidence |
|------|----------|
| Layering | `runtime` never imports from `surfaces` — no layer violation |
| Provider abstraction | `build_model(profile)` — no vendor SDK in business code |
| Supervisor routing | `_next_worker` pure-code dispatch; capability scope from resolved assets |
| Tool tracing | `make_traced_tools()` wraps all workers |
| HITL | `approval_gate_node` + `interrupt()` + resume cycle — fully wired |
| Adapter lifecycle | Lazy-init, closure-scoped, `aclose()` in finally blocks |
| Checkpoint | SQLite (dev) / Postgres (prod) factory |
| Surface thinness | API and webhook layers carry no business logic |
| Asset resolution | First-class graph stage; resolves target → `NodeMachine` by capabilities |
| Test hygiene | Full suite mocked offline; asset resolution mockable |

## Current investigation graph

```
START → asset_resolution → supervisor
   ├─→ log_detective
   ├─→ dispatch_machine_checks → Send(machine_check per asset) → machine_rollup
   ├─→ dispatch_security_checks → Send(security_guard per asset) → security_rollup
   ├─→ approval_gate
   └─→ reporter → END
```

`asset_resolution` produces `inspection_scope[]` and `capability_scope`;
workers are dispatched per IP, per typed capability — not blindly by target presence.

## Open gaps / showcase blockers

### 1. No independent runnable data path (P0)
The original `.env` referenced enterprise intranet endpoints (ES/Prom/WAF/GF,
even the LLM relay). The project must be independently runnable. Plan: a
`DATA_SOURCE=fake` source selection at the adapter seam, serving synthetic
fixtures derived from the 3 recorded incidents (see `docs/incidents.md`).

### 2. Surface hardening extension points missing (P1)
No framework story for auth, authorization, tenant isolation, or rate limiting.
These must exist as explicit extension points with reference defaults before the
system is treated as a deployable base layer.

### 3. Error normalization (P2)
`ErrorEvent` exists but is not yet the universal failure contract. Wrap
worker/reporter bodies with normalized error emission; preserve degraded report
generation when one worker fails.

### 4. Sync RAG isolation (P2)
`rag/engine.py` still needs `anyio.to_thread.run_sync` wrapping if live traffic
hits it heavily.

### 5. In-session tool-call cache (P2)
Repeated ES calls can still occur across redispatch loops. Add a
per-investigation cache in the ES tool factory.

### 6. Alert time-window alignment (P2)
Make alert end offset configurable; align ES comparison windows with the same setting.

## Target architecture (enterprise-grade direction)

A mature version adds these boundaries:

- `asset_resolution` as a first-class graph node (done)
- independent policy engine, not just an evidence-threshold file
- tenant / auth / RBAC / rate-limit into system boundaries
- event bus / audit / replay / eval into runtime defaults
- async ingress independent of the local in-memory flow
- domain services explicit — runtime must not assemble surface delivery logic

Reference shape for the target structure:

```
src/
  runtime/        # graph runtime + session kernel + state/events/checkpoint
  security/       # pure domain: assets, playbooks, policies, schemas, services
  surfaces/       # interaction: API / webhook / SSE / Feishu
  integrations/   # external-system adapters (future split from security)
  platform/       # auth, tenancy, audit, observability, config (future)
  eval/           # replay, benchmark, datasets (future)
```

The most important structural rule: **runtime must not depend on surface logic**,
and **integrations only connect external systems without owning investigation
semantics**.

## One-line judgment

`sec-investigator` is now a correctly shaped, offline-testable investigation
kernel; maturing it into an enterprise-grade platform requires governance,
audit, tenancy, replay, and async ingress on top of the existing core.
