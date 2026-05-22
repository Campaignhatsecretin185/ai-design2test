from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import sqlite3

from .models import Document, TestCase, dumps, loads, utc_now


DEFAULT_DB_PATH = Path(os.environ.get("APP_DB_PATH", "data/app.db"))


class Database:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        cur = self.connection.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                content TEXT NOT NULL,
                feature TEXT DEFAULT '',
                screen TEXT DEFAULT '',
                tags TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                tokens TEXT NOT NULL,
                feature TEXT DEFAULT '',
                screen TEXT DEFAULT '',
                source_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                feature TEXT NOT NULL,
                priority TEXT NOT NULL,
                platforms TEXT NOT NULL,
                tags TEXT NOT NULL,
                preconditions TEXT NOT NULL,
                steps TEXT NOT NULL,
                assertions TEXT NOT NULL,
                source_refs TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS maestro_flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_case_id INTEGER NOT NULL,
                yaml TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(test_case_id) REFERENCES test_cases(id)
            );

            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS test_run_case_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                test_case_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                output TEXT NOT NULL,
                artifacts TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES test_runs(id),
                FOREIGN KEY(test_case_id) REFERENCES test_cases(id)
            );

            CREATE TABLE IF NOT EXISTS features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                source_count INTEGER NOT NULL DEFAULT 0,
                case_count INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS screens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                feature TEXT DEFAULT '',
                source_count INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS test_case_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_case_id INTEGER NOT NULL,
                link_type TEXT NOT NULL,
                target TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                UNIQUE(test_case_id, link_type, target),
                FOREIGN KEY(test_case_id) REFERENCES test_cases(id)
            );

            CREATE TABLE IF NOT EXISTS failure_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_key TEXT NOT NULL UNIQUE,
                feature TEXT NOT NULL,
                message TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS case_run_stats (
                test_case_id INTEGER PRIMARY KEY,
                total_runs INTEGER NOT NULL DEFAULT 0,
                passed_runs INTEGER NOT NULL DEFAULT 0,
                failed_runs INTEGER NOT NULL DEFAULT 0,
                blocked_runs INTEGER NOT NULL DEFAULT 0,
                last_status TEXT DEFAULT '',
                last_run_at TEXT DEFAULT '',
                failure_count_30d INTEGER NOT NULL DEFAULT 0,
                pass_rate REAL NOT NULL DEFAULT 0,
                flaky_score REAL NOT NULL DEFAULT 0,
                avg_duration_ms REAL NOT NULL DEFAULT 0,
                linked_bug_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(test_case_id) REFERENCES test_cases(id)
            );

            CREATE TABLE IF NOT EXISTS figma_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                figma_url TEXT NOT NULL,
                file_key TEXT DEFAULT '',
                node_id TEXT DEFAULT '',
                screen TEXT NOT NULL,
                raw_context TEXT NOT NULL,
                screen_model TEXT NOT NULL,
                testable_points TEXT NOT NULL,
                document_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS source_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                source_type TEXT NOT NULL,
                feature TEXT DEFAULT '',
                screen TEXT DEFAULT '',
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                extracted_text TEXT NOT NULL,
                extraction_status TEXT NOT NULL,
                extraction_notes TEXT NOT NULL,
                document_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS source_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                feature TEXT NOT NULL,
                screen TEXT DEFAULT '',
                version_label TEXT DEFAULT '',
                model_json TEXT NOT NULL,
                source_refs TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_model_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_model_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                model_json TEXT NOT NULL,
                change_summary TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_model_id) REFERENCES source_models(id)
            );

            CREATE TABLE IF NOT EXISTS test_case_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_case_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                payload TEXT NOT NULL,
                change_reason TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(test_case_id) REFERENCES test_cases(id)
            );

            CREATE TABLE IF NOT EXISTS change_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                feature TEXT DEFAULT '',
                screen TEXT DEFAULT '',
                summary TEXT NOT NULL,
                source_model_ids TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS case_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_set_id INTEGER,
                suggestion_type TEXT NOT NULL,
                test_case_id INTEGER,
                payload TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ai_suggested',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(change_set_id) REFERENCES change_sets(id),
                FOREIGN KEY(test_case_id) REFERENCES test_cases(id)
            );
            """
        )
        self.connection.commit()

    def add_document(self, document: Document, chunks: list[dict[str, Any]]) -> int:
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO documents(title, source_type, content, feature, screen, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.title,
                document.source_type,
                document.content,
                document.feature,
                document.screen,
                dumps(document.tags),
                document.created_at,
            ),
        )
        document_id = int(cur.lastrowid)
        for chunk in chunks:
            cur.execute(
                """
                INSERT INTO document_chunks(document_id, chunk_index, content, tokens, feature, screen, source_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    chunk["chunk_index"],
                    chunk["content"],
                    dumps(chunk["tokens"]),
                    document.feature,
                    document.screen,
                    document.source_type,
                    document.created_at,
                ),
            )
        self.connection.commit()
        self.remember_feature(document.feature, source_delta=1)
        self.remember_screen(document.screen, document.feature)
        return document_id

    def list_documents(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM documents ORDER BY id DESC").fetchall()
        return [self._row_to_document_payload(row) for row in rows]

    def add_figma_artifact(
        self,
        figma_url: str,
        raw_context: Any,
        screen_model: dict[str, Any],
        document_id: int,
    ) -> int:
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO figma_artifacts(
              figma_url, file_key, node_id, screen, raw_context, screen_model,
              testable_points, document_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                figma_url,
                screen_model.get("file_key", ""),
                screen_model.get("node_id", ""),
                screen_model.get("screen", "Figma Screen"),
                dumps(raw_context),
                dumps(screen_model),
                dumps(screen_model.get("testable_points", [])),
                document_id,
                utc_now(),
            ),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def list_figma_artifacts(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM figma_artifacts ORDER BY id DESC").fetchall()
        return [
            dict(row)
            | {
                "screen_model": loads(row["screen_model"], {}),
                "testable_points": loads(row["testable_points"], []),
            }
            for row in rows
        ]

    def add_source_file(
        self,
        filename: str,
        content_type: str,
        source_type: str,
        feature: str,
        screen: str,
        size: int,
        path: str,
        extracted_text: str,
        extraction_status: str,
        extraction_notes: str,
        document_id: int | None,
    ) -> int:
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO source_files(
              filename, content_type, source_type, feature, screen, size, path,
              extracted_text, extraction_status, extraction_notes, document_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                content_type,
                source_type,
                feature,
                screen,
                size,
                path,
                extracted_text,
                extraction_status,
                extraction_notes,
                document_id,
                utc_now(),
            ),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def list_source_files(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, filename, content_type, source_type, feature, screen, size,
                   path, extraction_status, extraction_notes, document_id, created_at
            FROM source_files
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_chunks(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM document_chunks ORDER BY id DESC").fetchall()
        return [dict(row) | {"tokens": loads(row["tokens"], [])} for row in rows]

    def add_test_case(self, case: TestCase) -> int:
        now = utc_now()
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO test_cases(
              title, feature, priority, platforms, tags, preconditions, steps,
              assertions, source_refs, status, version, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.title,
                case.feature,
                case.priority,
                dumps(case.platforms),
                dumps(case.tags),
                dumps(case.preconditions),
                dumps([step.__dict__ for step in case.steps]),
                dumps([assertion.__dict__ for assertion in case.assertions]),
                dumps(case.source_refs),
                case.status,
                case.version,
                now,
                now,
            ),
        )
        self.connection.commit()
        self.remember_feature(case.feature, case_delta=1)
        case_id = int(cur.lastrowid)
        version_payload = case.to_payload()
        version_payload["id"] = case_id
        self.add_test_case_version(case_id, case.version, version_payload, "Initial test case version")
        self.add_test_case_link(case_id, "feature", case.feature, 1.0)
        for tag in case.tags:
            self.add_test_case_link(case_id, "tag", tag, 0.6)
        for source_ref in case.source_refs:
            target = f"{source_ref.get('type')}:{source_ref.get('document_id')}:{source_ref.get('chunk_id')}"
            self.add_test_case_link(case_id, "source", target, float(source_ref.get("score") or 1.0))
        return case_id

    def add_source_model(
        self,
        source_type: str,
        feature: str,
        screen: str,
        model_json: dict[str, Any],
        source_refs: list[dict[str, Any]] | None = None,
        version_label: str = "",
        confidence: float = 0,
        change_summary: str = "Initial source model version",
    ) -> int:
        now = utc_now()
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO source_models(
              source_type, feature, screen, version_label, model_json, source_refs,
              confidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                source_type,
                feature,
                screen,
                version_label,
                dumps(model_json),
                dumps(source_refs or []),
                confidence,
                now,
                now,
            ),
        )
        source_model_id = int(cur.lastrowid)
        self.connection.execute(
            """
            INSERT INTO source_model_versions(source_model_id, version, model_json, change_summary, created_at)
            VALUES (?, 1, ?, ?, ?)
            """,
            (source_model_id, dumps(model_json), change_summary, now),
        )
        self.connection.commit()
        self.remember_feature(feature, source_delta=1)
        self.remember_screen(screen, feature)
        return source_model_id

    def add_source_model_version(
        self,
        source_model_id: int,
        model_json: dict[str, Any],
        change_summary: str = "",
    ) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM source_model_versions WHERE source_model_id = ?",
            (source_model_id,),
        ).fetchone()
        next_version = int(row["version"]) + 1
        now = utc_now()
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO source_model_versions(source_model_id, version, model_json, change_summary, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_model_id, next_version, dumps(model_json), change_summary, now),
        )
        self.connection.execute(
            "UPDATE source_models SET model_json = ?, updated_at = ? WHERE id = ?",
            (dumps(model_json), now, source_model_id),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def list_source_models(self, feature: str = "", screen: str = "", limit: int = 20) -> list[dict[str, Any]]:
        sql = "SELECT * FROM source_models WHERE status = 'active'"
        params: list[Any] = []
        if feature:
            sql += " AND feature = ?"
            params.append(feature)
        if screen:
            sql += " AND screen = ?"
            params.append(screen)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(sql, params).fetchall()
        return [
            dict(row)
            | {
                "model_json": loads(row["model_json"], {}),
                "source_refs": loads(row["source_refs"], []),
            }
            for row in rows
        ]

    def add_test_case_version(
        self,
        test_case_id: int,
        version: int,
        payload: dict[str, Any],
        change_reason: str = "",
    ) -> int:
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO test_case_versions(test_case_id, version, payload, change_reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (test_case_id, version, dumps(payload), change_reason, utc_now()),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def create_change_set(
        self,
        name: str,
        summary: str,
        feature: str = "",
        screen: str = "",
        source_model_ids: list[int] | None = None,
    ) -> int:
        now = utc_now()
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO change_sets(name, feature, screen, summary, source_model_ids, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (name, feature, screen, summary, dumps(source_model_ids or []), now, now),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def add_case_suggestion(
        self,
        suggestion_type: str,
        payload: dict[str, Any],
        reason: str,
        change_set_id: int | None = None,
        test_case_id: int | None = None,
    ) -> int:
        now = utc_now()
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO case_suggestions(
              change_set_id, suggestion_type, test_case_id, payload, reason, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'ai_suggested', ?, ?)
            """,
            (change_set_id, suggestion_type, test_case_id, dumps(payload), reason, now, now),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def build_memory_context(self, feature: str = "", screen: str = "", limit: int = 10) -> dict[str, Any]:
        source_models = self.list_source_models(feature=feature, screen=screen, limit=limit)
        cases = [case.to_payload() for case in self.list_test_cases(feature=feature)[:limit]]
        stats_map = self.get_case_stats_map()
        case_stats = [
            stats_map[int(case["id"])]
            for case in cases
            if int(case["id"]) in stats_map
        ]
        failures_sql = "SELECT * FROM failure_patterns WHERE 1=1"
        params: list[Any] = []
        if feature:
            failures_sql += " AND feature = ?"
            params.append(feature)
        failures_sql += " ORDER BY count DESC, last_seen_at DESC LIMIT ?"
        params.append(limit)
        failures = [dict(row) for row in self.connection.execute(failures_sql, params).fetchall()]
        return {
            "feature": feature,
            "screen": screen,
            "related_source_models": source_models,
            "related_test_cases": cases,
            "case_run_stats": case_stats,
            "failure_patterns": failures,
        }

    def list_test_cases(self, status: str = "", feature: str = "") -> list[TestCase]:
        sql = "SELECT * FROM test_cases WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if feature:
            sql += " AND feature = ?"
            params.append(feature)
        sql += " ORDER BY id DESC"
        rows = self.connection.execute(sql, params).fetchall()
        return [TestCase.from_row(row) for row in rows]

    def get_test_case(self, case_id: int) -> TestCase | None:
        row = self.connection.execute("SELECT * FROM test_cases WHERE id = ?", (case_id,)).fetchone()
        return TestCase.from_row(row) if row else None

    def update_test_case_status(self, case_id: int, status: str) -> None:
        self.connection.execute(
            "UPDATE test_cases SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), case_id),
        )
        self.connection.commit()

    def add_maestro_flow(self, test_case_id: int, yaml: str, path: str) -> int:
        cur = self.connection.cursor()
        cur.execute(
            "INSERT INTO maestro_flows(test_case_id, yaml, path, created_at) VALUES (?, ?, ?, ?)",
            (test_case_id, yaml, path, utc_now()),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def create_run(self, name: str, mode: str) -> int:
        cur = self.connection.cursor()
        cur.execute(
            "INSERT INTO test_runs(name, mode, status, summary, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, mode, "running", "{}", utc_now()),
        )
        self.connection.commit()
        return int(cur.lastrowid)

    def add_run_result(
        self,
        run_id: int,
        test_case_id: int,
        status: str,
        duration_ms: int,
        output: str,
        artifacts: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO test_run_case_results(
              run_id, test_case_id, status, duration_ms, output, artifacts, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, test_case_id, status, duration_ms, output, dumps(artifacts), utc_now()),
        )
        self.connection.commit()
        self.update_case_run_stats(test_case_id, status, duration_ms, output)

    def complete_run(self, run_id: int, status: str, summary: dict[str, Any]) -> None:
        self.connection.execute(
            "UPDATE test_runs SET status = ?, summary = ?, completed_at = ? WHERE id = ?",
            (status, dumps(summary), utc_now(), run_id),
        )
        self.connection.commit()

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        run = self.connection.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            return None
        results = self.connection.execute(
            """
            SELECT r.*, c.title, c.feature, c.priority
            FROM test_run_case_results r
            JOIN test_cases c ON c.id = r.test_case_id
            WHERE r.run_id = ?
            ORDER BY r.id ASC
            """,
            (run_id,),
        ).fetchall()
        return {
            **dict(run),
            "summary": loads(run["summary"], {}),
            "results": [
                dict(row) | {"artifacts": loads(row["artifacts"], {})}
                for row in results
            ],
        }

    def remember_feature(self, name: str, source_delta: int = 0, case_delta: int = 0, description: str = "") -> None:
        name = (name or "").strip()
        if not name:
            return
        now = utc_now()
        existing = self.connection.execute("SELECT id FROM features WHERE name = ?", (name,)).fetchone()
        if existing:
            self.connection.execute(
                """
                UPDATE features
                SET source_count = source_count + ?,
                    case_count = case_count + ?,
                    description = COALESCE(NULLIF(?, ''), description),
                    last_seen_at = ?
                WHERE name = ?
                """,
                (source_delta, case_delta, description, now, name),
            )
        else:
            self.connection.execute(
                """
                INSERT INTO features(name, description, source_count, case_count, last_seen_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, description, source_delta, case_delta, now, now),
            )
        self.connection.commit()

    def remember_screen(self, name: str, feature: str = "") -> None:
        name = (name or "").strip()
        if not name:
            return
        now = utc_now()
        existing = self.connection.execute("SELECT id FROM screens WHERE name = ?", (name,)).fetchone()
        if existing:
            self.connection.execute(
                "UPDATE screens SET feature = COALESCE(NULLIF(?, ''), feature), source_count = source_count + 1, last_seen_at = ? WHERE name = ?",
                (feature, now, name),
            )
        else:
            self.connection.execute(
                "INSERT INTO screens(name, feature, source_count, last_seen_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, feature, 1, now, now),
            )
        self.connection.commit()

    def add_test_case_link(self, test_case_id: int, link_type: str, target: str, weight: float = 1.0) -> None:
        target = (target or "").strip()
        if not target:
            return
        self.connection.execute(
            """
            INSERT INTO test_case_links(test_case_id, link_type, target, weight, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(test_case_id, link_type, target) DO UPDATE SET weight = excluded.weight
            """,
            (test_case_id, link_type, target, weight, utc_now()),
        )
        self.connection.commit()

    def update_case_run_stats(self, test_case_id: int, status: str, duration_ms: int, output: str) -> None:
        now = utc_now()
        row = self.connection.execute(
            "SELECT * FROM case_run_stats WHERE test_case_id = ?",
            (test_case_id,),
        ).fetchone()
        if row:
            total_runs = row["total_runs"] + 1
            passed_runs = row["passed_runs"] + (1 if status == "passed" else 0)
            failed_runs = row["failed_runs"] + (1 if status == "failed" else 0)
            blocked_runs = row["blocked_runs"] + (1 if status == "blocked" else 0)
            avg_duration = ((row["avg_duration_ms"] * row["total_runs"]) + duration_ms) / total_runs
            failure_count_30d = row["failure_count_30d"] + (1 if status in {"failed", "blocked"} else 0)
        else:
            total_runs = 1
            passed_runs = 1 if status == "passed" else 0
            failed_runs = 1 if status == "failed" else 0
            blocked_runs = 1 if status == "blocked" else 0
            avg_duration = duration_ms
            failure_count_30d = 1 if status in {"failed", "blocked"} else 0
        pass_rate = passed_runs / total_runs if total_runs else 0
        flaky_score = min(1.0, (failed_runs + blocked_runs) / total_runs) if total_runs else 0
        self.connection.execute(
            """
            INSERT INTO case_run_stats(
              test_case_id, total_runs, passed_runs, failed_runs, blocked_runs, last_status,
              last_run_at, failure_count_30d, pass_rate, flaky_score, avg_duration_ms,
              linked_bug_count, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(test_case_id) DO UPDATE SET
              total_runs = excluded.total_runs,
              passed_runs = excluded.passed_runs,
              failed_runs = excluded.failed_runs,
              blocked_runs = excluded.blocked_runs,
              last_status = excluded.last_status,
              last_run_at = excluded.last_run_at,
              failure_count_30d = excluded.failure_count_30d,
              pass_rate = excluded.pass_rate,
              flaky_score = excluded.flaky_score,
              avg_duration_ms = excluded.avg_duration_ms,
              updated_at = excluded.updated_at
            """,
            (
                test_case_id,
                total_runs,
                passed_runs,
                failed_runs,
                blocked_runs,
                status,
                now,
                failure_count_30d,
                pass_rate,
                flaky_score,
                avg_duration,
                now,
            ),
        )
        self.connection.commit()
        if status in {"failed", "blocked"}:
            case = self.get_test_case(test_case_id)
            self.remember_failure_pattern(case.feature if case else "", output)

    def remember_failure_pattern(self, feature: str, message: str) -> None:
        message = (message or "").strip().splitlines()[0][:240]
        if not message:
            message = "Unknown failure"
        feature = feature or "general"
        key = f"{feature}:{message.lower()[:120]}"
        now = utc_now()
        existing = self.connection.execute("SELECT id FROM failure_patterns WHERE pattern_key = ?", (key,)).fetchone()
        if existing:
            self.connection.execute(
                "UPDATE failure_patterns SET count = count + 1, last_seen_at = ? WHERE pattern_key = ?",
                (now, key),
            )
        else:
            self.connection.execute(
                """
                INSERT INTO failure_patterns(pattern_key, feature, message, count, last_seen_at, created_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (key, feature, message, now, now),
            )
        self.connection.commit()

    def get_case_stats_map(self) -> dict[int, dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM case_run_stats").fetchall()
        return {int(row["test_case_id"]): dict(row) for row in rows}

    def memory_summary(self) -> dict[str, Any]:
        counts = {
            "features": self.connection.execute("SELECT COUNT(*) AS value FROM features").fetchone()["value"],
            "screens": self.connection.execute("SELECT COUNT(*) AS value FROM screens").fetchone()["value"],
            "case_links": self.connection.execute("SELECT COUNT(*) AS value FROM test_case_links").fetchone()["value"],
            "failure_patterns": self.connection.execute("SELECT COUNT(*) AS value FROM failure_patterns").fetchone()["value"],
            "case_run_stats": self.connection.execute("SELECT COUNT(*) AS value FROM case_run_stats").fetchone()["value"],
            "figma_artifacts": self.connection.execute("SELECT COUNT(*) AS value FROM figma_artifacts").fetchone()["value"],
            "source_files": self.connection.execute("SELECT COUNT(*) AS value FROM source_files").fetchone()["value"],
            "source_models": self.connection.execute("SELECT COUNT(*) AS value FROM source_models").fetchone()["value"],
            "source_model_versions": self.connection.execute("SELECT COUNT(*) AS value FROM source_model_versions").fetchone()["value"],
            "test_case_versions": self.connection.execute("SELECT COUNT(*) AS value FROM test_case_versions").fetchone()["value"],
            "change_sets": self.connection.execute("SELECT COUNT(*) AS value FROM change_sets").fetchone()["value"],
            "case_suggestions": self.connection.execute("SELECT COUNT(*) AS value FROM case_suggestions").fetchone()["value"],
        }
        features = [dict(row) for row in self.connection.execute("SELECT * FROM features ORDER BY last_seen_at DESC LIMIT 20").fetchall()]
        screens = [dict(row) for row in self.connection.execute("SELECT * FROM screens ORDER BY last_seen_at DESC LIMIT 20").fetchall()]
        failures = [dict(row) for row in self.connection.execute("SELECT * FROM failure_patterns ORDER BY count DESC, last_seen_at DESC LIMIT 20").fetchall()]
        stats = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT s.*, c.title, c.feature, c.priority
                FROM case_run_stats s
                JOIN test_cases c ON c.id = s.test_case_id
                ORDER BY s.updated_at DESC
                LIMIT 20
                """
            ).fetchall()
        ]
        figma_artifacts = [
            dict(row)
            for row in self.connection.execute(
                "SELECT id, figma_url, file_key, node_id, screen, document_id, created_at FROM figma_artifacts ORDER BY id DESC LIMIT 20"
            ).fetchall()
        ]
        source_files = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT id, filename, content_type, source_type, feature, screen,
                       size, extraction_status, extraction_notes, document_id, created_at
                FROM source_files
                ORDER BY id DESC
                LIMIT 20
                """
            ).fetchall()
        ]
        source_models = self.list_source_models(limit=20)
        change_sets = [
            dict(row) | {"source_model_ids": loads(row["source_model_ids"], [])}
            for row in self.connection.execute(
                "SELECT * FROM change_sets ORDER BY updated_at DESC LIMIT 20"
            ).fetchall()
        ]
        case_suggestions = [
            dict(row) | {"payload": loads(row["payload"], {})}
            for row in self.connection.execute(
                "SELECT * FROM case_suggestions ORDER BY updated_at DESC LIMIT 20"
            ).fetchall()
        ]
        return {
            "counts": counts,
            "features": features,
            "screens": screens,
            "failure_patterns": failures,
            "case_run_stats": stats,
            "figma_artifacts": figma_artifacts,
            "source_files": source_files,
            "source_models": source_models,
            "change_sets": change_sets,
            "case_suggestions": case_suggestions,
        }

    def _row_to_document_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["tags"] = loads(row["tags"], [])
        payload["content_preview"] = row["content"][:240]
        return payload
