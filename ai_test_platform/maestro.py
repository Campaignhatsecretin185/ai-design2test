from __future__ import annotations

from pathlib import Path
from shutil import which
from time import monotonic
from typing import Any
import os
import subprocess

from .models import TestAssertion, TestCase


FLOW_DIR = Path(os.environ.get("MAESTRO_FLOW_DIR", "data/maestro_flows"))


def yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def target_to_yaml(target: dict[str, Any]) -> str:
    if "id" in target:
        return f"id: {yaml_scalar(str(target['id']))}"
    if "text" in target:
        return yaml_scalar(str(target["text"]))
    if "label" in target:
        return yaml_scalar(str(target["label"]))
    return yaml_scalar(str(target))


def assertion_to_commands(assertion: TestAssertion) -> list[str]:
    if assertion.type in {"visible", "exists"}:
        return [f"- assertVisible: {target_to_yaml(assertion.target)}"]
    if assertion.type in {"not_visible", "not_exists"}:
        return [f"- assertNotVisible: {target_to_yaml(assertion.target)}"]
    if assertion.type == "ai":
        prompt = assertion.expected or str(assertion.target)
        return ["- assertWithAI:", f"    assertion: {yaml_scalar(prompt)}"]
    return [f"- assertVisible: {target_to_yaml(assertion.target)}"]


class MaestroFlowGenerator:
    def __init__(self, app_id: str = "${APP_ID}", flow_dir: Path = FLOW_DIR):
        self.app_id = app_id
        self.flow_dir = flow_dir
        self.flow_dir.mkdir(parents=True, exist_ok=True)

    def render(self, case: TestCase) -> str:
        lines = [
            f"appId: {self.app_id}",
            "tags:",
            *[f"  - {tag}" for tag in case.tags],
            "---",
        ]
        for step in case.steps:
            if step.action == "launch_app":
                lines.append("- launchApp")
            elif step.action == "tap":
                lines.append(f"- tapOn: {target_to_yaml(step.target)}")
            elif step.action == "input":
                lines.append(f"- inputText: {yaml_scalar(step.value)}")
            elif step.action == "assert":
                target = step.target or {"text": step.value}
                lines.append(f"- assertVisible: {target_to_yaml(target)}")
            elif step.action == "scroll_until_visible":
                lines.append("- scrollUntilVisible:")
                lines.append(f"    element: {target_to_yaml(step.target)}")
            elif step.action == "wait":
                lines.append("- extendedWaitUntil:")
                lines.append(f"    visible: {target_to_yaml(step.target)}")
                lines.append("    timeout: 10000")
        for assertion in case.assertions:
            lines.extend(assertion_to_commands(assertion))
        return "\n".join(lines) + "\n"

    def write(self, case: TestCase) -> tuple[str, Path]:
        yaml = self.render(case)
        safe_title = "".join(ch if ch.isalnum() else "_" for ch in case.title)[:60].strip("_")
        path = self.flow_dir / f"case_{case.id}_{safe_title}.yaml"
        path.write_text(yaml, encoding="utf-8")
        return yaml, path


class MaestroRunner:
    def __init__(self, enabled: bool | None = None):
        self.enabled = enabled if enabled is not None else os.environ.get("MAESTRO_ENABLED") == "true"

    def run(self, flow_path: Path) -> dict[str, Any]:
        start = monotonic()
        if not self.enabled:
            return {
                "status": "passed",
                "duration_ms": int((monotonic() - start) * 1000),
                "output": f"Dry-run passed. Flow generated at {flow_path}",
                "artifacts": {"flow_path": str(flow_path), "dry_run": True},
            }
        if which("maestro") is None:
            return {
                "status": "blocked",
                "duration_ms": int((monotonic() - start) * 1000),
                "output": "MAESTRO_ENABLED=true but maestro CLI was not found in PATH.",
                "artifacts": {"flow_path": str(flow_path), "dry_run": False},
            }
        process = subprocess.run(
            ["maestro", "test", str(flow_path)],
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        output = "\n".join(part for part in [process.stdout, process.stderr] if part)
        return {
            "status": "passed" if process.returncode == 0 else "failed",
            "duration_ms": int((monotonic() - start) * 1000),
            "output": output,
            "artifacts": {"flow_path": str(flow_path), "return_code": process.returncode},
        }

