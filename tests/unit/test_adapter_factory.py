"""Real resource contracts: lazy ownership, isolation, and cleanup on failure."""
from unittest.mock import AsyncMock

import pytest

from runtime.config.settings import Settings
from security.adapters.es import ESAdapter
from security.adapters.lifecycle import ToolBundle
from security.adapters.prometheus import PrometheusAdapter
from security.rag.engine import RAGEngine
from security.rag.rag_tools import get_rag_tools
from security.tools.es_tools import get_es_tools
from security.tools.prom_tools import get_prom_tools
from security.tools.security_tools import get_security_tools


@pytest.mark.parametrize("factory", [get_es_tools, get_prom_tools, get_security_tools, get_rag_tools])
def test_factories_do_not_share_tool_bundles(factory):
    first, second = factory(), factory()
    assert first is not second
    assert [tool.name for tool in first] == [tool.name for tool in second]


@pytest.mark.asyncio
async def test_default_es_is_lazy_reused_and_closed_with_real_interface(monkeypatch):
    import security.tools.es_tools as module
    created = []

    def build():
        adapter = ESAdapter(Settings(_env_file=None, data_source="fake"))
        created.append(adapter)
        return adapter

    monkeypatch.setattr(module, "ESAdapter", build)
    bundle = get_es_tools()
    assert not created
    async with bundle:
        tool = next(tool for tool in bundle if tool.name == "query_status_code_distribution")
        args = {"query_by": "domain", "value": "api2.xs2027.cn",
                "start_time": "2026-04-18 12:18:00", "end_time": "2026-04-18 12:36:00"}
        assert (await tool.ainvoke(args))["current"]
        await tool.ainvoke(args)
        assert len(created) == 1
        assert not created[0]._client.is_closed
    assert created[0]._client.is_closed
    await bundle.aclose()


@pytest.mark.asyncio
async def test_closing_one_bundle_does_not_close_another(monkeypatch):
    import security.tools.prom_tools as module
    created = []

    def build():
        adapter = PrometheusAdapter(Settings(_env_file=None, data_source="fake"))
        created.append(adapter)
        return adapter

    monkeypatch.setattr(module, "PrometheusAdapter", build)
    first, second = get_prom_tools(), get_prom_tools()
    async with first, second:
        first_tool = next(tool for tool in first if tool.name == "query_instance_uname")
        second_tool = next(tool for tool in second if tool.name == "query_instance_uname")
        await first_tool.ainvoke({"instance": "118.178.13.52"})
        await second_tool.ainvoke({"instance": "118.178.13.52"})
        await first.aclose()
        assert created[0]._client.is_closed
        assert not created[1]._client.is_closed
        await second_tool.ainvoke({"instance": "118.178.13.52"})
    assert created[1]._client.is_closed


@pytest.mark.asyncio
async def test_exception_unwinds_all_owned_resources():
    class Resource:
        aclose = AsyncMock()

    first, second = Resource(), Resource()
    first.aclose, second.aclose = AsyncMock(), AsyncMock()
    bundle = ToolBundle()
    with pytest.raises(ValueError, match="agent failed"):
        async with bundle:
            bundle.resource(lambda: first)()
            bundle.resource(lambda: second)()
            raise ValueError("agent failed")
    first.aclose.assert_awaited_once()
    second.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_supplied_adapter_stays_caller_owned():
    adapter = ESAdapter(Settings(_env_file=None, data_source="fake"))
    async with ToolBundle() as bundle:
        assert bundle.resource(ESAdapter, adapter)() is adapter
    assert not adapter._client.is_closed
    await adapter.aclose()
    assert adapter._client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_type", [ESAdapter, PrometheusAdapter, RAGEngine])
async def test_real_adapters_implement_aclose(adapter_type):
    adapter = adapter_type(Settings(_env_file=None, data_source="fake"))
    await adapter.aclose()


@pytest.mark.asyncio
async def test_unused_bundle_never_constructs_resource():
    def forbidden():
        raise AssertionError("unused adapter must not be created")

    async with ToolBundle() as bundle:
        get = bundle.resource(forbidden)
    with pytest.raises(RuntimeError, match="closed"):
        get()
