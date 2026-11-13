from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from codex_exporter.cli import main
from codex_exporter.config import DEFAULTS
from codex_exporter.extract import retain_recent_turns
from codex_exporter.output import (
    format_markdown_activity_transcript,
    format_markdown_transcript,
)


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


if __name__ == "__main__":
    unittest.main()