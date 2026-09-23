"""FastGPT RAG search engine — Milvus (vector) + MongoDB (document store).

Migrated from KKShieldHelper-main/utils/fastgpt_rag/search_engine.py with:
- os.getenv() → injected Settings
- sync pymilvus/pymongo → kept sync (pymilvus has no async client)
- module-level singleton → per-instance lazy _connect()
- no import-time I/O
"""
from __future__ import annotations

from typing import Any

import numpy as np
from bson import ObjectId
from openai import OpenAI
from pymilvus import Collection, connections
from pymongo import MongoClient

from kks_runtime.config.settings import Settings, get_settings

_MILVUS_ALIAS = "kks_rag"
_MILVUS_COLLECTION = "modeldata"
_MILVUS_DB = "fastgpt"
_MONGO_DB = "fastgpt"


class RAGEngine:
    """Lazy-connecting FastGPT RAG engine.

    Connects to Milvus and MongoDB on first ``search()`` call.
    All config comes from injected Settings — no os.getenv() calls.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._milvus_host = s.milvus_host
        self._milvus_port = s.milvus_port
        self._milvus_user = s.milvus_user
        self._milvus_password = s.milvus_password
        self._mongo_host = s.mongodb_host
        self._mongo_port = s.mongodb_port
        self._mongo_user = s.mongodb_user
        self._mongo_password = s.mongodb_password
        self._embedding_model = s.rag_embedding_model
        self._embedding_dimensions = s.rag_embedding_dimensions
        self._openai_api_key = s.openai_api_key
        self._openai_base_url = s.openai_api_base

        self._initialized = False
        self._collection: Collection | None = None
        self._mongo_db = None
        self._embedder: OpenAI | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        team_id: str | list[str] | None = None,
        dataset_id: str | list[str] | None = None,
        top_k: int = 5,
        score_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Vector search returning ranked document dicts.

        Each result: ``{"text": str, "source": str, "score": float}``
        """
        self._connect()

        query_vec = self._embed(query)
        expr = self._build_filter(team_id, dataset_id)

        hits = self._collection.search(  # type: ignore[union-attr]
            data=[query_vec],
            anns_field="vector",
            param={"metric_type": "IP", "params": {"nprobe": 50}},
            limit=top_k * 2,
            expr=expr,
            output_fields=["id", "teamId", "datasetId", "collectionId"],
        )

        candidates = []
        for batch in hits:
            for h in batch:
                if h.score > score_threshold:
                    candidates.append(
                        {
                            "id": h.entity.get("id"),
                            "teamId": h.entity.get("teamId"),
                            "datasetId": h.entity.get("datasetId"),
                            "collectionId": h.entity.get("collectionId"),
                            "score": float(h.score),
                        }
                    )

        if not candidates:
            return []

        return self._fetch_documents(candidates)[:top_k]

    def close(self) -> None:
        if self._mongo_db is not None:
            self._mongo_db.client.close()
        try:
            connections.disconnect(_MILVUS_ALIAS)
        except Exception:
            pass
        self._initialized = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        if self._initialized:
            return

        connections.connect(
            alias=_MILVUS_ALIAS,
            host=self._milvus_host,
            port=str(self._milvus_port),
            user=self._milvus_user,
            password=self._milvus_password,
            db_name=_MILVUS_DB,
        )
        self._collection = Collection(name=_MILVUS_COLLECTION, using=_MILVUS_ALIAS)
        try:
            self._collection.load()
        except Exception:
            pass  # already loaded or no index yet

        mongo_client = MongoClient(
            host=self._mongo_host,
            port=self._mongo_port,
            username=self._mongo_user or None,
            password=self._mongo_password or None,
            directConnection=True,
            serverSelectionTimeoutMS=5000,
        )
        self._mongo_db = mongo_client[_MONGO_DB]

        self._embedder = OpenAI(
            api_key=self._openai_api_key,
            base_url=self._openai_base_url,
        )
        self._initialized = True

    def _embed(self, text: str) -> list[float]:
        resp = self._embedder.embeddings.create(  # type: ignore[union-attr]
            model=self._embedding_model,
            input=text,
            encoding_format="float",
            dimensions=self._embedding_dimensions,
        )
        return np.array(resp.data[0].embedding).tolist()

    @staticmethod
    def _build_filter(
        team_id: str | list[str] | None,
        dataset_id: str | list[str] | None,
    ) -> str | None:
        parts: list[str] = []
        if team_id:
            if isinstance(team_id, list):
                ids = ", ".join(f'"{t}"' for t in team_id)
                parts.append(f"teamId in [{ids}]")
            else:
                parts.append(f'teamId == "{team_id}"')
        if dataset_id:
            if isinstance(dataset_id, list):
                ids = ", ".join(f'"{d}"' for d in dataset_id)
                parts.append(f"datasetId in [{ids}]")
            else:
                parts.append(f'datasetId == "{dataset_id}"')
        return " && ".join(parts) if parts else None

    def _fetch_documents(self, candidates: list[dict]) -> list[dict[str, Any]]:
        score_map = {str(r["id"]): r["score"] for r in candidates}
        collection_ids = {ObjectId(r["collectionId"]) for r in candidates}

        # Resolve collection names (document source labels)
        name_map: dict[str, str] = {}
        for item in self._mongo_db["dataset_collections"].find(
            {"_id": {"$in": list(collection_ids)}}, {"name": 1}
        ):
            name_map[str(item["_id"])] = item["name"]

        # Build $or query for dataset_datas
        query_args = [
            {
                "teamId": ObjectId(r["teamId"]),
                "datasetId": ObjectId(r["datasetId"]),
                "collectionId": ObjectId(r["collectionId"]),
                "indexes": {"$elemMatch": {"dataId": str(r["id"])}},
            }
            for r in candidates
        ]

        documents: list[dict[str, Any]] = []
        for doc in self._mongo_db["dataset_datas"].find({"$or": query_args}):
            for index in doc.get("indexes", []):
                data_id = index.get("dataId")
                if data_id not in score_map:
                    continue
                text = self._extract_text(doc, index)
                if text and len(text) >= 10:
                    source = name_map.get(str(doc.get("collectionId", "")), "unknown")
                    documents.append({"text": text, "source": source, "score": score_map[data_id]})
                break  # one index per doc is enough

        documents.sort(key=lambda x: x["score"], reverse=True)
        return documents

    @staticmethod
    def _extract_text(doc: dict, index: dict) -> str:
        """Extract best available text from a dataset_datas document."""
        q = doc.get("q", "").strip()
        a = doc.get("a", "").strip()
        if q and a:
            return f"**{q}**\n\n{a}"
        if a:
            return a
        if q:
            return q
        text = index.get("text", "").strip()
        if len(text) >= 20:
            return text
        return doc.get("content", doc.get("raw", "")).strip()
