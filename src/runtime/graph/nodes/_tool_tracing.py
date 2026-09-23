"""
Tool-tracing wrapper for worker node tool lists.

`make_traced_tools(tools, node_name)` wraps each LangChain tool so that
ToolCallEvent and ToolResultEvent are emitted via get_stream_writer() on
every invocation.

Usage in a worker node:

    from runtime.graph.nodes._tool_tracing import make_traced_tools

    traced = make_traced_tools(ES_TOOLS, "log_detective")
    agent = create_react_agent(model=llm, tools=traced, prompt=...)

Empty-result early-stop:
    When `max_empty` consecutive tool calls all return empty / zero-record
    results, the wrapper substitutes the raw result with a sentinel string:

        "[EARLY_STOP: N consecutive empty results ...]"

    The ReAct LLM sees this string and stops calling tools, preventing
    GraphRecursionError on targets with no ES data.

Implementation note:
- LangChain @tool functions are StructuredTool instances.
- We create thin wrapper tools that delegate to the original coroutine but
  bracket the call with event writes.
- get_stream_writer() is safe to call during node execution because LangGraph
  sets the context variable before entering a node.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.config import get_stream_writer

from runtime.events.protocol import ToolCallEvent, ToolResultEvent

_EARLY_STOP_TEMPLATE = (
    "[EARLY_STOP: {n} consecutive tool calls returned empty or zero results. "
    "Insufficient data for this target. Stop calling tools and summarize findings so far.]"
)


def _is_empty_collection(value: Any) -> bool | None:
    """Return emptiness for common collection/scalar result shapes, else None."""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return True
        try:
            return float(stripped) == 0
        except ValueError:
            return None
    return None


# Data-bearing keys checked for emptiness in dict results. A "no_data" style
# dict (e.g. {"status": "no_data", "points": []}) carries no actionable data,
# so it should count toward the early-stop budget, otherwise a flaky model can
# loop on such results until the recursion limit.
_DATA_KEYS = ("hits", "total", "count", "items", "results", "data", "points", "events", "nodes")
_NO_DATA_STATUS = {"no_data", "not_applicable", "unknown", "no data", "failed", "error", "empty"}


def _is_empty_result(result: Any) -> bool:
    """Return True when a tool result contains no actionable data."""
    if result is None:
        return True
    if isinstance(result, dict):
        # explicit error / no-data / failed markers
        err = result.get("error")
        if isinstance(err, str) and err.strip():
            return True
        status = result.get("status")
        if isinstance(status, str) and status.strip().lower() in _NO_DATA_STATUS:
            return True
        if result.get("success") is False:
            return True
        # any data-bearing key that is empty ⇒ whole result is empty
        for key in _DATA_KEYS:
            if key in result:
                empty = _is_empty_collection(result[key])
                if empty is not None:
                    return empty
        return not any(result.values())
    if isinstance(result, (list, tuple)):
        return len(result) == 0
    if isinstance(result, str):
        stripped = result.strip()
        return stripped in {"", "[]", "{}", "null", "none"}
    return False


def make_traced_tools(
    tools: list[BaseTool],
    node_name: str,
    *,
    max_empty: int = 3,
) -> list[BaseTool]:
    """
    Return a new list of tools whose invocations emit ToolCallEvent and
    ToolResultEvent on the current stream writer.

    All tools in the returned list share one empty-result counter per factory
    call (across all tool types for the same worker invocation).

    Args:
        tools: The original tool list to wrap.
        node_name: Used in event payloads to identify the emitting worker.
        max_empty: Consecutive empty-result threshold that triggers early-stop.
                   Set to 0 to disable. Tests should pass max_empty=0.
    """
    consecutive_empty: list[int] = [0]
    return [_traced(tool, node_name, consecutive_empty, max_empty) for tool in tools]


def _traced(
    original: BaseTool,
    node_name: str,
    consecutive_empty: list[int],
    max_empty: int,
) -> BaseTool:
    """Wrap a single BaseTool with before/after event emission."""
    orig_coroutine = original.coroutine  # the underlying async callable

    if orig_coroutine is None:
        # Sync-only tool — wrap _run instead (edge case; all current tools are async)
        return original

    tool_name = original.name

    async def _traced_coroutine(*args: Any, **kwargs: Any) -> Any:
        write = get_stream_writer()
        # Merge positional args into kwargs using the tool's arg_schema
        tool_input = _build_input_dict(original, args, kwargs)
        write(ToolCallEvent(node=node_name, tool_name=tool_name, tool_input=tool_input))
        try:
            result = await orig_coroutine(*args, **kwargs)
        except Exception as exc:
            write(
                ToolResultEvent(
                    node=node_name,
                    tool_name=tool_name,
                    output={"error": type(exc).__name__, "detail": str(exc)},
                )
            )
            raise

        # --- Empty-result early-stop ---
        if max_empty > 0:
            if _is_empty_result(result):
                consecutive_empty[0] += 1
            else:
                consecutive_empty[0] = 0

            if consecutive_empty[0] >= max_empty:
                result = _EARLY_STOP_TEMPLATE.format(n=consecutive_empty[0])

        write(ToolResultEvent(node=node_name, tool_name=tool_name, output=result))
        return result

    return StructuredTool(
        name=original.name,
        description=original.description,
        args_schema=original.args_schema,
        coroutine=_traced_coroutine,
        return_direct=original.return_direct,
    )


def _build_input_dict(tool: BaseTool, args: tuple, kwargs: dict) -> dict[str, Any]:
    """
    Best-effort: convert positional args + kwargs into a dict for the event payload.
    Falls back to {"args": args, "kwargs": kwargs} if schema lookup fails.
    """
    try:
        schema = tool.args_schema
        if schema is None:
            return dict(kwargs)
        field_names = list(schema.model_fields.keys())
        result = {}
        for i, val in enumerate(args):
            if i < len(field_names):
                result[field_names[i]] = val
        result.update(kwargs)
        return result
    except Exception:
        return {"args": list(args), "kwargs": kwargs}
