from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Any
import hashlib
import re

from .models import Document


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
EMBEDDING_DIMENSIONS = 64


def tokenize(text: str) -> list[str]:
    raw = [token.lower() for token in TOKEN_RE.findall(text)]
    tokens: list[str] = []
    for index, token in enumerate(raw):
        tokens.append(token)
        if len(token) == 1 and "\u4e00" <= token <= "\u9fff" and index + 1 < len(raw):
            nxt = raw[index + 1]
            if len(nxt) == 1 and "\u4e00" <= nxt <= "\u9fff":
                tokens.append(token + nxt)
    return tokens


def chunk_document(document: Document, max_chars: int = 900) -> list[dict[str, Any]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", document.content) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [document.content]:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            current = paragraph[:max_chars]
    if current:
        chunks.append(current)
    return [
        {
            "chunk_index": index,
            "content": content,
            "tokens": tokenize(" ".join([document.title, document.feature, document.screen, content])),
        }
        for index, content in enumerate(chunks)
    ]


def cosine_score(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    a = Counter(left)
    b = Counter(right)
    dot = sum(a[token] * b.get(token, 0) for token in a)
    mag_a = sqrt(sum(value * value for value in a.values()))
    mag_b = sqrt(sum(value * value for value in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def hash_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    magnitude = sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [round(value / magnitude, 6) for value in vector]


def vector_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(length))
    mag_left = sqrt(sum(value * value for value in left[:length]))
    mag_right = sqrt(sum(value * value for value in right[:length]))
    if mag_left == 0 or mag_right == 0:
        return 0.0
    return dot / (mag_left * mag_right)


class Retriever:
    def __init__(self, database: Any):
        self.database = database

    def search(
        self,
        query: str,
        feature: str = "",
        screen: str = "",
        source_types: list[str] | None = None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        if hasattr(self.database, "search_rag_nodes"):
            rag_results = self.database.search_rag_nodes(
                query=query,
                feature=feature,
                screen=screen,
                source_types=source_types,
                limit=limit,
            )
            if rag_results:
                return [self._rag_result_to_context(item) for item in rag_results]
        query_tokens = tokenize(" ".join([query, feature, screen]))
        source_types = source_types or []
        candidates: list[dict[str, Any]] = []
        for chunk in self.database.list_chunks():
            if source_types and chunk["source_type"] not in source_types:
                continue
            metadata_score = 0.0
            if feature and feature.lower() == str(chunk["feature"]).lower():
                metadata_score += 0.25
            if screen and screen.lower() == str(chunk["screen"]).lower():
                metadata_score += 0.15
            similarity = cosine_score(query_tokens, chunk["tokens"])
            score = similarity + metadata_score
            if score > 0:
                candidates.append(
                    {
                        "document_id": chunk["document_id"],
                        "chunk_id": chunk["id"],
                        "content": chunk["content"],
                        "feature": chunk["feature"],
                        "screen": chunk["screen"],
                        "source_type": chunk["source_type"],
                        "score": round(score, 4),
                    }
                )
        return sorted(candidates, key=lambda item: item["score"], reverse=True)[:limit]

    def _rag_result_to_context(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata", {})
        context = {
            "rag_node_id": item.get("rag_node_id"),
            "source_table": item.get("source_table"),
            "source_id": item.get("source_id"),
            "source_type": item.get("source_type") or item.get("node_kind"),
            "node_kind": item.get("node_kind"),
            "document_id": metadata.get("document_id"),
            "chunk_id": metadata.get("chunk_id"),
            "source_model_id": metadata.get("source_model_id"),
            "test_case_id": metadata.get("test_case_id"),
            "content": item.get("content", ""),
            "feature": item.get("feature", ""),
            "screen": item.get("screen", ""),
            "score": item.get("score", 0),
            "retrieval": item.get("retrieval", {}),
        }
        if context["source_table"] == "documents" and context["document_id"] is None:
            context["document_id"] = context["source_id"]
        if context["chunk_id"] is None:
            context["chunk_id"] = context["rag_node_id"]
        return context
