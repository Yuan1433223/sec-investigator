"""Async HTTP client factory — the single seam that enables DATA_SOURCE=fake.

Every adapter builds its ``httpx.AsyncClient`` through :func:`build_async_client`.
When ``settings.data_source == "fake"`` the client is given an ``httpx.MockTransport``
serving synthetic fixtures, so the adapter runs offline against realistic data.
When ``"real"`` it behaves exactly as before and reaches the configured endpoints.
"""

from __future__ import annotations

from typing import Any

import httpx

from runtime.config.settings import Settings
from security.fake.transport import FakeTransportHandler


def build_async_client(
    settings: Settings,
    *,
    verify: bool = True,
    timeout: float | int | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Return an AsyncClient, swapping in the fake transport when needed."""
    kwargs: dict[str, Any] = {"verify": verify}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if headers:
        kwargs["headers"] = headers

    if settings.data_source == "fake":
        kwargs["transport"] = httpx.MockTransport(FakeTransportHandler())

    return httpx.AsyncClient(**kwargs)
