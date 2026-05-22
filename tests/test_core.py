from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ai_test_platform.db import Database
from ai_test_platform.ai_client import AIStatus
from ai_test_platform.file_ingestion import extract_text
from ai_test_platform.figma_mcp import build_screen_model, parse_figma_url, screen_model_to_document
from ai_test_platform.generator import CaseGenerator
from ai_test_platform.maestro import MaestroFlowGenerator, MaestroRunner
from ai_test_platform.models import Document, TestAssertion, TestCase, TestStep
from ai_test_platform.rag import Retriever, chunk_document
from ai_test_platform.regression import RegressionSelector


class CoreFlowTest(unittest.TestCase):
    def test_file_text_extraction(self) -> None:
        text, status, notes = extract_text("login.png", b"not-a-real-image", "image/png")
        self.assertEqual(status, "needs_ai")
        self.assertIn("Image file uploaded", text)
        self.assertIn("multimodal", notes)

    def test_figma_mcp_context_builds_screen_model(self) -> None:
        parsed = parse_figma_url("https://www.figma.com/design/abc123/Login?node-id=1-2")
        self.assertEqual(parsed["file_key"], "abc123")
        self.assertEqual(parsed["node_id"], "1:2")

        context = {
            "name": "Login Screen",
            "type": "FRAME",
            "children": [
                {"id": "1:3", "type": "TEXT", "name": "Title", "characters": "Login"},
                {"id": "1:4", "type": "INSTANCE", "name": "Phone Input", "componentName": "TextField"},
                {
                    "id": "1:5",
                    "type": "INSTANCE",
                    "name": "Continue Button",
                    "componentName": "Button/Primary",
                    "children": [{"id": "1:6", "type": "TEXT", "name": "Button Label", "characters": "Continue"}],
                },
            ],
        }
        model = build_screen_model("https://www.figma.com/design/abc123/Login?node-id=1-2", context)
        self.assertEqual(model["screen"], "Login Screen")
        self.assertTrue(any(element["role"] == "button" for element in model["elements"]))
        self.assertTrue(any("Continue" in point for point in model["testable_points"]))
        self.assertIn("Testable points", screen_model_to_document(model))

    def test_generate_store_render_and_select_regression(self) -> None:
        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "app.db")
            figma_model = build_screen_model(
                "https://www.figma.com/design/abc123/Login?node-id=1-2",
                {
                    "name": "Login Screen",
                    "type": "FRAME",
                    "children": [
                        {"id": "1:5", "type": "INSTANCE", "name": "Continue Button", "componentName": "Button/Primary"}
                    ],
                },
            )
            figma_doc = Document(
                id=None,
                title="Figma MCP: Login Screen",
                source_type="figma_mcp",
                content=screen_model_to_document(figma_model),
                feature="login",
                screen="Login Screen",
            )
            figma_document_id = db.add_document(figma_doc, chunk_document(figma_doc))
            db.add_figma_artifact("https://www.figma.com/design/abc123/Login?node-id=1-2", {}, figma_model, figma_document_id)
            memory = db.memory_summary()
            self.assertEqual(memory["counts"]["features"], 1)
            self.assertEqual(memory["counts"]["screens"], 1)
            self.assertEqual(memory["counts"]["figma_artifacts"], 1)
            self.assertGreaterEqual(memory["counts"]["rag_nodes"], 1)
            source_model_id = db.add_source_model(
                source_type="figma_image",
                feature="login",
                screen="Login Screen",
                model_json={
                    "source_type": "figma_image",
                    "feature": "login",
                    "screen": "Login Screen",
                    "visible_texts": ["Login", "Continue"],
                    "controls": [{"role": "button", "label": "Continue"}],
                    "states": ["default"],
                    "testable_points": ["Continue button should be visible"],
                    "risks": ["Primary action may be disabled before valid input"],
                    "open_questions": [],
                    "confidence": 0.9,
                },
                confidence=0.9,
            )
            rag_hits = Retriever(db).search("Continue button", feature="login", screen="Login Screen", limit=3)
            self.assertTrue(rag_hits)
            self.assertTrue(any("Continue" in hit["content"] for hit in rag_hits))

            generator = CaseGenerator(Retriever(db))
            cases = generator.generate(
                {
                    "feature": "login",
                    "requirement": "Generate happy-path and error-path test cases for login.",
                    "platforms": ["android"],
                    "max_cases": 4,
                }
            )
            self.assertGreaterEqual(len(cases), 2)
            self.assertFalse(any("cross-source" in case.tags for case in cases))
            self.assertTrue(any(ref["type"] == "source_model" for ref in cases[0].source_refs))
            for case in cases:
                case.id = db.add_test_case(case)
                db.update_test_case_status(case.id, "approved")
            duplicate_id = db.add_test_case(cases[0])
            self.assertEqual(duplicate_id, cases[0].id)
            self.assertGreaterEqual(db.memory_summary()["counts"]["case_links"], len(cases))
            db.add_source_file(
                filename="login.png",
                content_type="image/png",
                source_type="figma_image",
                feature="login",
                screen="Login Screen",
                size=42,
                path="/tmp/login.png",
                extracted_text="Image file uploaded: login.png.",
                extraction_status="needs_ai",
                extraction_notes="Image binary stored.",
                document_id=figma_document_id,
            )
            self.assertEqual(db.memory_summary()["counts"]["source_files"], 1)
            db.add_source_model_version(source_model_id, {"feature": "login", "version": 2}, "Updated Figma image model")
            change_set_id = db.create_change_set(
                name="Login iteration",
                summary="Login Figma design changed",
                feature="login",
                screen="Login Screen",
                source_model_ids=[source_model_id],
            )
            db.add_case_suggestion(
                suggestion_type="update_case",
                payload={"case_id": cases[0].id},
                reason="Align with updated source model",
                change_set_id=change_set_id,
                test_case_id=cases[0].id,
            )
            context = db.build_memory_context(feature="login", screen="Login Screen")
            self.assertEqual(context["related_source_models"][0]["feature"], "login")
            self.assertGreaterEqual(len(context["related_test_cases"]), 1)
            summary = db.memory_summary()
            self.assertEqual(summary["counts"]["source_models"], 1)
            self.assertEqual(summary["counts"]["source_model_versions"], 2)
            self.assertGreaterEqual(summary["counts"]["test_case_versions"], 1)
            self.assertEqual(summary["counts"]["change_sets"], 1)
            self.assertEqual(summary["counts"]["case_suggestions"], 1)
            self.assertGreaterEqual(summary["counts"]["rag_nodes"], 4)
            self.assertEqual(summary["rag"]["backend"], "sqlite")

            flow_generator = MaestroFlowGenerator(app_id="com.example.app", flow_dir=Path(directory) / "flows")
            yaml, path = flow_generator.write(cases[0])
            self.assertIn("appId: com.example.app", yaml)
            self.assertIn("launchApp", yaml)
            self.assertTrue(path.exists())
            self.assertEqual(MaestroRunner(enabled=False).run(path)["status"], "passed")

            db.add_run_result(
                run_id=db.create_run("failed login run", "dry-run"),
                test_case_id=cases[0].id,
                status="failed",
                duration_ms=120,
                output="The invalid code message did not appear.",
                artifacts={},
            )
            stats = db.get_case_stats_map()
            self.assertEqual(stats[cases[0].id]["last_status"], "failed")
            self.assertEqual(db.memory_summary()["counts"]["failure_patterns"], 1)
            self.assertGreaterEqual(db.memory_summary()["counts"]["rag_nodes"], summary["counts"]["rag_nodes"])

            selected = RegressionSelector().select(
                db.list_test_cases(),
                {"changed_features": ["login"], "change_summary": "The invalid code message changed."},
                stats,
            )
            self.assertGreaterEqual(len(selected), 1)
            self.assertEqual(selected[0]["case"]["feature"], "login")
            self.assertIn("recently failed", selected[0]["reason"])

    def test_ai_generation_path_with_fake_client(self) -> None:
        class FakeAIClient:
            enabled = True

            def status(self) -> AIStatus:
                return AIStatus(True, "fake", "fake-model", "test")

            def generate_test_cases(self, **kwargs):
                return [
                    {
                        "title": "AI login happy path",
                        "feature": "login",
                        "priority": "P0",
                        "platforms": ["android"],
                        "tags": ["smoke", "regression"],
                        "preconditions": ["The app is installed"],
                        "steps": [
                            {"action": "launch_app", "target_text": "", "target_id": "", "value": "", "note": ""},
                            {"action": "tap", "target_text": "Login", "target_id": "", "value": "", "note": "Open login"},
                        ],
                        "assertions": [
                            {"type": "visible", "target_text": "Home", "target_id": "", "expected": "Home is visible"}
                        ],
                        "source_summary": "Generated from test context.",
                    }
                ]

        with TemporaryDirectory() as directory:
            db = Database(Path(directory) / "app.db")
            generator = CaseGenerator(Retriever(db), ai_client=FakeAIClient())
            cases = generator.generate({"feature": "login", "requirement": "Generate login tests", "platforms": ["android"]})
            self.assertEqual(generator.last_generation_mode, "ai")
            self.assertEqual(cases[0].title, "AI login happy path")
            self.assertIn("ai-generated", cases[0].tags)

    def test_maestro_dry_run_blocks_invalid_flow(self) -> None:
        with TemporaryDirectory() as directory:
            invalid_case = TestCase(
                id=1,
                title="Invalid empty input flow",
                feature="login",
                priority="P1",
                platforms=["android"],
                tags=["regression"],
                preconditions=["The app is installed"],
                steps=[TestStep(action="launch_app"), TestStep(action="input", target={}, value="")],
                assertions=[TestAssertion(type="visible", target={"text": "Login"}, expected="Login is visible")],
                source_refs=[],
            )
            _, path = MaestroFlowGenerator(app_id="com.example.app", flow_dir=Path(directory) / "flows").write(invalid_case)
            result = MaestroRunner(enabled=False).run(path)
            self.assertEqual(result["status"], "blocked")
            self.assertIn("inputText command has an empty value", result["output"])


if __name__ == "__main__":
    unittest.main()
