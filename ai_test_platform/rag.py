from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Any
import re

from .models import Document


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


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

