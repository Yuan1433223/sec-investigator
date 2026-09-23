"""Fake data-source fixtures.

Synthetic but realistic data derived from the three recorded incidents
(`docs/incidents.md`). This is what the fake backend serves when
``DATA_SOURCE=fake``, so the demo reproduces the same causal chains as the
original enterprise incidents without touching any real system.

Every number below is anchored to a recorded incident so the LLM can reach
the same conclusion it reached in production:
  1. game.ali213.net        — 4xx spike +1000% (distributed crawler scan)
  2. api2.xs2027.cn         — 5xx spike +600%  (source-station application fault)
  3. kk331dsdi32onew.liu6t.cn — 5xx >6000       (high-concurrency origin overload)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IncidentProfile:
    """One incident's characteristic signal, used to synthesise ES/Prom data."""

    key: str
    domain: str | None
    node_ip: str                 # GF/WAF node IP being investigated
    product_ips: list[str]       # extra product IPs returned by node resolution
    origin_ip: str               # 源站 (GF upstream), "ip:port"
    product: str                 # "GF" or "WAF"
    window_start: str            # YYYY-MM-DD HH:MM:SS
    window_end: str
    spike_time: str              # "HH:MM" when the peak occurs
    qps_base: int                # per-minute baseline requests
    qps_peak: int                # per-minute requests at spike_time
    status_share: dict[int, float]      # current-window status code → share
    status_share_prev: dict[int, float] # 30-min-prior (normal) status → share
    top_ips: list[tuple[str, int]]      # (ip, request count) for top-n ranking
    cpu_pct: float               # node CPU usage returned by fake Prometheus
    mem_pct: float
    tcp_estab: int
    has_cc: bool = False
    has_ddos: bool = False
    peak_minute: int = 0         # minute offset of the spike within the window

    @property
    def is_4xx(self) -> bool:
        return any(400 <= s < 500 for s in self.status_share)

    @property
    def is_5xx(self) -> bool:
        return any(500 <= s < 600 for s in self.status_share)


# ---------------------------------------------------------------------------
# The three recorded incidents
# ---------------------------------------------------------------------------

_PROFILES: dict[str, IncidentProfile] = {
    # Incident 1 — distributed crawler scan, 404 (72%) + 499 (25%), top IP 74.7.227.59
    "game.ali213.net": IncidentProfile(
        key="crawler_4xx",
        domain="game.ali213.net",
        node_ip="117.24.6.116",
        product_ips=["103.248.152.176", "103.248.153.12"],
        origin_ip="103.248.152.176:443",
        product="GF",
        window_start="2026-04-23 11:56:40",
        window_end="2026-04-23 12:14:40",
        spike_time="12:03",
        qps_base=600,
        qps_peak=7418,
        status_share={200: 0.15, 301: 0.02, 404: 0.62, 499: 0.19, 403: 0.02},
        status_share_prev={200: 0.93, 301: 0.03, 404: 0.02, 499: 0.01, 403: 0.01},
        top_ips=[
            ("74.7.227.59", 5120),
            ("45.117.11.97", 890),
            ("103.248.153.12", 410),
            ("203.0.113.7", 205),
            ("198.51.100.44", 118),
        ],
        cpu_pct=4.2,
        mem_pct=28.0,
        tcp_estab=1900,
    ),
    # Incident 2 — origin app fault, 502 = 62.9%, fast error (0.07-0.10s)
    "api2.xs2027.cn": IncidentProfile(
        key="origin_5xx",
        domain="api2.xs2027.cn",
        node_ip="118.178.13.52",
        product_ips=["118.178.13.53"],
        origin_ip="180.188.35.116:443",
        product="GF",
        window_start="2026-04-18 12:18:00",
        window_end="2026-04-18 12:36:00",
        spike_time="12:23",
        qps_base=300,
        qps_peak=1800,
        status_share={200: 0.30, 502: 0.629, 503: 0.04, 504: 0.03, 500: 0.001},
        status_share_prev={200: 0.98, 502: 0.01, 503: 0.005, 504: 0.005},
        top_ips=[
            ("223.104.41.98", 860),
            ("117.136.7.12", 420),
            ("117.148.72.5", 305),
            ("112.64.190.9", 144),
        ],
        cpu_pct=5.6,
        mem_pct=22.0,
        tcp_estab=1500,
    ),
    # Incident 3 — high-concurrency origin overload, QPS 31.5万→93.5万/min, all 502
    "kk331dsdi32onew.liu6t.cn": IncidentProfile(
        key="origin_overload",
        domain="kk331dsdi32onew.liu6t.cn",
        node_ip="112.90.155.1",
        product_ips=["112.90.155.2", "112.90.155.3"],
        origin_ip="47.98.255.59:80",
        product="GF",
        window_start="2026-04-18 02:23:40",
        window_end="2026-04-18 02:41:40",
        spike_time="02:24",
        qps_base=525_000,
        qps_peak=935_000,
        status_share={200: 0.94, 502: 0.04, 503: 0.02},
        status_share_prev={200: 0.985, 502: 0.01, 503: 0.005},
        top_ips=[
            ("113.87.88.6", 52_000),
            ("111.18.147.3", 33_400),
            ("112.20.77.9", 21_600),
            ("183.14.190.5", 12_800),
        ],
        cpu_pct=85.0,
        mem_pct=70.0,
        tcp_estab=60_000,
    ),
}

# Alias node/product IPs back to their profile so resolve_ip / prom lookups work.
_IP_TO_PROFILE: dict[str, IncidentProfile] = {}
for _p in _PROFILES.values():
    _IP_TO_PROFILE[_p.node_ip] = _p
    _IP_TO_PROFILE[_p.origin_ip.split(":")[0]] = _p
    for _x in _p.product_ips:
        _IP_TO_PROFILE[_x] = _p


def get_profile(domain: str | None = None, ip: str | None = None) -> IncidentProfile | None:
    """Return the incident profile matching a domain or node/product IP."""
    if domain:
        p = _PROFILES.get(domain)
        if p:
            return p
        # wildcard / subdomain fallback
        for name, prof in _PROFILES.items():
            if name and (name == domain or domain.endswith(name)):
                return prof
    if ip:
        return _IP_TO_PROFILE.get(ip)
    return None


def all_profiles() -> dict[str, IncidentProfile]:
    """All incident profiles, keyed by domain (or node IP for IP-only demos)."""
    return dict(_PROFILES)


# ---------------------------------------------------------------------------
# Static knowledge base for the fake RAG engine (offline runbook excerpts)
# ---------------------------------------------------------------------------

STATIC_KB: list[dict[str, str]] = [
    {
        "source": "runbook/4xx-crawler.md",
        "keywords": ("4xx", "404", "爬虫", "crawler", "扫描", "扫描器", "UA"),
        "text": (
            "4xx 突增排查：\n"
            "1) 先看 status 分布——404 高且 499 高通常指向分布式爬虫/批量扫描，"
            "而非源站故障。\n"
            "2) 校验源站稳定性：若 5xx < 60 且节点 CPU/内存正常，判定为客户端侧爬虫。\n"
            "3) 处置：URI 正则封禁路径拼接探测（如 /forum.php、/home.php?mod=rss）；"
            "对 top IP 加黑名单/人机校验；命中 CC 阈值则启用频率限制。"
        ),
    },
    {
        "source": "runbook/5xx-origin.md",
        "keywords": ("5xx", "502", "源站", "origin", "upstream", "应用故障", "宕机"),
        "text": (
            "5xx 突增排查：\n"
            "1) 关键判据：node status == upstream_status 且响应时间极短（0.07-0.10s）"
            "→ 是源站应用层快速报错，不是网络超时。\n"
            "2) 单源站 = 单点故障；让客户用 `curl -I` 验证源站，检查 Nginx/应用"
            "崩溃、重启或发布。\n"
            "3) 建议增加备用源站与健康检查，消除单点。"
        ),
    },
    {
        "source": "runbook/origin-overload.md",
        "keywords": ("高并发", "过载", "overload", "QPS", "流量突增", "限流", "熔断"),
        "text": (
            "高并发源站过载：\n"
            "1) QPS 数倍突增且单一源站承担 >99% 请求 → 源站过载返回 502。\n"
            "2) 处置：扩容源站（worker/连接/内存）、在多个源站间负载均衡、"
            "收紧单 IP 频率限制、加请求队列/熔断。\n"
            "3) QPS 回落后通常自动恢复。"
        ),
    },
    {
        "source": "runbook/no-attack.md",
        "keywords": ("CC", "DDoS", "攻击", "attack", "pps", "清洗"),
        "text": (
            "攻击判定：仅当 CC PPS 超过阈值（input_pps > 2000 且过滤增量 >= 1000）"
            "或 DDoS bps >= 1Gbps 时判定为攻击。多数 4xx/5xx 突增由爬虫或源站故障"
            "引起，不属于 CC/DDoS 攻击。"
        ),
    },
]


def search_kb(query: str, top_k: int = 3) -> list[dict[str, str]]:
    """Naive keyword match over STATIC_KB — enough to ground the LLM in a demo."""
    q = query.lower()
    scored: list[tuple[float, dict[str, str]]] = []
    for doc in STATIC_KB:
        score = sum(1 for kw in doc["keywords"] if kw in q)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [d for _, d in scored[:top_k]]


# ---------------------------------------------------------------------------
# Helpers used by the fake transport
# ---------------------------------------------------------------------------


def _default_profile() -> IncidentProfile:
    """Benign profile for unknown targets — normal traffic, healthy node."""
    return IncidentProfile(
        key="normal",
        domain=None,
        node_ip="10.0.0.1",
        product_ips=[],
        origin_ip="10.0.0.2:443",
        product="GF",
        window_start="2026-01-01 00:00:00",
        window_end="2026-01-01 00:10:00",
        spike_time="",
        qps_base=200,
        qps_peak=240,
        status_share={200: 0.97, 301: 0.02, 404: 0.01},
        status_share_prev={200: 0.98, 301: 0.01, 404: 0.01},
        top_ips=[("203.0.113.9", 120)],
        cpu_pct=6.0,
        mem_pct=30.0,
        tcp_estab=1200,
    )
