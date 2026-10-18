"""Unit test — adapter factory lazy-init, client reuse, and aclose lifecycle."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from security.tools.es_tools import get_es_tools, aclose_es_adapters, _es_default_adapter
from security.tools.prom_tools import get_prom_tools, aclose_prom_adapters, _prom_default_adapter
from security.tools.security_tools import get_security_tools, aclose_security_adapters, _security_tools_cache
from security.rag.rag_tools import get_rag_tools, aclose_rag_engine, _rag_default_engine


def test_get_es_tools_caches_result():
    """Second call returns the same list (cached, not recreated)."""
    import security.tools.es_tools as es_mod
    es_mod._es_tools_cache = None

    first = get_es_tools()
    second = get_es_tools()
    assert first is second


def test_get_prom_tools_caches_result():
    import security.tools.prom_tools as prom_mod
    prom_mod._prom_tools_cache = None

    first = get_prom_tools()
    second = get_prom_tools()
    assert first is second


def test_get_security_tools_caches_result():
    import security.tools.security_tools as sec_mod
    sec_mod._security_tools_cache = None

    first = get_security_tools()
    second = get_security_tools()
    assert first is second


def test_get_rag_tools_caches_result():
    import security.rag.rag_tools as rag_mod
    rag_mod._rag_tools_cache = None

    first = get_rag_tools()
    second = get_rag_tools()
    assert first is second


@pytest.mark.asyncio
async def test_aclose_es_adapters_calls_aclose():
    """aclose_es_adapters() actually awaits the adapter's aclose() and resets to None."""
    import security.tools.es_tools as es_mod
    mock_adapter = MagicMock()
    mock_adapter.aclose = AsyncMock()
    es_mod._es_default_adapter = mock_adapter

    await aclose_es_adapters()
    mock_adapter.aclose.assert_called_once()
    assert es_mod._es_default_adapter is None

    # Second call is idempotent (no double await)
    await aclose_es_adapters()
    mock_adapter.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_aclose_prom_adapters_calls_aclose():
    import security.tools.prom_tools as prom_mod
    mock_adapter = MagicMock()
    mock_adapter.aclose = AsyncMock()
    prom_mod._prom_default_adapter = mock_adapter

    await aclose_prom_adapters()
    mock_adapter.aclose.assert_called_once()
    assert prom_mod._prom_default_adapter is None


@pytest.mark.asyncio
async def test_aclose_security_adapters_calls_aclose():
    import security.tools.security_tools as sec_mod
    mock_cc = MagicMock()
    mock_cc.aclose = AsyncMock()
    mock_ddos = MagicMock()
    mock_ddos.aclose = AsyncMock()
    sec_mod._sec_default_cc = mock_cc
    sec_mod._sec_default_ddos = mock_ddos
    sec_mod._sec_default_gf = None
    sec_mod._sec_default_waf = None
    sec_mod._sec_default_nr = None

    await aclose_security_adapters()
    mock_cc.aclose.assert_called_once()
    mock_ddos.aclose.assert_called_once()
    assert sec_mod._sec_default_cc is None
    assert sec_mod._sec_default_ddos is None


@pytest.mark.asyncio
async def test_aclose_rag_engine_calls_aclose():
    import security.rag.rag_tools as rag_mod
    mock_engine = MagicMock()
    mock_engine.aclose = AsyncMock()
    rag_mod._rag_default_engine = mock_engine

    await aclose_rag_engine()
    mock_engine.aclose.assert_called_once()
    assert rag_mod._rag_default_engine is None
