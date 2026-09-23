"""Unit tests for public_tools (current_time, check_connection_status, table structures)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from security.tools.public_tools import (
    _GF_TABLE_STRUCT,
    _WAF_TABLE_STRUCT,
    PUBLIC_TOOLS,
    _ping_sync,
    check_connection_status,
    current_time,
    get_gf_log_table_structure,
    get_waf_log_table_structure,
)

_CST = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# current_time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_current_time_returns_iso_string():
    result = await current_time.ainvoke({})
    # Should be parseable as ISO-8601 with UTC+8 offset
    dt = datetime.fromisoformat(result)
    assert dt.utcoffset() is not None


@pytest.mark.asyncio
async def test_current_time_is_cst():
    result = await current_time.ainvoke({})
    dt = datetime.fromisoformat(result)
    assert dt.utcoffset() == timedelta(hours=8)


@pytest.mark.asyncio
async def test_current_time_is_recent():
    result = await current_time.ainvoke({})
    dt = datetime.fromisoformat(result).astimezone(UTC)
    now_utc = datetime.now(UTC)
    diff = abs((now_utc - dt).total_seconds())
    assert diff < 5, f"current_time too far from now: {diff}s"


# ---------------------------------------------------------------------------
# check_connection_status — unit tests via _ping_sync mock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_connection_status_returns_dict_keyed_by_target():
    with patch("security.tools.public_tools._ping_sync", return_value="reachable"):
        result = await check_connection_status.ainvoke({"targets": ["1.2.3.4", "5.6.7.8"]})
    assert set(result.keys()) == {"1.2.3.4", "5.6.7.8"}


@pytest.mark.asyncio
async def test_check_connection_status_maps_values():
    with patch("security.tools.public_tools._ping_sync", return_value="unreachable"):
        result = await check_connection_status.ainvoke({"targets": ["1.2.3.4"]})
    assert result["1.2.3.4"] == "unreachable"


@pytest.mark.asyncio
async def test_check_connection_status_empty_list():
    result = await check_connection_status.ainvoke({"targets": []})
    assert result == {}


# ---------------------------------------------------------------------------
# _ping_sync — unit tests (no actual network)
# ---------------------------------------------------------------------------


def test_ping_sync_success(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Minimum = 5ms, Maximum = 10ms, Average = 7ms"
    monkeypatch.setattr(
        "security.tools.public_tools.subprocess.run", lambda *a, **kw: mock_result
    )
    out = _ping_sync("1.2.3.4")
    assert "reachable" in out


def test_ping_sync_failure(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    monkeypatch.setattr(
        "security.tools.public_tools.subprocess.run", lambda *a, **kw: mock_result
    )
    out = _ping_sync("1.2.3.4")
    assert out == "unreachable"


def test_ping_sync_timeout(monkeypatch):
    import subprocess
    monkeypatch.setattr(
        "security.tools.public_tools.subprocess.run",
        lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="ping", timeout=10)),
    )
    out = _ping_sync("1.2.3.4")
    assert "error" in out


# ---------------------------------------------------------------------------
# Table structure tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_gf_log_table_structure_returns_markdown():
    result = await get_gf_log_table_structure.ainvoke({})
    assert "remote_addr" in result
    assert "status" in result
    assert "|" in result  # markdown table


@pytest.mark.asyncio
async def test_get_waf_log_table_structure_returns_markdown():
    result = await get_waf_log_table_structure.ainvoke({})
    assert "status_code" in result
    assert "event_type" in result
    assert "|" in result  # markdown table


@pytest.mark.asyncio
async def test_gf_table_matches_constant():
    result = await get_gf_log_table_structure.ainvoke({})
    assert result == _GF_TABLE_STRUCT.strip()


@pytest.mark.asyncio
async def test_waf_table_matches_constant():
    result = await get_waf_log_table_structure.ainvoke({})
    assert result == _WAF_TABLE_STRUCT.strip()


# ---------------------------------------------------------------------------
# PUBLIC_TOOLS list
# ---------------------------------------------------------------------------


def test_public_tools_exported():
    tool_names = {t.name for t in PUBLIC_TOOLS}
    assert "current_time" in tool_names
    assert "check_connection_status" in tool_names
    assert "get_gf_log_table_structure" in tool_names
    assert "get_waf_log_table_structure" in tool_names


def test_public_tools_has_four_tools():
    assert len(PUBLIC_TOOLS) == 4


# ---------------------------------------------------------------------------
# Worker node tool composition: security_guard includes check_connection_status
# ---------------------------------------------------------------------------


def test_security_guard_tool_list_includes_check_connection_status():
    from runtime.graph.nodes.security_guard import _SECURITY_TOOLS

    tool_names = {t.name for t in _SECURITY_TOOLS}
    assert "check_connection_status" in tool_names


def test_security_guard_tool_list_includes_current_time():
    from runtime.graph.nodes.security_guard import _SECURITY_TOOLS

    tool_names = {t.name for t in _SECURITY_TOOLS}
    assert "current_time" in tool_names


def test_log_detective_tool_list_includes_table_tools():
    from runtime.graph.nodes.log_detective import _LOG_TOOLS

    tool_names = {t.name for t in _LOG_TOOLS}
    assert "get_gf_log_table_structure" in tool_names
    assert "get_waf_log_table_structure" in tool_names
    assert "current_time" in tool_names
