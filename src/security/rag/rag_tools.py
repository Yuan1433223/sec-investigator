"""LangChain RAG tool — knowledge-base search for ops runbooks.

Adaptive multi-round strategy: tries progressively lower thresholds
until enough results are found or all rounds are exhausted.

All tools use the adapter-injection pattern:
  _make_rag_tools(engine) → list[BaseTool]

Each bundle lazily owns a default engine. Tests can inject a caller-owned engine.
"""
from __future__ import annotations

from langchain_core.tools import tool

from security.rag.engine import RAGEngine
from security.adapters.lifecycle import ToolBundle

_SEARCH_ROUNDS = [
    {"threshold": 0.7, "top_k": 2},
    {"threshold": 0.55, "top_k": 3},
    {"threshold": 0.4, "top_k": 5},
]
_MAX_RESULTS = 5


def _make_rag_tools(engine: RAGEngine | None = None):
    """Return list of RAG LangChain tools with injected engine.

    A default engine is lazy, cached for this bundle, and closed on exit.
    """
    bundle = ToolBundle()
    _get_engine = bundle.resource(RAGEngine, engine)

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

    bundle.extend([search_knowledge])
    return bundle


def get_rag_tools() -> ToolBundle:
    """Return a fresh factory scope; use as an async context manager."""
    return _make_rag_tools()
