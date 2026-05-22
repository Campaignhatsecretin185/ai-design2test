from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
import json
import re


CONTROL_HINTS = {
    "button": "button",
    "btn": "button",
    "input": "input",
    "field": "input",
    "textfield": "input",
    "text field": "input",
    "tab": "tab",
    "checkbox": "checkbox",
    "switch": "switch",
    "toggle": "switch",
    "modal": "modal",
    "dialog": "dialog",
    "toast": "toast",
    "alert": "alert",
    "card": "card",
    "nav": "navigation",
}


def parse_figma_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    file_key = ""
    if len(parts) >= 2 and parts[0] in {"file", "design", "proto"}:
        file_key = parts[1]

    query = parse_qs(parsed.query)
    node_id = query.get("node-id", [""])[0] or query.get("node_id", [""])[0]
    if not node_id:
        match = re.search(r"node-id=([^&]+)", url)
        node_id = unquote(match.group(1)) if match else ""
    return {"file_key": file_key, "node_id": node_id.replace("-", ":")}


def parse_context_payload(raw_context: Any) -> Any:
    if isinstance(raw_context, (dict, list)):
        return raw_context
    if raw_context is None:
        return {}
    text = str(raw_context).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"type": "MCP_TEXT_CONTEXT", "name": "Figma MCP Context", "text": text}


def build_screen_model(figma_url: str, raw_context: Any) -> dict[str, Any]:
    parsed_url = parse_figma_url(figma_url)
    context = parse_context_payload(raw_context)
    nodes = list(_walk_nodes(context))
    frame = _pick_screen_node(nodes) or {}
    elements = _extract_elements(nodes)
    screen_name = str(frame.get("name") or _find_first_name(context) or "Figma Screen")
    testable_points = _build_testable_points(screen_name, elements)
    return {
        "source": "figma_mcp",
        "figma_url": figma_url,
        "file_key": parsed_url["file_key"],
        "node_id": parsed_url["node_id"],
        "screen": screen_name,
        "elements": elements,
        "testable_points": testable_points,
    }


def screen_model_to_document(model: dict[str, Any]) -> str:
    lines = [
        f"Figma screen: {model.get('screen', 'Figma Screen')}",
        f"File key: {model.get('file_key', '')}",
        f"Node ID: {model.get('node_id', '')}",
        "",
        "UI elements:",
    ]
    for element in model.get("elements", []):
        label = element.get("text") or element.get("name") or "Unnamed"
        role = element.get("role") or element.get("type") or "element"
        lines.append(f"- {role}: {label}")
    lines.append("")
    lines.append("Testable points:")
    for point in model.get("testable_points", []):
        lines.append(f"- {point}")
    return "\n".join(lines)


def _walk_nodes(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if any(key in value for key in ("name", "type", "characters", "text", "children")):
            found.append(value)
        for child in value.values():
            found.extend(_walk_nodes(child))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_nodes(item))
    return found


def _pick_screen_node(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred_types = {"FRAME", "COMPONENT", "INSTANCE", "SECTION"}
    for node in nodes:
        if str(node.get("type", "")).upper() in preferred_types and node.get("name"):
            return node
    for node in nodes:
        if node.get("name"):
            return node
    return None


def _extract_elements(nodes: list[dict[str, Any]], limit: int = 80) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for node in nodes:
        node_type = str(node.get("type") or node.get("nodeType") or "").upper()
        name = str(node.get("name") or node.get("label") or "").strip()
        text = str(node.get("characters") or node.get("text") or "").strip()
        component = _component_name(node)
        role = _infer_role(" ".join([name, text, component, node_type]))
        is_relevant = text or role != "element" or node_type in {"TEXT", "INSTANCE", "COMPONENT"}
        if not is_relevant:
            continue
        key = (node_type, name, text)
        if key in seen:
            continue
        seen.add(key)
        elements.append(
            {
                "type": node_type or "UNKNOWN",
                "name": name,
                "text": text,
                "role": role,
                "component": component,
                "node_id": str(node.get("id") or ""),
            }
        )
        if len(elements) >= limit:
            break
    return elements


def _component_name(node: dict[str, Any]) -> str:
    for key in ("componentName", "component", "componentPath", "mainComponentName"):
        value = node.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and value.get("name"):
            return str(value["name"])
    return ""


def _infer_role(value: str) -> str:
    lowered = value.lower().replace("_", " ")
    for hint, role in CONTROL_HINTS.items():
        if hint in lowered:
            return role
    return "text" if "TEXT" in value else "element"


def _build_testable_points(screen_name: str, elements: list[dict[str, Any]]) -> list[str]:
    points: list[str] = [f"{screen_name} should render successfully."]
    for element in elements[:30]:
        label = element.get("text") or element.get("name")
        role = element.get("role") or "element"
        if not label:
            continue
        if role in {"button", "input", "tab", "checkbox", "switch"}:
            points.append(f"{label} {role} should be visible and interactive.")
        elif role in {"modal", "dialog", "toast", "alert"}:
            points.append(f"{label} {role} state should be validated when triggered.")
        elif role == "text":
            points.append(f"Text '{label}' should be visible.")
    return _dedupe(points)


def _find_first_name(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("name"):
            return str(value["name"])
        for child in value.values():
            name = _find_first_name(child)
            if name:
                return name
    if isinstance(value, list):
        for item in value:
            name = _find_first_name(item)
            if name:
                return name
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

