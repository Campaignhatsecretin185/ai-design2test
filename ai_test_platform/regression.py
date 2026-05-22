from __future__ import annotations

from typing import Any

from .models import TestCase
from .rag import cosine_score, tokenize


PRIORITY_WEIGHT = {"P0": 10, "P1": 7, "P2": 4, "P3": 1}


class RegressionSelector:
    def select(
        self,
        cases: list[TestCase],
        payload: dict[str, Any],
        stats_map: dict[int, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        stats_map = stats_map or {}
        changed_features = [str(item).lower() for item in payload.get("changed_features", [])]
        changed_screens = [str(item).lower() for item in payload.get("changed_screens", [])]
        change_summary = str(payload.get("change_summary", ""))
        query_tokens = tokenize(" ".join(changed_features + changed_screens + [change_summary]))

        selected: list[dict[str, Any]] = []
        for case in cases:
            case_text = " ".join(
                [
                    case.title,
                    case.feature,
                    " ".join(case.tags),
                    " ".join(step.note for step in case.steps),
                    " ".join(assertion.expected for assertion in case.assertions),
                ]
            )
            semantic = cosine_score(query_tokens, tokenize(case_text))
            direct = 1.0 if case.feature.lower() in changed_features else 0.0
            tag_match = 1.0 if set(changed_features).intersection({tag.lower() for tag in case.tags}) else 0.0
            smoke = 1.0 if "smoke" in case.tags else 0.0
            priority = PRIORITY_WEIGHT.get(case.priority, 3)
            stats = stats_map.get(int(case.id or 0), {})
            recent_failure = 1.0 if stats.get("last_status") in {"failed", "blocked"} else 0.0
            failure_history = min(1.0, float(stats.get("failure_count_30d") or 0) / 3)
            flaky_attention = min(1.0, float(stats.get("flaky_score") or 0))
            score = (
                direct * 40
                + semantic * 25
                + tag_match * 15
                + priority
                + smoke * 5
                + recent_failure * 15
                + failure_history * 10
                + flaky_attention * 4
            )
            if score >= 8 or smoke:
                selected.append(
                    {
                        "case": case.to_payload(),
                        "score": round(score, 2),
                        "reason": self._reason(
                            direct,
                            semantic,
                            tag_match,
                            smoke,
                            case.priority,
                            recent_failure,
                            failure_history,
                            flaky_attention,
                        ),
                        "memory": {
                            "last_status": stats.get("last_status", ""),
                            "failure_count_30d": stats.get("failure_count_30d", 0),
                            "pass_rate": stats.get("pass_rate", None),
                            "flaky_score": stats.get("flaky_score", None),
                        },
                    }
                )
        return sorted(selected, key=lambda item: item["score"], reverse=True)

    def _reason(
        self,
        direct: float,
        semantic: float,
        tag_match: float,
        smoke: float,
        priority: str,
        recent_failure: float = 0,
        failure_history: float = 0,
        flaky_attention: float = 0,
    ) -> str:
        reasons: list[str] = []
        if direct:
            reasons.append("direct feature match")
        if tag_match:
            reasons.append("tag match")
        if semantic >= 0.12:
            reasons.append("semantic match")
        if smoke:
            reasons.append("smoke coverage")
        if recent_failure:
            reasons.append("recently failed or blocked")
        if failure_history:
            reasons.append("30-day failure history")
        if flaky_attention >= 0.3:
            reasons.append("stability risk")
        reasons.append(f"{priority} priority")
        return ", ".join(reasons)
