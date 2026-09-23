"""
General-purpose utility tools for the investigation graph.

Ported from KKShieldHelper-main/agents/tools/public.py and
KKShieldHelper-main/agents/tools/knowledge.py (table-structure tools).

Tools:
  - current_time: returns the current datetime in Asia/Shanghai timezone.
  - check_connection_status: concurrent ICMP ping for a list of targets.
  - get_gf_log_table_structure: static ES field reference for GF (高防) logs.
  - get_waf_log_table_structure: static ES field reference for WAF logs.

These are pure-Python / stdlib tools — no external adapter needed.
PUBLIC_TOOLS is the module-level export consumed by worker nodes.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# UTC+8 (Asia/Shanghai) — no pytz / zoneinfo dependency
_CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# Static table-structure payloads (source: KKShieldHelper-main/agents/tools/knowledge.py)
# ---------------------------------------------------------------------------

_GF_TABLE_STRUCT = """
| 参数名 | 类型 | 说明 | 取值示例 |
| ---- | ---- | ---- | ---- |
| body_bytes_sent | 整型 | 发送到客户端的字节数，不包含响应头的大小 | 123 |
| bytes_sent | 整型 | 发送给客户端的总字节数 | 434 |
| create_date | 日期 | es记录创建时间 | 2023-04-04 15:46:48 |
| headers | 文本 | 客户端请求头部信息 | json请求头数据 |
| http_host | 文本 | 防护域名，host请求头携带的域名 | 1014wgr01.kktest.com.cn |
| hostname | 文本 | 节点名称 | s202-98 |
| server_addr | 关键字 | 防护节点IP | 127.0.0.1 |
| query_string | 文本 | 客户端请求中的查询字符串 | title=tm_content%3Darticle&pid=123 |
| request_time | 浮点 | 节点到客户端响应时间 | 0.19 |
| request_method | 文本 | 客户端请求的请求方法 | GET POST |
| request_length | 长整型 | 回源字节数，含请求行、头、体。单位：Byte | 1111 |
| real_client_ip | 关键字 | 真实客户端IP；无法判定时显示- | 127.0.0.1 |
| request_path | 文本 | 被请求的相对路径（不含查询字符串） | /news/search.php |
| request_uri | 文本 | 被请求的相对路径（含查询字符串） | /news/search.php?a=2&b=1 |
| server_id | 整型→关键字 | 规则ID | kk_123 |
| server_name | 文本 | nginx配置上的域名 | 1014wgr01.kktest.com.cn |
| status | 整型 | HTTP状态码 | 200 |
| scheme | 关键字 | http类型 | http 或 https |
| time | 日期 | 客户端请求的发起时间 | 2023-02-08T10:17:31+08:00 |
| upstream_addr | 关键字 | 源站响应ip:端口 | 127.0.0.1:443 |
| upstream_status | 整型 | 源站响应HTTP状态码 | 200 |
| upstream_response_length | 整型 | 源站响应大小。单位：Byte | 123 |
| upstream_response_time | 浮点 | 源站响应处理时间。单位：秒 | 0.002 |
| upstream_connect_time | 浮点 | DNS解析+TCP握手时间 | 0.001 |
| upstream_header_time | 浮点 | connect_time+发送+源站返回头所用时间 | 0.002 |
| http_x_forwarded_for | 文本 | X-Forwarded-For字段，逗号分割按转发顺序 | 127.0.0.1,127.0.0.2 |
| http_user_agent | 文本 | User-Agent字段 | Dalvik/2.1.0 (...) |
| http_referer | 文本 | Referer字段；无来源URL时显示- | http://example.com |
| remote_addr | 关键字 | 与游戏盾建立连接的IP | 客户端ip |
| remote_port | 整型 | 与节点建立连接的端口 | 客户端连接端口 |
| response_headers | 文本 | 源站返回的响应头信息 | |
"""

_WAF_TABLE_STRUCT = """
| 参数名 | 类型 | 说明 | 取值示例 | 是否必需（默认是） |
| ---- | ---- | ---- | ---- | ---- |
| create_date | 日期 | 客户端请求的发起时间 | 2023-04-04 15:08:49 | 是 |
| event_type | 文本 | 防护事件类型 | CC攻击，SQL注入攻击 | 是 |
| headers | 文本 | 客户端请求头部信息 | json请求头数据 | 是 |
| http_host | 文本 | 防护域名 | 1014wgr01.kktest.com.cn | |
| http_user_agent | 文本 | User-Agent字段 | Dalvik/2.1.0 (...) | 是 |
| m_ip | 关键字 | 转发地址 | 0.0.0.0 | 是 |
| m_port | 整型 | 转发端口 | 8080 | 是 |
| real_client_ip | 关键字 | 真实客户端IP；无法判定时显示- | 127.0.0.1 | |
| request_method | 文本 | 客户端请求方法 | GET POST | 是 |
| remote_port | 整形 | 客户端请求端口 | 80 | 是 |
| request_length | 长整型 | 客户端请求字节数。单位：Byte | 111 | 是 |
| response_size | 长整型 | 源站回源字节数。单位：Byte | 1111 | 是 |
| response_time | 长整型 | 源站响应时间 | 0.02 | 是 |
| request_url | 文本 | 客户端请求路径 | /www | 是 |
| scheme | 关键字 | http类型 | http 或 https | 是 |
| servername | 文本 | 实际域名 | 1014wgr01.kktest.com.cn | |
| source_ip | 关键字 | 源站IP | 14.213.4.46 | 是 |
| source_port | 关键字 | 源站端口 | 8000 | 是 |
| status_code | 整型 | WAF响应HTTP状态码 | 200 | 是 |
| time | 文本 | 时间 | 2023-04-04 15:46:48 | 是 |
| time_local | 日期 | es记录创建时间 | 2023-04-04 15:46:48 | 是 |
| upstream_status | 整型 | 源站响应HTTP状态码 | 200 | 是 |
| upstream_response_length | 整型 | 源站响应大小 | 123 | 是 |
| upstream_response_time | 文本 | 源站响应处理时间。单位：秒 | 0.002 | 是 |
| user_agent | 文本 | 用户UA标识 | Mozilla/5.0 (...) | 是 |
"""

# ---------------------------------------------------------------------------
# Ping helper
# ---------------------------------------------------------------------------


async def _ping(target: str) -> str:
    """
    Ping a single IP or hostname using the OS ping command.

    Returns a short result string: "reachable (avg Xms)" or "unreachable".
    Runs ping in an executor to keep it non-blocking.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _ping_sync, target)


def _ping_sync(target: str) -> str:
    """Blocking ping; returns a short status string."""
    if sys.platform == "win32":
        cmd = ["ping", "-n", "3", "-w", "1000", target]
    else:
        cmd = ["ping", "-c", "3", "-W", "1", target]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Extract avg RTT line if present
            out = result.stdout
            for line in out.splitlines():
                low = line.lower()
                if "average" in low or "avg" in low or "平均" in low:
                    return f"reachable ({line.strip()})"
            return "reachable"
        return "unreachable"
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("ping failed for %s: %s", target, exc)
        return f"error: {type(exc).__name__}"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@tool
async def current_time() -> str:
    """Get the current date and time in Asia/Shanghai timezone (UTC+8).

    Use this tool whenever you need to know the current datetime, for example
    to build relative time windows or to stamp an investigation.

    Returns:
        Current datetime as a string in ISO-8601 format, e.g.
        "2026-04-24T15:30:00+08:00".
    """
    return datetime.now(_CST).isoformat(timespec="seconds")


@tool
async def check_connection_status(targets: list[str]) -> dict[str, str]:
    """Check network reachability for a list of IP addresses or hostnames via ICMP ping.

    Use when you need to confirm that CDN nodes, origin servers, or suspected
    attacker IPs are online and responding. Runs all pings concurrently.

    Args:
        targets: List of IP addresses or domain names to ping.
                 Example: ["103.248.152.176", "45.117.11.97", "example.com"]

    Returns:
        Dict mapping each target to a reachability string, e.g.
        {"103.248.152.176": "reachable (avg 12ms)", "1.2.3.4": "unreachable"}.
    """
    logger.info("check_connection_status: targets=%s", targets)
    results = await asyncio.gather(*(_ping(t) for t in targets))
    return dict(zip(targets, results))


@tool
async def get_gf_log_table_structure() -> str:
    """Return the ES field schema for GF (高防/GameShield) access logs.

    Use this tool when you need to know which fields are available in the
    Elasticsearch GF log index — for example, before writing a raw ES query
    or when the task asks about an unfamiliar field name.

    Returns:
        Markdown table listing all field names, types, descriptions, and example values.
    """
    return _GF_TABLE_STRUCT.strip()


@tool
async def get_waf_log_table_structure() -> str:
    """Return the ES field schema for WAF access logs.

    Use this tool when you need to know which fields are available in the
    Elasticsearch WAF log index — for example, before writing a raw ES query
    or when the task asks about a WAF-specific field name.

    Returns:
        Markdown table listing all field names, types, descriptions, and example values.
    """
    return _WAF_TABLE_STRUCT.strip()


# ---------------------------------------------------------------------------
# Module-level export
# ---------------------------------------------------------------------------

PUBLIC_TOOLS = [
    current_time,
    check_connection_status,
    get_gf_log_table_structure,
    get_waf_log_table_structure,
]
