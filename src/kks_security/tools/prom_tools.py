"""
Prometheus LangChain tools for the machine_check worker.

Each @tool:
1. Builds a PromQL expression (pure string formatting)
2. Executes it via PrometheusAdapter (async, injectable for tests)
3. Returns a JSON-serialisable dict

Time parameters are ISO strings ("YYYY-MM-DD HH:MM:SS") to match the
pattern established in the ES tools.

Migrated from KKShieldHelper-main/agents/tools/prometheus.py with:
- No global client singleton — adapter injected via _make_prom_tools()
- Time strings converted to timestamps inside the tool (not the client)
- Peak-value extraction delegated to adapter._peak_value helper
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.tools import tool

from kks_security.adapters.prometheus import PrometheusAdapter, _peak_value


def _ts(time_str: str) -> int:
    return int(datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").timestamp())


def _make_prom_tools(adapter: PrometheusAdapter | None = None):
    """
    Factory returning a list of Prometheus tools bound to an adapter.

    If adapter is None the first tool call lazily creates one PrometheusAdapter
    and caches it in closure scope — subsequent calls reuse the same httpx client.
    Pass a mock adapter in tests to avoid real HTTP calls.
    """
    _cached: PrometheusAdapter | None = adapter

    async def _get() -> PrometheusAdapter:
        nonlocal _cached
        if _cached is None:
            _cached = PrometheusAdapter()
        return _cached

    @tool
    async def query_instance_uname(instance: str) -> dict[str, Any]:
        """Query OS / hardware info for an instance (hostname, kernel, arch)."""
        prom = await _get()
        inst = prom.instance(instance)
        results = await prom.instant(f'node_uname_info{{instance="{inst}"}}')
        if not results:
            return {"system": {}}
        m = results[0]["metric"]
        return {
            "system": {
                "instance": m.get("instance", ""),
                "nodename": m.get("nodename", ""),
                "sysname": m.get("sysname", ""),
                "machine": m.get("machine", ""),
                "release": m.get("release", ""),
            }
        }

    @tool
    async def query_instance_cpu(
        instance: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """Query peak CPU usage percentage for an instance over a time range."""
        prom = await _get()
        inst = prom.instance(instance)
        step_hint = max(60, (_ts(end_time) - _ts(start_time)) // 60)
        promql = (
            f'100 * (1 - avg(rate(node_cpu_seconds_total{{mode="idle",'
            f'instance="{inst}"}}[{step_hint}s])) by (instance))'
        )
        results = await prom.range_query(promql, _ts(start_time), _ts(end_time))
        peak = _peak_value(results)
        return {"cpu_usage": f"{round(peak, 2)}%" if peak is not None else "no data"}

    @tool
    async def query_instance_memory(
        instance: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """Query peak memory usage percentage for an instance over a time range."""
        prom = await _get()
        inst = prom.instance(instance)
        promql = (
            f"(1 - (node_memory_MemAvailable_bytes{{instance=\"{inst}\"}} "
            f"/ node_memory_MemTotal_bytes{{instance=\"{inst}\"}})) * 100"
        )
        results = await prom.range_query(promql, _ts(start_time), _ts(end_time))
        peak = _peak_value(results)
        return {"memory_usage": f"{round(peak, 2)}%" if peak is not None else "no data"}

    @tool
    async def query_instance_tcp(
        instance: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """Query peak established TCP connection count for an instance."""
        prom = await _get()
        inst = prom.instance(instance)
        promql = f'node_netstat_Tcp_CurrEstab{{instance="{inst}"}}'
        results = await prom.range_query(promql, _ts(start_time), _ts(end_time))
        peak = _peak_value(results)
        return {"tcp_established": int(round(peak)) if peak is not None else None}

    @tool
    async def query_instance_bandwidth(
        instance: str, start_time: str, end_time: str, device: str = "eth0"
    ) -> dict[str, Any]:
        """
        Query peak network bandwidth (Mbps) for an instance.
        Returns rx_mbps and tx_mbps.
        """
        prom = await _get()
        inst = prom.instance(instance)
        step_hint = max(60, (_ts(end_time) - _ts(start_time)) // 60)
        rx_q = (
            f'irate(node_network_receive_bytes_total{{instance="{inst}",'
            f'device="{device}"}}[{step_hint}s]) * 8 / 1_000_000'
        )
        tx_q = (
            f'irate(node_network_transmit_bytes_total{{instance="{inst}",'
            f'device="{device}"}}[{step_hint}s]) * 8 / 1_000_000'
        )
        rx_r, tx_r = await _gather(
            prom.range_query(rx_q, _ts(start_time), _ts(end_time)),
            prom.range_query(tx_q, _ts(start_time), _ts(end_time)),
        )
        rx = _peak_value(rx_r)
        tx = _peak_value(tx_r)
        return {
            "rx_mbps": round(rx, 2) if rx is not None else None,
            "tx_mbps": round(tx, 2) if tx is not None else None,
        }

    @tool
    async def query_instance_status(
        instance: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """
        Composite query: CPU, memory, TCP connections and bandwidth in one call.
        Use this as the primary machine health check tool.
        """
        prom = await _get()
        inst = prom.instance(instance)
        start, end = _ts(start_time), _ts(end_time)
        step_hint = max(60, (end - start) // 60)

        cpu_q = (
            f'100 * (1 - avg(rate(node_cpu_seconds_total{{mode="idle",'
            f'instance="{inst}"}}[{step_hint}s])) by (instance))'
        )
        mem_q = (
            f"(1 - (node_memory_MemAvailable_bytes{{instance=\"{inst}\"}} "
            f"/ node_memory_MemTotal_bytes{{instance=\"{inst}\"}})) * 100"
        )
        tcp_q = f'node_netstat_Tcp_CurrEstab{{instance="{inst}"}}'

        cpu_r, mem_r, tcp_r = await _gather(
            prom.range_query(cpu_q, start, end),
            prom.range_query(mem_q, start, end),
            prom.range_query(tcp_q, start, end),
        )
        cpu = _peak_value(cpu_r)
        mem = _peak_value(mem_r)
        tcp = _peak_value(tcp_r)

        return {
            "instance": instance,
            "cpu_usage": f"{round(cpu, 2)}%" if cpu is not None else "no data",
            "memory_usage": f"{round(mem, 2)}%" if mem is not None else "no data",
            "tcp_established": int(round(tcp)) if tcp is not None else None,
        }

    @tool
    async def query_instance_disk(
        instance: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """
        Query peak disk I/O rates (MB/s read and write) for each device on an instance.

        Note: IP-only or IP:port instances only — domain names are not supported.

        Args:
            instance: Server instance, e.g. "117.24.6.116" or "117.24.6.116:64998".
            start_time: Start time, format YYYY-MM-DD HH:MM:SS.
            end_time: End time, format YYYY-MM-DD HH:MM:SS.

        Returns:
            {"disk_io": {"sda": {"read_mbps": float, "write_mbps": float}, ...}}
        """
        prom = await _get()
        inst = prom.instance(instance)
        start, end = _ts(start_time), _ts(end_time)
        step_hint = max(60, (end - start) // 60)
        read_q = (
            f'irate(node_disk_read_bytes_total{{instance="{inst}"}}[{step_hint}s])'
            f" / 1_000_000"
        )
        write_q = (
            f'irate(node_disk_written_bytes_total{{instance="{inst}"}}[{step_hint}s])'
            f" / 1_000_000"
        )
        read_r, write_r = await _gather(
            prom.range_query(read_q, start, end),
            prom.range_query(write_q, start, end),
        )

        def _by_device(results: list[dict[str, Any]]) -> dict[str, float | None]:
            out: dict[str, float | None] = {}
            for item in results:
                device = item.get("metric", {}).get("device", "unknown")
                out[device] = _peak_value([item])
            return out

        reads = _by_device(read_r)
        writes = _by_device(write_r)
        devices = sorted(set(reads) | set(writes))
        disk_io = {
            dev: {
                "read_mbps": round(reads.get(dev), 4) if reads.get(dev) is not None else None,
                "write_mbps": round(writes.get(dev), 4) if writes.get(dev) is not None else None,
            }
            for dev in devices
        }
        return {"disk_io": disk_io}

    @tool
    async def query_instance_socket(
        instance: str, start_time: str, end_time: str
    ) -> dict[str, Any]:
        """
        Query peak socket (file descriptor) count in use for an instance.

        Note: IP-only or IP:port instances only — domain names are not supported.

        Args:
            instance: Server instance, e.g. "117.24.6.116" or "117.24.6.116:64998".
            start_time: Start time, format YYYY-MM-DD HH:MM:SS.
            end_time: End time, format YYYY-MM-DD HH:MM:SS.

        Returns:
            {"sockets_used": int | None}
        """
        prom = await _get()
        inst = prom.instance(instance)
        promql = f'node_sockstat_sockets_used{{instance="{inst}"}}'
        results = await prom.range_query(promql, _ts(start_time), _ts(end_time))
        peak = _peak_value(results)
        return {"sockets_used": int(round(peak)) if peak is not None else None}

    return [
        query_instance_uname,
        query_instance_cpu,
        query_instance_memory,
        query_instance_tcp,
        query_instance_bandwidth,
        query_instance_status,
        query_instance_disk,
        query_instance_socket,
    ]


async def _gather(*coros: Any) -> tuple[Any, ...]:
    import asyncio
    return tuple(await asyncio.gather(*coros))


# Default tool list (no injected adapter — uses PrometheusAdapter from settings)
PROM_TOOLS = _make_prom_tools()
