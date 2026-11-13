from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codex_exporter.cli import main
from codex_exporter.config import DEFAULTS
from codex_exporter.extract import retain_recent_turns
from codex_exporter.output import (
    format_markdown_activity_transcript,
    format_markdown_transcript,
)
from codex_exporter.products import PRESETS, PRODUCTS, resolve_preset


class CliFeatureTests(unittest.TestCase):
    def test_default_output_directory_is_generic(self) -> None:
        self.assertEqual(DEFAULTS["output_dir"], "./exports")

    def test_list_sessions_is_read_only_and_honors_last(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "codex"
            sessions_dir = source / "sessions" / "2026"
            sessions_dir.mkdir(parents=True)
            for session_id, timestamp in (
                ("ses_old", "2026-11-10T10:00:00Z"),
                ("ses_new", "2026-11-12T10:00:00Z"),
            ):
                path = sessions_dir / f"{session_id}.jsonl"
                path.write_text(
                    json.dumps(
                        {
                            "type": "session_meta",
                            "timestamp": timestamp,
                            "payload": {
                                "id": session_id,
                                "timestamp": timestamp,
                                "cwd": "/work/example-project",
                            },
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            config = root / "codex_export.ini"
            config.write_text(
                f"[codex]\ndir = {source}\n[output]\ndir = {root / 'exports'}\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(
                    ["--config", str(config), "--list-sessions", "--last", "1", "--json"]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(payload["sessions_found"], 1)
            self.assertEqual(payload["sessions"][0]["id"], "ses_new")
            self.assertFalse((root / "exports").exists())

    def test_recent_turns_keeps_developer_context_and_latest_turn(self) -> None:
        events = [
            {"kind": "message", "role": "developer", "text": "context"},
            {"kind": "message", "role": "user", "text": "first"},
            {"kind": "message", "role": "assistant", "text": "answer one"},
            {"kind": "tool_output", "output": "result one"},
            {"kind": "message", "role": "user", "text": "second"},
            {"kind": "message", "role": "assistant", "text": "answer two"},
            {"kind": "tool_output", "output": "result two"},
        ]

        retained = retain_recent_turns(events, 1)

        self.assertEqual(
            [event.get("text") or event.get("output") for event in retained],
            ["context", "second", "answer two", "result two"],
        )

    def test_markdown_transcripts_do_not_repeat_codex_history_heading(self) -> None:
        message = {"role": "user", "text": "hello"}
        self.assertNotIn("Codex History", format_markdown_transcript([message]))
        activity = format_markdown_activity_transcript(
            [{"kind": "message", **message}]
        )
        self.assertNotIn("Codex History", activity)
        self.assertIn("## User", activity)

    def test_complete_preset_has_product_specific_policies(self) -> None:
        self.assertIn("complete", PRESETS)
        self.assertIn("source", PRESETS)
        self.assertNotIn("archive", PRESETS)
        self.assertNotIn("rag", PRESETS)
        self.assertIn("corpus", PRODUCTS)
        self.assertNotIn("rag", PRODUCTS)

        products = resolve_preset("complete")
        self.assertEqual(
            [product.name for product in products],
            ["faithful", "transcript", "memory", "corpus"],
        )
        corpus = products[-1]
        self.assertEqual(corpus.developer, "exclude")
        self.assertTrue(corpus.message_only)

    def test_complete_writes_run_level_jsonl_and_titled_session_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "codex"
            sessions_dir = source / "sessions" / "2026" / "11"
            sessions_dir.mkdir(parents=True)
            session_specs = [
                ("ses_12345678", "A useful title", "2026-11-12T10:00:00Z"),
                ("ses_87654321", "Another title", "2026-11-13T10:00:00Z"),
            ]
            raw_sources = {}
            index_records = []
            for session_id, title, timestamp in session_specs:
                raw_source = (
                    json.dumps(
                        {
                            "type": "session_meta",
                            "timestamp": timestamp,
                            "payload": {
                                "id": session_id,
                                "timestamp": timestamp,
                                "cwd": "/work/example-project",
                            },
                        }
                    )
                    + "\n"
                )
                (sessions_dir / f"{session_id}.jsonl").write_text(
                    raw_source,
                    encoding="utf-8",
                )
                raw_sources[session_id] = raw_source
                index_records.append({"id": session_id, "thread_name": title})
            (source / "session_index.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in index_records),
                encoding="utf-8",
            )
            output = root / "exports"
            config = root / "codex_export.ini"
            config.write_text(
                f"[codex]\ndir = {source}\n[output]\ndir = {output}\n",
                encoding="utf-8",
            )
            events = [
                {"kind": "message", "role": "developer", "text": "developer context"},
                {"kind": "message", "role": "user", "text": "hello"},
                {"kind": "message", "role": "assistant", "text": "world"},
                {"kind": "tool_output", "role": "assistant", "output": "result"},
            ]

            with mock.patch(
                "codex_exporter.cli.extract_session_events_from_jsonl",
                return_value=events,
            ), contextlib.redirect_stdout(io.StringIO()):
                result = main(
                    [str(source), "--config", str(config), "--preset", "complete", "--quiet"]
                )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema_version"], 8)
            self.assertEqual(metadata["product_artifacts"], {
                "memory": "memory.jsonl",
                "corpus": "corpus.jsonl",
            })
            self.assertEqual(metadata["counts"]["files_written"], 6)

            memory_text = (run_dir / "memory.jsonl").read_text(encoding="utf-8")
            corpus_text = (run_dir / "corpus.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("\n\n", memory_text)
            self.assertNotIn("\n\n", corpus_text)
            memory_lines = [json.loads(line) for line in memory_text.splitlines()]
            corpus_lines = [json.loads(line) for line in corpus_text.splitlines()]
            self.assertEqual(
                {line["session_id"] for line in memory_lines},
                set(raw_sources),
            )
            self.assertEqual(
                {line["session_title"] for line in corpus_lines},
                {record["thread_name"] for record in index_records},
            )
            self.assertIn("developer", {line.get("role") for line in memory_lines})
            self.assertNotIn("developer", {line.get("role") for line in corpus_lines})

            transcript_files = list(run_dir.glob("*/*.transcript.md"))
            self.assertEqual(len(transcript_files), len(session_specs))
            markdown = [path.read_text(encoding="utf-8") for path in transcript_files]
            for _, title, _ in session_specs:
                self.assertTrue(any(f'title: "{title}"' in text for text in markdown))
                self.assertTrue(any(f"# {title}" in text for text in markdown))
            faithful_files = list(run_dir.glob("*/*.faithful.jsonl"))
            self.assertEqual(len(faithful_files), len(raw_sources))
            self.assertEqual(
                {path.read_text(encoding="utf-8") for path in faithful_files},
                set(raw_sources.values()),
            )
            self.assertFalse(list(run_dir.glob("*/*.memory.jsonl")))
            self.assertFalse(list(run_dir.glob("*/*.corpus.jsonl")))


if __name__ == "__main__":
    unittest.main()