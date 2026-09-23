# Recorded Incidents

Three real production incidents recorded during the original system's operation.
They are used as the replay fixtures and the gold-standard answers for the demo
path. The synthetic data source (`DATA_SOURCE=fake`, see AGENTS.md) is derived
from these so the demo reproduces realistic causal chains.

Each entry: [告警实体] at [时间] via Grafana, assembled into [分析问题], processed
through the investigation graph, ending in the [AI 诊断报告] conclusion.

---

## 1. game.ali213.net — 4xx spike +1000% (distributed crawler scan)

- **Alert time**: 2026-04-23 12:11
- **Alert name**: 域名1min聚合4xx趋势突增1000%
- **Window**: 2026-04-23 11:56:40 → 12:14:40
- **Gold conclusion**: 4xx spike driven by a distributed crawler/batch-scan wave,
  peak 7418/min at 12:03, ~12× baseline. Source site itself stable (5xx <60
  total), nodes healthy. `404` (72%, invalid-path probes like `/forum.php`,
  `/home.php?mod=rss`) + `499` (25%, crawlers disconnecting early). UA spoofed as
  normal browsers; no DDoS/CC alert triggered.
- **Advice**: URI regex block for path-joining probes; blacklist / human-verify
  top IP `74.7.227.59`; shield invalid RSS param combos; enable CC frequency
  limits if it persists.

## 2. api2.xs2027.cn — 5xx spike +600% (source-station application fault)

- **Alert time**: 2026-04-18 12:33
- **Alert name**: 域名1min聚合5xx趋势上涨600%
- **Window**: 2026-04-18 12:18:00 → 12:36:00
- **Gold conclusion**: 502 returned directly by the origin `180.188.35.116:443`
  (node `status` == `upstream_status` == 502), 5xx ratio ~100% from 12:23, ~10
  min outage. Origin response 0.07–0.10s = fast error, not timeout → app-layer,
  not network. Single origin = single point of failure. Nodes healthy; normal
  mobile traffic (`okhttp/3.12.6`), no attack.
- **Advice**: have customer check origin Nginx/app crash/restart or deploy; verify
  with `curl -I`; add standby origin + health checks.

## 3. kk331dsdi32onew.liu6t.cn — 5xx >6000 (high-concurrency origin overload)

- **Alert time**: 2026-04-18 02:38
- **Alert name**: 域名1min聚合5xx超6000、源站域名1min聚合5xx超3000
- **Window**: 2026-04-18 02:23:40 → 02:41:40
- **Gold conclusion**: QPS spiked ~3× (31.5万→93.5万/min at 02:24), main origin
  `47.98.255.59:80` took >99% of requests and briefly overloaded → 502. All
  17,569 5xx are 502; node/upstream counts match. Same wave as the QPS alarm at
  01:50–02:05 (uni-app UA 84%, `/message/unreadCount` 39%). Recovery automatic as
  QPS fell.
- **Advice**: scale origin (workers/conns/mem); load-balance the 3 origins;
  consider tightening per-IP rate limits; add request queue / circuit breaker.

---

## Usage

- **Replay tests**: `tests/replay/test_incident_replay.py` pre-injects these
  findings and asserts the graph routes correctly and produces a valid report.
- **Demo data**: the fake source derives ES/Prom/security fixtures from these
  windows so the demo reproduces the same conclusions.
