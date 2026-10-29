"""Factory-owned, lazy tool resources; no process-wide clients or tool caches."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Protocol, TypeVar

from langchain_core.tools import BaseTool


class AsyncCloseable(Protocol):
    async def aclose(self) -> None: ...


T = TypeVar("T", bound=AsyncCloseable)


class ToolBundle(list[BaseTool]):
    """A tool list whose default resources live only as long as its context.

    Resource getters cache clients in closures on first use. Injected resources
    stay caller-owned. ExitStack closes every owned resource, including when a
    tool/agent raises or its task is cancelled.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stack = AsyncExitStack()
        self._closed = False

    def resource(self, factory: Callable[[], T], supplied: T | None = None) -> Callable[[], T]:
        cached = supplied

        def get() -> T:
            nonlocal cached
            if self._closed:
                raise RuntimeError("Tool bundle is closed")
            if cached is None:
                cached = factory()
                self._stack.push_async_callback(cached.aclose)
            return cached

        return get

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await self._stack.aclose()

    async def __aenter__(self) -> ToolBundle:
        if self._closed:
            raise RuntimeError("Tool bundle is closed")
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
