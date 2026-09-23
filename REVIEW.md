# Architecture Review

Last updated: 2026-04-27.

## Review Position

This review holds `sec-investigator` to a foundation-grade standard, not only an enterprise-delivery standard. The codebase should be built with the discipline required to survive future rewrites — or make them unnecessary.

## Executive Summary

`sec-investigator` is directionally strong:

- Clean three-layer split (`runtime` / `security` / `surfaces`)
- Typed state, event, finding, artifact, and report contracts
- Model-profile abstraction — no vendor lock-in in business code
- Deterministic supervisor routing — pure code, LLM generates tasks only
- Tool budget enforced via `recursion_limit = max_tool_calls * 2 + 1`
- Full event stream: `ToolCallEvent / ToolResultEvent / ArtifactEvent / FinalEvent`
- HITL gate wired: `EvidencePolicy.requires_approval` → `approval_gate_node` → approve/reject
- 387 tests passing; 3 production replay incidents covered

The project is a credible foundation candidate, not yet a foundation. That distinction is healthy and should not be resolved by lowering the standard.

---

## What Is Solid (do not revisit)

| Area | Evidence |
|------|----------|
| Layering | `runtime` never imports from `surfaces` — *except one violation listed below* |
| Provider abstraction | `build_model(profile)` — no vendor SDK in business code |
| Supervisor routing | `_next_worker` pure-code dispatch; `target_type == "ip"` gate on `machine_check` |
| Tool tracing | `make_traced_tools()` wraps all workers |
| HITL | `approval_gate_node` + `interrupt()` + resume cycle — fully wired |
| Adapter lifecycle | Lazy-init, closure-scoped, `aclose()` in finally blocks |
| Checkpoint | SQLite (dev) / Postgres (prod) factory |
| Surface thinness | API and webhook layers carry no business logic |

---

## Open Gaps

### 1. Asset resolution is not a first-class graph stage

**Production behavior (KKShieldHelper-main)**

`ServerQueryClient.analysis_use_domain` runs before any worker:

1. Domain/IP → WAF or GF product APIs → `node_ip` list + `product_ip` list
2. GF product priority: GameShield → High-Defence IP → DDoS High-Defence (first match wins)
3. WAF API: `GET /api/security_assistant/get_node_ips?domain=X&time_stamp=Y`
4. Each resolved IP is typed as one of three `NodeMachine.type` values:
   - `node` — Prometheus-monitored only → dispatch `machine_check`
   - `product` — CC/DDoS-protected only → dispatch `security_guard`
   - `node_product` — both → dispatch both workers
5. Supervisor dispatches workers **per IP, per type** — not blindly by target presence.

**sec-investigator current state**

`collectors/node_resolver.py`, `waf_collector.py`, `gf_collector.py` exist but are not wired as a graph node. Eligibility check is on raw user input (`target_type == "ip"`), not on resolved `NodeMachine.type`.

**CLAUDE.md §Hard rules §6 is formally written but not enforced by any runtime struct:**

> Worker eligibility must be determined from validated capabilities, not just target presence.

**Required action**

Add `asset_resolution` as an explicit graph stage before the supervisor:

```
entry → asset_resolution → supervisor → workers
```

State fields to populate in `asset_resolution`:

```python
target_type: Literal["ip", "domain"]
source_type: Literal["WAF", "GF"] | None
node_ips: list[str]          # Prometheus-eligible
product_ips: list[str]       # CC/DDoS-eligible
inspection_scope: list[NodeMachine]
```

Supervisor routes workers based on `inspection_scope[i].type`, not on raw `target`.

---

### 2. Hard attack thresholds live only in prompts

Old KKS encodes these as explicit code conditions in `tools/` clients. sec-investigator references them only in playbook system prompts. A prompt is not a policy.

| Signal | Threshold | Required location |
|--------|-----------|-------------------|
| CC attack active | `input_pps > 2000 AND (input_pps - input_submit_pps) >= 1000` | `policies/evidence.py` |
| DDoS attack active | `peak_bps > 1_000_000` kbps (≥ 1 Gbps) | `policies/evidence.py` |
| CPU critical | > 90 % | `policies/evidence.py` |
| HTTP 4xx critical | > 50 % of total | `policies/evidence.py` |
| HTTP 5xx critical | > 10 % of total | `policies/evidence.py` |

**Required action:** Move threshold checks into `EvidencePolicy` or a new `ThresholdPolicy`. Workers emit raw numbers; policy derives `risk_level` and `alert_status` deterministically. The LLM must not be the single point of failure for threshold evaluation.

---

### 3. Reporter imports from `surfaces` — CLAUDE.md §Hard rules §5 violation

`runtime/graph/nodes/reporter.py` line 27:

```python
from surfaces.feishu.delivery import send_report_to_feishu
```

`runtime` must not depend on `surfaces`. This breaks both the layer contract and hard rule 5 ("Do not place HTTP/webhook/Feishu logic inside graph node business code").

**Required action:** Remove the Feishu call from `reporter_node`. Reporter emits `FinalEvent`. Surface layer subscribes to `FinalEvent` and drives Feishu delivery independently. Two-line removal from `reporter.py`, corresponding addition in a `feishu_dispatcher` surface hook.

---

### 4. `alert_status=None` fails Pydantic validation when LLM returns null

`InvestigationReport.alert_status` is typed `Literal["normal", "warning", "critical"]` (non-Optional). When ES data is empty and the LLM emits JSON `null`, Pydantic raises a validation error before `_derive_risk_level`'s `or "warning"` fallback is ever reached.

**Required action:**

```python
alert_status: Literal["normal", "warning", "critical"] | None = Field(default="warning", ...)
```

---

### 5. Empty-data exhaustion: no early-stop in workers

When ES returns zero hits across consecutive tool calls, `log_detective` continues querying until `recursion_limit` is exhausted (21 steps). This produces `GraphRecursionError` instead of a clean "insufficient data" finding.

Observed: `kk331dsdi32onew.liu6t.cn` with stale ES index → 10 tool calls returned zero rows → graph raised exception.

**Required action:** Add consecutive-empty-result counter in `make_traced_tools` wrapper or playbook post-processing. If N = 3 consecutive tool results return zero records, emit early-stop signal. Prevents runaway loops on data-unavailable targets.

---

### 6. Surface hardening — explicit extension points missing

There is no framework story for authentication, authorization, tenant isolation, or rate limiting. These must exist as explicit extension points and reference defaults before the system is treated as a deployable base layer — even if deployment-specific credentials remain private.

This is currently recorded as a Phase 5 todo item. It remains open.

---

## Donor code not yet migrated

| Donor module | Value | Priority |
|---|---|---|
| `tools/waf_client.py` + `tools/gf_client.py` | WAF/GF node resolution API calls | P0 — blocks asset_resolution |
| `logic/server_check.py` `NodeMachine` dataclass | Typed per-IP capability model | P0 — blocks asset_resolution |
| `logic/server_check.py` concurrent gather pattern | 6 sub-queries per node via `asyncio.gather` | P1 — performance |
| `utils/feishu_card.py` rich card templates | 20+ variable Feishu card format | P2 — post-switchover |
| `utils/grafana_render.py` chart rendering | PNG panel → Feishu image upload | P2 — post-switchover |

---

## Priority order

1. **Fix layer violation** — remove Feishu import from `reporter_node` (30 min, zero risk)
2. **Fix `alert_status` schema** — allow `None`, add default (15 min)
3. **Add early-stop on consecutive empty results** (half day)
4. **Encode hard thresholds in `EvidencePolicy`** (1 day)
5. **Migrate `asset_resolution` node** — wire `node_resolver` into graph as Stage 0 (2–3 days)
6. **Surface hardening extension points** — auth/rate-limit hooks (1 day)
7. **P2 Feishu polish** — rich card + Grafana chart (post-switchover)

---

## What Must Be True Before Foundation Status

- Worker routing is capability-safe and typed by `NodeMachine.type`, not raw target string
- All hard thresholds are code, not prompts
- Layer boundaries are clean: `runtime` imports nothing from `surfaces`
- Failure modes are normalized into typed platform events, not unhandled exceptions
- Integration test passes against real adapters
- Cross-model evaluation exists for key profiles
