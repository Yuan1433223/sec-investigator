"""Aggregated adapter lifecycle management.

Call `aclose_all_adapters()` on session exit to release all cached
default adapters created by the tool factories.
"""
from __future__ import annotations

from security.rag.rag_tools import aclose_rag_engine
from security.tools.es_tools import aclose_es_adapters
from security.tools.prom_tools import aclose_prom_adapters
from security.tools.security_tools import aclose_security_adapters


async def aclose_all_adapters() -> None:
    """Close all cached default adapters. Idempotent."""
    await aclose_es_adapters()
    await aclose_prom_adapters()
    await aclose_security_adapters()
    await aclose_rag_engine()
