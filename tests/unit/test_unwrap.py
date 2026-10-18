"""Unit tests for _unwrap (subgraph namespace extraction)."""
from __future__ import annotations

from surfaces.api.investigation import _unwrap


def test_unwrap_bare_event():
    """Bare event (no subgraphs) → empty namespace."""
    result = _unwrap({"kind": "status"})
    assert result == ([], {"kind": "status"})


def test_unwrap_tuple_event():
    """Tuple (namespace, event) with subgraphs=True → extracted namespace."""
    result = _unwrap((("log_detective:1234",), {"kind": "tool_call"}))
    assert result == (["log_detective:1234"], {"kind": "tool_call"})


def test_unwrap_tuple_empty_namespace():
    """Tuple with empty namespace → empty list."""
    result = _unwrap(((), {"kind": "status"}))
    assert result == ([], {"kind": "status"})


def test_unwrap_tuple_multi_level_namespace():
    """Multi-level namespace tuple → list of strings."""
    result = _unwrap((("root", "log_detective:abc"), {"kind": "tool_call"}))
    assert result == (["root", "log_detective:abc"], {"kind": "tool_call"})
