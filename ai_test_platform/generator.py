from __future__ import annotations

from typing import Any
import re

from .ai_client import OpenAIClient
from .models import TestAssertion, TestCase, TestStep
from .rag import Retriever


def normalize_feature(value: str) -> str:
    value = value.strip()
    if not value:
        return "general"
    return re.sub(r"\s+", "_", value.lower())


def infer_priority(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["p0", "payment", "login", "signup", "checkout", "core", "critical"]):
        return "P0"
    if any(token in lowered for token in ["p1", "error", "permission", "network", "edge", "boundary", "failure"]):
        return "P1"
    return "P2"


def extract_rules(text: str) -> list[str]:
    lines = []
    for raw in re.split(r"[\n。；;]", text):
        line = raw.strip(" -\t\r")
        if 6 <= len(line) <= 120:
            lines.append(line)
    if not lines and text.strip():
        lines = [text.strip()[:100]]
    return lines[:8]


class CaseGenerator:
    def __init__(self, retriever: Retriever, ai_client: OpenAIClient | None = None):
        self.retriever = retriever
        self.ai_client = ai_client or OpenAIClient()
        self.last_generation_mode = "rule_fallback"
        self.last_generation_error = ""

    def generate(self, payload: dict[str, Any]) -> list[TestCase]:
        requirement = str(payload.get("requirement") or "")
        feature = normalize_feature(str(payload.get("feature") or ""))
        screen = str(payload.get("screen") or "")
        platforms = payload.get("platforms") or ["android", "ios"]
        max_cases = int(payload.get("max_cases") or 4)

        contexts = self.retriever.search(
            query=requirement,
            feature=feature if feature != "general" else "",
            screen=screen,
            limit=8,
        )
        # Figma-only MVP: PRD ingestion is intentionally disabled for now.
        prd_contexts: list[dict[str, Any]] = []
        figma_contexts = self.retriever.search(
            query=requirement,
            feature=feature if feature != "general" else "",
            screen=screen,
            source_types=["figma", "figma_mcp", "figma_image", "design"],
            limit=4,
        )
        contexts = self._merge_contexts([figma_contexts, contexts])
        ai_cases = self._generate_with_ai(
            requirement=requirement,
            feature=feature,
            screen=screen,
            platforms=platforms,
            max_cases=max_cases,
            contexts=contexts,
            prd_contexts=prd_contexts,
            figma_contexts=figma_contexts,
        )
        if ai_cases:
            self.last_generation_mode = "ai"
            self.last_generation_error = ""
            return ai_cases[:max_cases]

        self.last_generation_mode = "rule_fallback"
        context_text = "\n".join(item["content"] for item in contexts)
        rules = extract_rules("\n".join([requirement, context_text]))
        if not rules:
            rules = [f"{feature} happy-path validation"]

        cases: list[TestCase] = []
        cases.append(self._happy_path_case(feature, platforms, requirement, contexts))

        for index, rule in enumerate(rules[: max_cases - len(cases)], start=1):
            cases.append(self._rule_case(feature, platforms, rule, requirement, contexts, index))

        return cases[:max_cases]

    def ai_status(self) -> dict[str, Any]:
        status = self.ai_client.status()
        return {
            "enabled": status.enabled,
            "provider": status.provider,
            "model": status.model,
            "reason": status.reason,
            "last_generation_mode": self.last_generation_mode,
            "last_generation_error": self.last_generation_error,
        }

    def _generate_with_ai(
        self,
        requirement: str,
        feature: str,
        screen: str,
        platforms: list[str],
        max_cases: int,
        contexts: list[dict[str, Any]],
        prd_contexts: list[dict[str, Any]],
        figma_contexts: list[dict[str, Any]],
    ) -> list[TestCase]:
        if not self.ai_client.enabled:
            self.last_generation_error = ""
            return []
        try:
            payloads = self.ai_client.generate_test_cases(
                requirement=requirement,
                feature=feature,
                screen=screen,
                platforms=platforms,
                max_cases=max_cases,
                contexts=contexts,
                prd_contexts=prd_contexts,
                figma_contexts=figma_contexts,
            )
            return [self._case_from_ai_payload(item, feature, platforms, contexts) for item in payloads[:max_cases]]
        except Exception as exc:
            self.last_generation_error = str(exc)
            return []

    def _case_from_ai_payload(
        self,
        payload: dict[str, Any],
        default_feature: str,
        default_platforms: list[str],
        contexts: list[dict[str, Any]],
    ) -> TestCase:
        feature = normalize_feature(str(payload.get("feature") or default_feature))
        steps = [
            TestStep(
                action=str(item.get("action") or "assert"),
                target=self._target_from_ai(item),
                value=str(item.get("value") or ""),
                note=str(item.get("note") or ""),
            )
            for item in payload.get("steps", [])
            if isinstance(item, dict)
        ]
        assertions = [
            TestAssertion(
                type=str(item.get("type") or "visible"),
                target=self._target_from_ai(item),
                expected=str(item.get("expected") or ""),
            )
            for item in payload.get("assertions", [])
            if isinstance(item, dict)
        ]
        if not steps:
            steps = [TestStep(action="launch_app")]
        if not assertions:
            assertions = [TestAssertion(type="visible", target={"text": self._entry_text(feature)}, expected="Expected UI is visible")]
        tags = [str(tag) for tag in payload.get("tags", []) if str(tag).strip()]
        if "ai-generated" not in tags:
            tags.append("ai-generated")
        return TestCase(
            id=None,
            title=str(payload.get("title") or f"{feature} AI generated validation"),
            feature=feature,
            priority=str(payload.get("priority") or "P2"),
            platforms=[str(item) for item in payload.get("platforms", [])] or default_platforms,
            tags=tags,
            preconditions=[str(item) for item in payload.get("preconditions", [])],
            steps=steps,
            assertions=assertions,
            source_refs=self._source_refs(contexts),
        )

    def _target_from_ai(self, item: dict[str, Any]) -> dict[str, Any]:
        target_id = str(item.get("target_id") or "").strip()
        target_text = str(item.get("target_text") or "").strip()
        if target_id:
            return {"id": target_id}
        if target_text:
            return {"text": target_text}
        return {}

    def _happy_path_case(
        self,
        feature: str,
        platforms: list[str],
        requirement: str,
        contexts: list[dict[str, Any]],
    ) -> TestCase:
        title = f"{feature} happy-path validation"
        entry_text = self._entry_text(feature)
        return TestCase(
            id=None,
            title=title,
            feature=feature,
            priority=infer_priority(requirement),
            platforms=platforms,
            tags=["smoke", "regression", feature],
            preconditions=["The app is installed", "Test account and test data are ready"],
            steps=[
                TestStep(action="launch_app"),
                TestStep(action="tap", target={"text": entry_text}, note="Open the target feature"),
                TestStep(action="assert", target={"text": entry_text}, note="Confirm the entry point is visible"),
            ],
            assertions=[
                TestAssertion(type="visible", target={"text": entry_text}, expected="The feature entry point or target screen is visible"),
            ],
            source_refs=self._source_refs(contexts),
        )

    def _rule_case(
        self,
        feature: str,
        platforms: list[str],
        rule: str,
        requirement: str,
        contexts: list[dict[str, Any]],
        index: int,
    ) -> TestCase:
        priority = infer_priority(rule + requirement)
        tags = ["regression", feature]
        if priority == "P0":
            tags.append("smoke")
        target_text = self._guess_target_text(rule, feature)
        return TestCase(
            id=None,
            title=f"{feature} rule validation {index}: {rule[:36]}",
            feature=feature,
            priority=priority,
            platforms=platforms,
            tags=tags,
            preconditions=["The app is installed", "The test environment is available"],
            steps=[
                TestStep(action="launch_app"),
                TestStep(action="tap", target={"text": self._entry_text(feature)}),
                TestStep(action="assert", target={"text": target_text}, note=rule),
            ],
            assertions=[
                TestAssertion(type="visible", target={"text": target_text}, expected=rule),
            ],
            source_refs=self._source_refs(contexts),
        )

    def _source_refs(self, contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": item["source_type"],
                "document_id": item["document_id"],
                "chunk_id": item["chunk_id"],
                "score": item["score"],
            }
            for item in contexts[:4]
        ]

    def _merge_contexts(self, groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for group in groups:
            for item in group:
                key = (int(item["document_id"]), int(item["chunk_id"]))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return sorted(merged, key=lambda item: item["score"], reverse=True)

    def _entry_text(self, feature: str) -> str:
        common = {
            "login": "Login",
            "payment": "Payment",
            "order": "Orders",
            "profile": "Profile",
            "search": "Search",
        }
        return common.get(feature, feature.replace("_", " "))

    def _guess_target_text(self, rule: str, feature: str) -> str:
        quoted = re.findall(r"[「“\"]([^」”\"]+)[」”\"]", rule)
        if quoted:
            return quoted[0]
        for keyword in ["success", "failed", "error", "home", "payment", "order", "login", "code", "submit", "save"]:
            if keyword in rule:
                return keyword
        return self._entry_text(feature)
