from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib import request, error
import base64
import json
import os


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


TEST_CASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cases"],
    "properties": {
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "feature",
                    "priority",
                    "platforms",
                    "tags",
                    "preconditions",
                    "steps",
                    "assertions",
                    "source_summary",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "feature": {"type": "string"},
                    "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                    "platforms": {"type": "array", "items": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "preconditions": {"type": "array", "items": {"type": "string"}},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["action", "target_text", "target_id", "value", "note"],
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["launch_app", "tap", "input", "assert", "scroll_until_visible", "wait"],
                                },
                                "target_text": {"type": "string"},
                                "target_id": {"type": "string"},
                                "value": {"type": "string"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "assertions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["type", "target_text", "target_id", "expected"],
                            "properties": {
                                "type": {"type": "string", "enum": ["visible", "not_visible", "exists", "not_exists", "ai"]},
                                "target_text": {"type": "string"},
                                "target_id": {"type": "string"},
                                "expected": {"type": "string"},
                            },
                        },
                    },
                    "source_summary": {"type": "string"},
                },
            },
        }
    },
}


SOURCE_MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "source_type",
        "feature",
        "screen",
        "visible_texts",
        "controls",
        "states",
        "testable_points",
        "risks",
        "open_questions",
        "confidence",
    ],
    "properties": {
        "source_type": {"type": "string"},
        "feature": {"type": "string"},
        "screen": {"type": "string"},
        "visible_texts": {"type": "array", "items": {"type": "string"}},
        "controls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["role", "label", "description"],
                "properties": {
                    "role": {"type": "string"},
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "states": {"type": "array", "items": {"type": "string"}},
        "testable_points": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
}


@dataclass
class AIStatus:
    enabled: bool
    provider: str
    model: str
    reason: str


class OpenAIClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("AI_MODEL") or DEFAULT_OPENAI_MODEL
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.timeout_seconds = timeout_seconds or int(os.environ.get("AI_TIMEOUT_SECONDS") or "45")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def status(self) -> AIStatus:
        if not self.enabled:
            return AIStatus(
                enabled=False,
                provider="openai",
                model=self.model,
                reason="OPENAI_API_KEY is not set. Rule-based fallback generation is active.",
            )
        return AIStatus(
            enabled=True,
            provider="openai",
            model=self.model,
            reason="OPENAI_API_KEY is set. Structured AI generation is active.",
        )

    def generate_test_cases(
        self,
        requirement: str,
        feature: str,
        screen: str,
        platforms: list[str],
        max_cases: int,
        contexts: list[dict[str, Any]],
        prd_contexts: list[dict[str, Any]],
        figma_contexts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        prompt = self._build_case_prompt(
            requirement=requirement,
            feature=feature,
            screen=screen,
            platforms=platforms,
            max_cases=max_cases,
            contexts=contexts,
            prd_contexts=prd_contexts,
            figma_contexts=figma_contexts,
        )
        payload = {
            "model": self.model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "test_case_generation",
                    "description": "Structured mobile app test cases for the platform Test Case DSL.",
                    "strict": True,
                    "schema": TEST_CASE_SCHEMA,
                }
            },
        }
        data = self._post_json("/responses", payload)
        parsed = self._extract_json(data)
        cases = parsed.get("cases", [])
        return cases if isinstance(cases, list) else []

    def extract_figma_image_source_model(
        self,
        image_bytes: bytes,
        content_type: str,
        filename: str,
        feature: str,
        screen: str,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        image_data = base64.b64encode(image_bytes).decode("ascii")
        media_type = content_type or "image/png"
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"""Extract a structured testing source model from this Figma design image.

Focus on mobile app testing. Identify visible UI text, controls, screen states, and concrete testable points.

Filename: {filename}
Feature: {feature}
Screen: {screen}
""",
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{media_type};base64,{image_data}",
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "figma_image_source_model",
                    "description": "Structured source model extracted from a Figma design image.",
                    "strict": True,
                    "schema": SOURCE_MODEL_SCHEMA,
                }
            },
        }
        data = self._post_json("/responses", payload)
        parsed = self._extract_json(data)
        parsed["source_type"] = parsed.get("source_type") or "figma_image"
        parsed["feature"] = parsed.get("feature") or feature
        parsed["screen"] = parsed.get("screen") or screen
        return parsed

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc

    def _extract_json(self, response_data: dict[str, Any]) -> dict[str, Any]:
        if isinstance(response_data.get("output_text"), str):
            return json.loads(response_data["output_text"])
        for item in response_data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return json.loads(text)
        raise RuntimeError("OpenAI response did not contain structured output text")

    def _build_case_prompt(
        self,
        requirement: str,
        feature: str,
        screen: str,
        platforms: list[str],
        max_cases: int,
        contexts: list[dict[str, Any]],
        prd_contexts: list[dict[str, Any]],
        figma_contexts: list[dict[str, Any]],
    ) -> str:
        context_block = self._format_contexts(contexts)
        # Figma-only MVP: PRD context is intentionally empty unless a future mode re-enables it.
        prd_block = self._format_contexts(prd_contexts)
        figma_block = self._format_contexts(figma_contexts)
        return f"""You are generating executable mobile app test cases for an AI testing platform.

Return JSON that matches the provided schema exactly.

Rules:
- Generate at most {max_cases} cases.
- Prefer deterministic assertions over vague visual checks.
- Use action names from the schema only.
- Use target_text when the UI copy is known. Use target_id only when an explicit id is known.
- Include smoke and regression tags for critical happy paths.
- Generate cases from structured source models and Figma/design context first. Treat the requirement text only as optional guidance.
- Prefer controls, visible_texts, states, risks, and testable_points from source_model context when present.
- Keep steps concise and executable through Maestro-style UI automation.

Feature: {feature}
Screen: {screen}
Platforms: {", ".join(platforms)}

Requirement:
{requirement}

Requirement notes:
{prd_block}

Figma / design context:
{figma_block}

Combined retrieved context:
{context_block}
"""

    def _format_contexts(self, contexts: list[dict[str, Any]], limit: int = 8) -> str:
        if not contexts:
            return "No context found."
        lines: list[str] = []
        for index, context in enumerate(contexts[:limit], start=1):
            source = context.get("source_type", "unknown")
            document_id = context.get("document_id", "")
            chunk_id = context.get("chunk_id", "")
            score = context.get("score", "")
            content = str(context.get("content") or "").strip()[:1600]
            lines.append(f"[{index}] source={source} document={document_id} chunk={chunk_id} score={score}\n{content}")
        return "\n\n".join(lines)
