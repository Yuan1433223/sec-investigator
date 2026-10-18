"""LangChain RAG tool — knowledge-base search for ops runbooks.

Adaptive multi-round strategy: tries progressively lower thresholds
until enough results are found or all rounds are exhausted.

All tools use the adapter-injection pattern:
  _make_rag_tools(engine) → list[BaseTool]

Module-level RAG_TOOLS constructs a real engine from settings.
Tests inject a mock engine via _make_rag_tools(mock_engine).
"""
from __future__ import annotations

from langchain_core.tools import tool

from security.rag.engine import RAGEngine

_SEARCH_ROUNDS = [
    {"threshold": 0.7, "top_k": 2},
    {"threshold": 0.55, "top_k": 3},
    {"threshold": 0.4, "top_k": 5},
]
_MAX_RESULTS = 5


def _make_rag_tools(engine: RAGEngine | None = None):
    """Return list of RAG LangChain tools with injected engine.

    When engine is None, a default RAGEngine is created at factory scope and
    stored in _rag_default_engine for session-exit cleanup.
    """
    global _rag_default_engine
    _engine = engine if engine is not None else RAGEngine()
    if engine is None:
        _rag_default_engine = _engine

    def _get_engine() -> RAGEngine:
        return _engine

    @tool
    def search_knowledge(query: str) -> str:
        """Search the ops knowledge base for runbooks and historical cases.

        Use when you need troubleshooting guidance, handling procedures,
        or historical incident references (e.g. "502 error", "CC attack",
        "high CPU usage").

        Uses adaptive multi-round search: starts at high similarity threshold
        and relaxes progressively until enough results are found.

        Args:
            query: Search keywords, e.g. "CC attack mitigation", "502 troubleshooting".

        Returns:
            Markdown-formatted document excerpts for the LLM to reason over,
            or a message indicating no results were found.
        """
        eng = _get_engine()
        all_results: list[dict] = []
        seen: set[str] = set()

        for rnd in _SEARCH_ROUNDS:
            try:
                results = eng.search(
                    query=query,
                    top_k=rnd["top_k"],
                    score_threshold=rnd["threshold"],
                )
            except Exception as exc:
                return f"Knowledge base query failed: {type(exc).__name__} — {exc}"

            for doc in results:
                if doc["text"] not in seen:
                    all_results.append(doc)
                    seen.add(doc["text"])

            if len(all_results) >= 2:
                break

        if not all_results:
            return "No relevant documents found after multi-round search."

        parts = []
        for doc in all_results[:_MAX_RESULTS]:
            parts.append(
                f"[Source: {doc['source']}] (score: {doc['score']:.2%})\n\n{doc['text']}"
            )
        return "\n\n---\n\n".join(parts)

    return [search_knowledge]


# Lazy-init factory: cached on first use.
_rag_tools_cache: list | None = None
_rag_default_engine: RAGEngine | None = None


def get_rag_tools() -> list:
    global _rag_tools_cache
    if _rag_tools_cache is None:
        _rag_tools_cache = _make_rag_tools()
    return _rag_tools_cache


async def aclose_rag_engine() -> None:
    """Close the default RAG engine. Idempotent."""
    global _rag_default_engine
    if _rag_default_engine is not None and hasattr(_rag_default_engine, "aclose"):
        await _rag_default_engine.aclose()
        _rag_default_engine = None
