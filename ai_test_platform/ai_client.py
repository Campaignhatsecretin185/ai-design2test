from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib import request, error
import base64
import json
import os
import re


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
    base_url: str = ""
    api_style: str = ""


class ProviderClient:
    provider = "disabled"
    api_style = ""

    @property
    def enabled(self) -> bool:
        return False

    def status(self) -> AIStatus:
        return AIStatus(False, self.provider, "", "AI provider is disabled.")

    def generate_test_cases(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def extract_figma_image_source_model(self, **kwargs: Any) -> dict[str, Any]:
        return {}


class DisabledAIClient(ProviderClient):
    def __init__(self, provider: str = "disabled", model: str = "", reason: str = "") -> None:
        self.provider = provider
        self.model = model
        self.reason = reason or "AI provider is disabled. Rule-based fallback generation is active."

    def status(self) -> AIStatus:
        return AIStatus(False, self.provider, self.model, self.reason)


class PromptMixin:
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

    def _build_source_model_prompt(self, filename: str, feature: str, screen: str) -> str:
        return f"""Extract a structured testing source model from this Figma design image.

Return JSON that matches the provided schema exactly.

Focus on mobile app testing. Identify visible UI text, controls, screen states, and concrete testable points.

Filename: {filename}
Feature: {feature}
Screen: {screen}
"""

    def _schema_instruction(self, schema: dict[str, Any]) -> str:
        return "\n\nJSON schema:\n" + json.dumps(schema, ensure_ascii=False, sort_keys=True)

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


class HTTPJSONClient(PromptMixin, ProviderClient):
    def __init__(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str = "",
        timeout_seconds: int = 45,
        api_style: str = "",
    ) -> None:
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.api_style = api_style

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.base_url)

    def status(self) -> AIStatus:
        if not self.enabled:
            return AIStatus(
                False,
                self.provider,
                self.model,
                f"{self.provider} is not configured. Rule-based fallback generation is active.",
                self.base_url,
                self.api_style,
            )
        return AIStatus(
            True,
            self.provider,
            self.model,
            f"{self.provider} provider is configured. Structured AI generation is active.",
            self.base_url,
            self.api_style,
        )

    def _post_json(self, path: str, payload: dict[str, Any], auth_required: bool = False) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif auth_required:
            raise RuntimeError(f"{self.provider} API key is required")
        req = request.Request(f"{self.base_url}{path}", data=body, method="POST", headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.provider} API error {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"{self.provider} API request failed: {exc.reason}") from exc

    def _extract_json_from_text(self, text: str) -> dict[str, Any]:
        text = text.strip()
        fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise


class OpenAIResponsesClient(HTTPJSONClient):
    def __init__(self, api_key: str, model: str, base_url: str, timeout_seconds: int) -> None:
        super().__init__("openai", model, base_url, api_key, timeout_seconds, api_style="responses")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

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
        prompt = self._build_case_prompt(requirement, feature, screen, platforms, max_cases, contexts, prd_contexts, figma_contexts)
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
        parsed = self._extract_responses_json(self._post_json("/responses", payload, auth_required=True))
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
                        {"type": "input_text", "text": self._build_source_model_prompt(filename, feature, screen)},
                        {"type": "input_image", "image_url": f"data:{media_type};base64,{image_data}"},
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
        parsed = self._extract_responses_json(self._post_json("/responses", payload, auth_required=True))
        parsed["source_type"] = parsed.get("source_type") or "figma_image"
        parsed["feature"] = parsed.get("feature") or feature
        parsed["screen"] = parsed.get("screen") or screen
        return parsed

    def _extract_responses_json(self, response_data: dict[str, Any]) -> dict[str, Any]:
        if isinstance(response_data.get("output_text"), str):
            return self._extract_json_from_text(response_data["output_text"])
        for item in response_data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return self._extract_json_from_text(text)
        raise RuntimeError("AI response did not contain structured output text")


class OpenAICompatibleChatClient(HTTPJSONClient):
    def __init__(self, provider: str, api_key: str, model: str, base_url: str, timeout_seconds: int) -> None:
        super().__init__(provider, model, base_url, api_key, timeout_seconds, api_style="chat_completions")
        self.response_format = os.environ.get("AI_RESPONSE_FORMAT", "json_object").strip().lower()

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
        prompt = self._build_case_prompt(requirement, feature, screen, platforms, max_cases, contexts, prd_contexts, figma_contexts)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt + self._schema_instruction(TEST_CASE_SCHEMA)}],
            "temperature": 0,
        }
        if self.response_format != "none":
            payload["response_format"] = {"type": self.response_format or "json_object"}
        parsed = self._extract_chat_json(self._post_json("/chat/completions", payload))
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
        prompt = self._build_source_model_prompt(filename, feature, screen) + self._schema_instruction(SOURCE_MODEL_SCHEMA)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                    ],
                }
            ],
            "temperature": 0,
        }
        if self.response_format != "none":
            payload["response_format"] = {"type": self.response_format or "json_object"}
        parsed = self._extract_chat_json(self._post_json("/chat/completions", payload))
        parsed["source_type"] = parsed.get("source_type") or "figma_image"
        parsed["feature"] = parsed.get("feature") or feature
        parsed["screen"] = parsed.get("screen") or screen
        return parsed

    def _extract_chat_json(self, response_data: dict[str, Any]) -> dict[str, Any]:
        choices = response_data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                return self._extract_json_from_text(content)
        raise RuntimeError("AI chat response did not contain structured output text")


class OllamaChatClient(HTTPJSONClient):
    def __init__(self, model: str, base_url: str, timeout_seconds: int) -> None:
        super().__init__("ollama", model, base_url, "", timeout_seconds, api_style="ollama_chat")

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
        prompt = self._build_case_prompt(requirement, feature, screen, platforms, max_cases, contexts, prd_contexts, figma_contexts)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt + self._schema_instruction(TEST_CASE_SCHEMA)}],
            "stream": False,
            "format": "json",
        }
        parsed = self._extract_ollama_json(self._post_json("/api/chat", payload))
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
        prompt = self._build_source_model_prompt(filename, feature, screen) + self._schema_instruction(SOURCE_MODEL_SCHEMA)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image_bytes).decode("ascii")],
                }
            ],
            "stream": False,
            "format": "json",
        }
        parsed = self._extract_ollama_json(self._post_json("/api/chat", payload))
        parsed["source_type"] = parsed.get("source_type") or "figma_image"
        parsed["feature"] = parsed.get("feature") or feature
        parsed["screen"] = parsed.get("screen") or screen
        return parsed

    def _extract_ollama_json(self, response_data: dict[str, Any]) -> dict[str, Any]:
        message = response_data.get("message", {})
        content = message.get("content", "")
        if isinstance(content, str) and content.strip():
            return self._extract_json_from_text(content)
        if isinstance(response_data.get("response"), str):
            return self._extract_json_from_text(response_data["response"])
        raise RuntimeError("Ollama response did not contain structured output text")


class AIClient(ProviderClient):
    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
        api_style: str | None = None,
    ) -> None:
        timeout = timeout_seconds or int(os.environ.get("AI_TIMEOUT_SECONDS") or "45")
        selected_provider = (provider or os.environ.get("AI_PROVIDER") or self._default_provider()).strip().lower()
        selected_model = model or os.environ.get("AI_MODEL") or os.environ.get("OPENAI_MODEL") or ""
        selected_key = api_key if api_key is not None else (os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "")
        selected_base_url = base_url or os.environ.get("AI_BASE_URL") or ""
        selected_style = (api_style or os.environ.get("AI_API_STYLE") or "").strip().lower()
        self.client = self._build_client(selected_provider, selected_key, selected_model, selected_base_url, timeout, selected_style)

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    def status(self) -> AIStatus:
        return self.client.status()

    def generate_test_cases(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.client.generate_test_cases(**kwargs)

    def extract_figma_image_source_model(self, **kwargs: Any) -> dict[str, Any]:
        return self.client.extract_figma_image_source_model(**kwargs)

    def _default_provider(self) -> str:
        if os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_API_KEY"):
            return "openai"
        if os.environ.get("OLLAMA_MODEL"):
            return "ollama"
        return "disabled"

    def _build_client(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
        api_style: str,
    ) -> ProviderClient:
        if provider in {"", "disabled", "none", "false"}:
            return DisabledAIClient("disabled", model)
        if provider == "openai":
            openai_model = model or DEFAULT_OPENAI_MODEL
            openai_base = base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            if api_style == "chat_completions":
                return OpenAICompatibleChatClient("openai", api_key, openai_model, openai_base, timeout_seconds)
            return OpenAIResponsesClient(api_key, openai_model, openai_base, timeout_seconds)
        if provider in {"compatible", "openai-compatible", "custom"}:
            if not base_url:
                return DisabledAIClient(provider, model, "AI_BASE_URL is required for OpenAI-compatible providers.")
            if not model:
                return DisabledAIClient(provider, model, "AI_MODEL is required for OpenAI-compatible providers.")
            return OpenAICompatibleChatClient(provider, api_key, model, base_url, timeout_seconds)
        if provider == "ollama":
            ollama_model = model or os.environ.get("OLLAMA_MODEL") or ""
            ollama_base = base_url or os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
            if not ollama_model:
                return DisabledAIClient("ollama", "", "AI_MODEL or OLLAMA_MODEL is required for Ollama.")
            return OllamaChatClient(ollama_model, ollama_base, timeout_seconds)
        return DisabledAIClient(provider, model, f"Unknown AI_PROVIDER '{provider}'.")


# Backward-compatible name used by older code paths.
OpenAIClient = AIClient
