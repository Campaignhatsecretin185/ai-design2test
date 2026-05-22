from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any
import cgi
import json
import os
import re

from .db import Database
from .figma_mcp import build_screen_model, parse_context_payload, screen_model_to_document
from .file_ingestion import store_and_extract_file
from .generator import CaseGenerator
from .maestro import MaestroFlowGenerator, MaestroRunner
from .models import Document
from .rag import Retriever, chunk_document
from .regression import RegressionSelector
from .report import build_report_html


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


class App:
    def __init__(self) -> None:
        self.db = Database()
        self.retriever = Retriever(self.db)
        self.generator = CaseGenerator(self.retriever)
        self.flow_generator = MaestroFlowGenerator(app_id=os.environ.get("APP_ID", "${APP_ID}"))
        self.runner = MaestroRunner()
        self.regression_selector = RegressionSelector()

    def add_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        document = Document(
            id=None,
            title=str(payload.get("title") or "Untitled"),
            source_type=str(payload.get("source_type") or "prd"),
            content=str(payload.get("content") or ""),
            feature=str(payload.get("feature") or ""),
            screen=str(payload.get("screen") or ""),
            tags=list(payload.get("tags") or []),
        )
        if not document.content.strip():
            raise ValueError("content is required")
        document_id = self.db.add_document(document, chunk_document(document))
        return {"id": document_id}

    def generate_cases(self, payload: dict[str, Any]) -> dict[str, Any]:
        cases = self.generator.generate(payload)
        stored = []
        duplicate_count = 0
        for case in cases:
            case.fingerprint = case.fingerprint or case.compute_fingerprint()
            existing = self.db.get_test_case_by_fingerprint(case.fingerprint)
            if existing:
                duplicate_count += 1
                existing_payload = existing.to_payload()
                existing_payload["deduped"] = True
                existing_payload["duplicate_reason"] = "matched existing test case fingerprint"
                stored.append(existing_payload)
                continue
            case.id = self.db.add_test_case(case)
            stored_payload = case.to_payload()
            stored_payload["deduped"] = False
            stored.append(stored_payload)
        return {
            "cases": stored,
            "created_count": len(stored) - duplicate_count,
            "duplicate_count": duplicate_count,
            "generation_mode": self.generator.last_generation_mode,
            "generation_error": self.generator.last_generation_error,
        }

    def add_source_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_json = payload.get("model_json") or payload.get("model") or {}
        if not isinstance(model_json, dict):
            raise ValueError("model_json must be an object")
        source_model_id = self.db.add_source_model(
            source_type=str(payload.get("source_type") or model_json.get("source_type") or "unknown"),
            feature=str(payload.get("feature") or model_json.get("feature") or ""),
            screen=str(payload.get("screen") or model_json.get("screen") or ""),
            model_json=model_json,
            source_refs=payload.get("source_refs") or [],
            version_label=str(payload.get("version_label") or model_json.get("version_label") or ""),
            confidence=float(payload.get("confidence") or model_json.get("confidence") or 0),
            change_summary=str(payload.get("change_summary") or "Initial source model version"),
        )
        return {"id": source_model_id}

    def create_change_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        change_set_id = self.db.create_change_set(
            name=str(payload.get("name") or "Untitled change set"),
            summary=str(payload.get("summary") or ""),
            feature=str(payload.get("feature") or ""),
            screen=str(payload.get("screen") or ""),
            source_model_ids=[int(item) for item in payload.get("source_model_ids", [])],
        )
        return {"id": change_set_id}

    def add_case_suggestion(self, payload: dict[str, Any]) -> dict[str, Any]:
        suggestion_id = self.db.add_case_suggestion(
            suggestion_type=str(payload.get("suggestion_type") or "new_case"),
            payload=payload.get("payload") or {},
            reason=str(payload.get("reason") or ""),
            change_set_id=int(payload["change_set_id"]) if payload.get("change_set_id") else None,
            test_case_id=int(payload["test_case_id"]) if payload.get("test_case_id") else None,
        )
        return {"id": suggestion_id}

    def ingest_figma_mcp_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        figma_url = str(payload.get("figma_url") or "")
        raw_context = payload.get("mcp_context")
        feature = str(payload.get("feature") or "")
        if not figma_url.strip():
            raise ValueError("figma_url is required")
        if raw_context in (None, ""):
            raise ValueError("mcp_context is required")
        parsed_context = parse_context_payload(raw_context)
        screen_model = build_screen_model(figma_url, parsed_context)
        screen = str(payload.get("screen") or screen_model.get("screen") or "Figma Screen")
        screen_model["screen"] = screen
        document = Document(
            id=None,
            title=f"Figma MCP: {screen}",
            source_type="figma_mcp",
            content=screen_model_to_document(screen_model),
            feature=feature,
            screen=screen,
            tags=["figma", "mcp", "design-context"],
        )
        document_id = self.db.add_document(document, chunk_document(document))
        artifact_id = self.db.add_figma_artifact(figma_url, parsed_context, screen_model, document_id)
        return {
            "id": artifact_id,
            "document_id": document_id,
            "screen_model": screen_model,
        }

    def ingest_source_file(self, fields: dict[str, Any]) -> dict[str, Any]:
        file_info = fields.get("file")
        if not isinstance(file_info, dict):
            raise ValueError("file is required")
        source_type = str(fields.get("source_type") or "document")
        feature = str(fields.get("feature") or "")
        screen = str(fields.get("screen") or "")
        extracted = store_and_extract_file(
            filename=str(file_info.get("filename") or "upload.bin"),
            content=file_info.get("content") or b"",
            content_type=str(file_info.get("content_type") or ""),
        )
        ai_source_model: dict[str, Any] = {}
        ai_extraction_error = ""
        if source_type == "figma_image" and self.generator.ai_client.enabled:
            try:
                ai_source_model = self.generator.ai_client.extract_figma_image_source_model(
                    image_bytes=Path(extracted.path).read_bytes(),
                    content_type=extracted.content_type,
                    filename=extracted.filename,
                    feature=feature,
                    screen=screen,
                )
                extracted.extracted_text = self._source_model_to_document(ai_source_model)
                extracted.extraction_status = "ai_extracted"
                extracted.extraction_notes = "Figma image was parsed by OpenAI vision into a structured source model."
            except Exception as exc:
                ai_extraction_error = str(exc)
        document = Document(
            id=None,
            title=f"{source_type}: {extracted.filename}",
            source_type=source_type,
            content=extracted.extracted_text,
            feature=feature,
            screen=screen,
            tags=["upload", extracted.extraction_status],
        )
        document_id = self.db.add_document(document, chunk_document(document))
        source_file_id = self.db.add_source_file(
            filename=extracted.filename,
            content_type=extracted.content_type,
            source_type=source_type,
            feature=feature,
            screen=screen,
            size=extracted.size,
            path=extracted.path,
            extracted_text=extracted.extracted_text,
            extraction_status=extracted.extraction_status,
            extraction_notes=extracted.extraction_notes,
            document_id=document_id,
        )
        source_model_id = None
        if ai_source_model:
            source_model_id = self.db.add_source_model(
                source_type="figma_image",
                feature=feature,
                screen=screen,
                model_json=ai_source_model,
                source_refs=[{"type": "source_file", "id": source_file_id, "document_id": document_id}],
                version_label=extracted.filename,
                confidence=float(ai_source_model.get("confidence") or 0),
                change_summary="Initial Figma image source model extracted by AI",
            )
        return {
            "id": source_file_id,
            "document_id": document_id,
            "source_model_id": source_model_id,
            "filename": extracted.filename,
            "content_type": extracted.content_type,
            "size": extracted.size,
            "extraction_status": extracted.extraction_status,
            "extraction_notes": extracted.extraction_notes,
            "ai_extraction_error": ai_extraction_error,
            "extracted_preview": extracted.extracted_text[:1000],
        }

    def _source_model_to_document(self, model: dict[str, Any]) -> str:
        lines = [
            f"Figma image source model for {model.get('screen', 'Unknown Screen')}",
            f"Feature: {model.get('feature', '')}",
            "",
            "Visible texts:",
            *[f"- {item}" for item in model.get("visible_texts", [])],
            "",
            "Controls:",
        ]
        for control in model.get("controls", []):
            lines.append(f"- {control.get('role', 'control')}: {control.get('label', '')} {control.get('description', '')}".strip())
        lines.append("")
        lines.append("States:")
        lines.extend([f"- {item}" for item in model.get("states", [])])
        lines.append("")
        lines.append("Testable points:")
        lines.extend([f"- {item}" for item in model.get("testable_points", [])])
        lines.append("")
        lines.append("Risks:")
        lines.extend([f"- {item}" for item in model.get("risks", [])])
        return "\n".join(lines)

    def approve_case(self, case_id: int) -> dict[str, Any]:
        if not self.db.get_test_case(case_id):
            raise KeyError("test case not found")
        self.db.update_test_case_status(case_id, "approved")
        return {"id": case_id, "status": "approved"}

    def generate_maestro(self, case_id: int) -> dict[str, Any]:
        case = self.db.get_test_case(case_id)
        if not case:
            raise KeyError("test case not found")
        yaml, path = self.flow_generator.write(case)
        flow_id = self.db.add_maestro_flow(case_id, yaml, str(path))
        self.db.update_test_case_status(case_id, "executable")
        return {"id": flow_id, "case_id": case_id, "path": str(path), "yaml": yaml}

    def select_regression(self, payload: dict[str, Any]) -> dict[str, Any]:
        cases = self.db.list_test_cases()
        selected = self.regression_selector.select(cases, payload, self.db.get_case_stats_map())
        return {"selected": selected, "count": len(selected)}

    def run_cases(self, payload: dict[str, Any]) -> dict[str, Any]:
        case_ids = [int(case_id) for case_id in payload.get("case_ids", [])]
        if not case_ids:
            selected = self.select_regression(payload).get("selected", [])
            case_ids = [int(item["case"]["id"]) for item in selected]
        name = str(payload.get("name") or "Manual run")
        mode = str(payload.get("mode") or ("dry-run" if not self.runner.enabled else "maestro"))
        run_id = self.db.create_run(name=name, mode=mode)

        counts = {"passed": 0, "failed": 0, "blocked": 0}
        total = 0
        for case_id in case_ids:
            case = self.db.get_test_case(case_id)
            if not case:
                continue
            _, path = self.flow_generator.write(case)
            result = self.runner.run(path)
            status = result["status"]
            counts[status] = counts.get(status, 0) + 1
            total += 1
            self.db.add_run_result(
                run_id=run_id,
                test_case_id=case_id,
                status=status,
                duration_ms=result["duration_ms"],
                output=result["output"],
                artifacts=result["artifacts"],
            )
        passed = counts.get("passed", 0)
        summary = {
            "total": total,
            "passed": passed,
            "failed": counts.get("failed", 0),
            "blocked": counts.get("blocked", 0),
            "pass_rate": f"{round((passed / total) * 100, 1)}%" if total else "0%",
        }
        overall = "passed" if total and summary["failed"] == 0 and summary["blocked"] == 0 else "failed"
        self.db.complete_run(run_id, overall, summary)
        return {"run": self.db.get_run(run_id)}


APP = App()


class Handler(BaseHTTPRequestHandler):
    server_version = "AITestPlatform/0.1"

    def do_GET(self) -> None:
        self.dispatch("GET")

    def do_POST(self) -> None:
        self.dispatch("POST")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_cors_headers()
        self.end_headers()

    def dispatch(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/":
                return self.send_static("index.html")
            if path.startswith("/static/"):
                return self.send_static(path.removeprefix("/static/"))
            if path == "/api/health" and method == "GET":
                return self.send_json({"ok": True, "version": "0.1.0"})
            if path == "/api/ai/status" and method == "GET":
                return self.send_json({"ai": APP.generator.ai_status()})
            if path == "/api/documents" and method == "GET":
                return self.send_json({"documents": APP.db.list_documents()})
            if path == "/api/documents" and method == "POST":
                return self.send_json(APP.add_document(self.read_json()), HTTPStatus.CREATED)
            if path == "/api/figma/mcp-context" and method == "POST":
                return self.send_json(APP.ingest_figma_mcp_context(self.read_json()), HTTPStatus.CREATED)
            if path == "/api/figma/artifacts" and method == "GET":
                return self.send_json({"artifacts": APP.db.list_figma_artifacts()})
            if path == "/api/source-files" and method == "POST":
                return self.send_json(APP.ingest_source_file(self.read_multipart()), HTTPStatus.CREATED)
            if path == "/api/source-files" and method == "GET":
                return self.send_json({"files": APP.db.list_source_files()})
            if path == "/api/generate-cases" and method == "POST":
                return self.send_json(APP.generate_cases(self.read_json()), HTTPStatus.CREATED)
            if path == "/api/test-cases" and method == "GET":
                status = query.get("status", [""])[0]
                feature = query.get("feature", [""])[0]
                cases = [case.to_payload() for case in APP.db.list_test_cases(status=status, feature=feature)]
                return self.send_json({"cases": cases})
            if path == "/api/memory" and method == "GET":
                return self.send_json({"memory": APP.db.memory_summary()})
            if path == "/api/memory/context" and method == "GET":
                feature = query.get("feature", [""])[0]
                screen = query.get("screen", [""])[0]
                return self.send_json({"context": APP.db.build_memory_context(feature=feature, screen=screen)})
            if path == "/api/source-models" and method == "POST":
                return self.send_json(APP.add_source_model(self.read_json()), HTTPStatus.CREATED)
            if path == "/api/source-models" and method == "GET":
                feature = query.get("feature", [""])[0]
                screen = query.get("screen", [""])[0]
                return self.send_json({"source_models": APP.db.list_source_models(feature=feature, screen=screen)})
            if path == "/api/change-sets" and method == "POST":
                return self.send_json(APP.create_change_set(self.read_json()), HTTPStatus.CREATED)
            if path == "/api/case-suggestions" and method == "POST":
                return self.send_json(APP.add_case_suggestion(self.read_json()), HTTPStatus.CREATED)
            if match := re.fullmatch(r"/api/test-cases/(\d+)/approve", path):
                if method == "POST":
                    return self.send_json(APP.approve_case(int(match.group(1))))
            if match := re.fullmatch(r"/api/test-cases/(\d+)/maestro", path):
                if method == "POST":
                    return self.send_json(APP.generate_maestro(int(match.group(1))))
            if path == "/api/regression/select" and method == "POST":
                return self.send_json(APP.select_regression(self.read_json()))
            if path == "/api/runs" and method == "POST":
                return self.send_json(APP.run_cases(self.read_json()), HTTPStatus.CREATED)
            if match := re.fullmatch(r"/api/runs/(\d+)", path):
                if method == "GET":
                    run = APP.db.get_run(int(match.group(1)))
                    if not run:
                        raise KeyError("run not found")
                    return self.send_json({"run": run})
            if match := re.fullmatch(r"/api/reports/(\d+)\.html", path):
                if method == "GET":
                    run = APP.db.get_run(int(match.group(1)))
                    if not run:
                        raise KeyError("run not found")
                    return self.send_html(build_report_html(run))
            self.send_error_json(HTTPStatus.NOT_FOUND, "not found")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except KeyError as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc).strip("'"))
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("json body must be an object")
        return value

    def read_multipart(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("multipart/form-data is required")
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        fields: dict[str, Any] = {}
        for key in form.keys():
            item = form[key]
            if isinstance(item, list):
                item = item[0]
            if item.filename:
                fields[key] = {
                    "filename": item.filename,
                    "content_type": item.type or "",
                    "content": item.file.read(),
                }
            else:
                fields[key] = item.value
        return fields

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_cors_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, name: str) -> None:
        path = (STATIC_DIR / name).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())) or not path.exists():
            return self.send_error_json(HTTPStatus.NOT_FOUND, "static file not found")
        content_type = "text/html; charset=utf-8"
        if path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("QUIET_LOGS") != "true":
            super().log_message(format, *args)


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AI App Test Platform running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
