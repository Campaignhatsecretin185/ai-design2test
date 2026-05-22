from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@dataclass
class Document:
    id: int | None
    title: str
    source_type: str
    content: str
    feature: str = ""
    screen: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)


@dataclass
class TestStep:
    action: str
    target: dict[str, Any] = field(default_factory=dict)
    value: str = ""
    note: str = ""


@dataclass
class TestAssertion:
    type: str
    target: dict[str, Any] = field(default_factory=dict)
    expected: str = ""


@dataclass
class TestCase:
    id: int | None
    title: str
    feature: str
    priority: str
    platforms: list[str]
    tags: list[str]
    preconditions: list[str]
    steps: list[TestStep]
    assertions: list[TestAssertion]
    source_refs: list[dict[str, Any]]
    status: str = "ai_generated"
    version: int = 1
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "feature": self.feature,
            "priority": self.priority,
            "platforms": self.platforms,
            "tags": self.tags,
            "preconditions": self.preconditions,
            "steps": [step.__dict__ for step in self.steps],
            "assertions": [assertion.__dict__ for assertion in self.assertions],
            "source_refs": self.source_refs,
            "status": self.status,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> "TestCase":
        return cls(
            id=row["id"],
            title=row["title"],
            feature=row["feature"],
            priority=row["priority"],
            platforms=loads(row["platforms"], []),
            tags=loads(row["tags"], []),
            preconditions=loads(row["preconditions"], []),
            steps=[TestStep(**item) for item in loads(row["steps"], [])],
            assertions=[TestAssertion(**item) for item in loads(row["assertions"], [])],
            source_refs=loads(row["source_refs"], []),
            status=row["status"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

