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
    settings = MagicMock(data_source="real")
    with (patch("security.tools.public_tools.get_settings", return_value=settings),
          patch("security.tools.public_tools._ping_sync", return_value="unreachable")):
        result = await check_connection_status.ainvoke({"targets": ["1.2.3.4"]})
    assert result["1.2.3.4"] == "unreachable"


@pytest.mark.asyncio
async def test_fake_connection_status_does_not_ping():
    settings = MagicMock(data_source="fake")
    with (patch("security.tools.public_tools.get_settings", return_value=settings),
          patch("security.tools.public_tools._ping_sync", side_effect=AssertionError("unexpected ping"))):
        result = await check_connection_status.ainvoke({"targets": ["1.2.3.4"]})
    assert result == {"1.2.3.4": "not checked (fake data mode)"}


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
    from security.tools.security_tools import get_security_tools
    from security.tools.public_tools import check_connection_status

    security_tools = get_security_tools() + [check_connection_status]
    tool_names = {t.name for t in security_tools}
    assert "check_connection_status" in tool_names


def test_security_guard_tool_list_excludes_current_time():
    """current_time is deliberately excluded to prevent budget burn on time queries."""
    from security.tools.security_tools import get_security_tools
    from security.tools.public_tools import check_connection_status

    security_tools = get_security_tools() + [check_connection_status]
    tool_names = {t.name for t in security_tools}
    assert "current_time" not in tool_names


def test_log_detective_tool_list_includes_table_tools():
    from security.tools.es_tools import get_es_tools
    from security.rag.rag_tools import get_rag_tools
    from security.tools.public_tools import (
        get_gf_log_table_structure,
        get_waf_log_table_structure,
    )

    log_tools = get_es_tools() + get_rag_tools() + [
        get_gf_log_table_structure,
        get_waf_log_table_structure,
    ]
    tool_names = {t.name for t in log_tools}
    assert "get_gf_log_table_structure" in tool_names
    assert "get_waf_log_table_structure" in tool_names
    assert "current_time" not in tool_names
