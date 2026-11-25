from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from codex_exporter.cli import main
from codex_exporter.config import DEFAULTS
from codex_exporter.extract import read_session_metadata, retain_recent_turns
from codex_exporter.organize import session_date
from codex_exporter.output import (
    format_markdown_activity_transcript,
    format_markdown_transcript,
)
from codex_exporter.products import PRESETS, PRODUCTS, resolve_preset


def write_session(
    path: Path,
    session_id: str,
    timestamp: str = "2026-11-12T10:00:00Z",
    cwd: object = "/work/example-project",
    parent_thread_id: str | None = None,
    messages: tuple[tuple[str, str], ...] = (),
    include_meta: bool = True,
) -> None:
    payload = {"id": session_id, "timestamp": timestamp}
    if cwd is not None:
        payload["cwd"] = cwd
    if parent_thread_id:
        payload["parent_thread_id"] = parent_thread_id

    lines = []
    if include_meta:
        lines.append(
            json.dumps(
                {
                    "type": "session_meta",
                    "timestamp": timestamp,
                    "payload": payload,
                }
            )
        )
    for role, text in messages:
        lines.append(
            json.dumps(
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "message",
                        "role": role,
                        "content": [{"type": "input_text", "text": text}],
                    },
                }
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mirrored_session(path: Path, session_id: str, text: str) -> None:
    timestamp = "2026-11-12T10:00:00Z"
    lines = [
        json.dumps(
            {
                "type": "session_meta",
                "timestamp": timestamp,
                "payload": {
                    "id": session_id,
                    "timestamp": timestamp,
                    "cwd": "/work/mirror",
                },
            }
        ),
        json.dumps(
            {
                "type": "response_item",
                "timestamp": timestamp,
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        ),
        json.dumps(
            {
                "type": "event_msg",
                "timestamp": timestamp,
                "payload": {"type": "user_message", "message": text},
            }
        ),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup_export(root: Path, sessions: list[tuple[str, str, dict]]) -> tuple[Path, Path, Path]:
    source = root / "codex"
    sessions_dir = source / "sessions" / "2026" / "11"
    for name, session_id, options in sessions:
        write_session(sessions_dir / f"{name}.jsonl", session_id, **options)
    output = root / "exports"
    config = root / "codex_export.ini"
    config.write_text(
        f"[codex]\ndir = {source}\n[output]\ndir = {output}\n",
        encoding="utf-8",
    )
    return source, output, config


def run_cli(args: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        result = main(args)
    return result, stdout.getvalue()


class CliFeatureTests(unittest.TestCase):
    def test_default_output_directory_is_generic(self) -> None:
        self.assertEqual(DEFAULTS["output_dir"], "./exports")

    def test_list_sessions_is_read_only_and_honors_last(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "codex"
            sessions_dir = source / "sessions" / "2026"
            for session_id, timestamp in (
                ("ses_old", "2026-11-10T10:00:00Z"),
                ("ses_new", "2026-11-12T10:00:00Z"),
            ):
                write_session(
                    sessions_dir / f"{session_id}.jsonl",
                    session_id,
                    timestamp=timestamp,
                )
            config = root / "codex_export.ini"
            config.write_text(
                f"[codex]\ndir = {source}\n[output]\ndir = {root / 'exports'}\n",
                encoding="utf-8",
            )

            result, stdout = run_cli(
                ["--config", str(config), "--list-sessions", "--last", "1", "--json"]
            )

            payload = json.loads(stdout)
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

    def test_session_date_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            epoch = datetime(2022, 3, 3, tzinfo=timezone.utc).timestamp()

            mtime_path = root / "2020-01-01_session.jsonl"
            write_session(mtime_path, "mtime", include_meta=False)
            os.utime(mtime_path, (epoch, epoch))
            self.assertEqual(session_date({"timestamp": "2021-02-02T00:00:00Z"}, mtime_path), "2022-03-03")

            meta_path = root / "2020-01-01_meta.jsonl"
            write_session(meta_path, "meta", timestamp="2021-02-02T00:00:00Z")
            os.utime(meta_path, (1, 1))
            metadata = read_session_metadata(meta_path)

            filename_path = root / "2020-01-01_filename.jsonl"
            write_session(filename_path, "filename", include_meta=False)
            os.utime(filename_path, (1, 1))

            unknown_path = root / "no-date.jsonl"
            write_session(unknown_path, "unknown", include_meta=False)
            os.utime(unknown_path, (1, 1))

            with mock.patch(
                "codex_exporter.organize._file_modified_at", return_value=None
            ):
                self.assertEqual(session_date(metadata, meta_path), "2021-02-02")
                self.assertEqual(session_date({}, filename_path), "2020-01-01")
                self.assertEqual(session_date({}, unknown_path), "unknown-date")

    def test_list_presets_describes_distinct_products(self) -> None:
        self.assertIn("complete", PRESETS)
        self.assertNotIn("archive", PRESETS)
        self.assertNotIn("rag", PRODUCTS)
        self.assertEqual(
            [product.name for product in resolve_preset("complete")],
            ["faithful", "transcript", "memory", "corpus"],
        )
        self.assertEqual([product.name for product in resolve_preset("memory")], ["memory"])
        self.assertEqual([product.name for product in resolve_preset("corpus")], ["corpus"])

        result, stdout = run_cli(["--list-presets", "--json"])
        payload = json.loads(stdout)
        descriptions = {item["name"]: item["description"] for item in payload["products"]}
        recipes = {item["name"]: item["recipe"] for item in payload["presets"]}
        self.assertEqual(result, 0)
        self.assertIn("Session-structured", descriptions["memory"])
        self.assertIn("Flattened", descriptions["corpus"])
        self.assertEqual(recipes["complete"], ["faithful", "transcript", "memory", "corpus"])
        self.assertEqual(recipes["memory"], ["memory"])
        self.assertEqual(recipes["corpus"], ["corpus"])

    def test_project_folders_hold_session_files_without_session_or_date_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    (
                        "one",
                        "ses_11111111",
                        {"cwd": "/work/example-project", "messages": (("user", "hello"),)},
                    ),
                    (
                        "two",
                        "ses_22222222",
                        {"cwd": "/work/example-project", "messages": (("user", "hi"),)},
                    ),
                ],
            )

            result, _ = run_cli(
                [str(source), "--config", str(config), "--preset", "complete", "--json"]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            self.assertRegex(run_dir.name, r"^\d{8}T\d{6}Z_complete$")
            project_dirs = [path for path in run_dir.iterdir() if path.is_dir()]
            self.assertEqual(len(project_dirs), 1)
            project_dir = project_dirs[0]
            self.assertRegex(
                project_dir.name,
                r"^\d{4}-\d{2}-\d{2}_example-project_[0-9a-f]{12}$",
            )
            for path in project_dir.iterdir():
                self.assertTrue(path.is_file())

            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["product_artifacts"], {})
            self.assertEqual(metadata["counts"]["files_written"], 7)
            self.assertEqual(
                metadata["counts"]["product_counts"],
                {
                    "faithful": 2,
                    "transcript": 2,
                    "memory": 2,
                    "corpus": 2,
                },
            )
            for product_name, paths in metadata["artifacts"].items():
                self.assertEqual(len(paths), 1 if product_name == "corpus" else 2)
                for relative in paths:
                    if product_name == "corpus":
                        self.assertEqual(relative, "corpus.jsonl")
                    else:
                        self.assertTrue(relative.startswith(f"{project_dir.name}/"))
                    self.assertFalse(Path(relative).is_absolute())

            root_index = (run_dir / "index.md").read_text(encoding="utf-8")
            memory_index = (run_dir / "index.memory.md").read_text(encoding="utf-8")
            self.assertIn(f"{project_dir.name}/", root_index)
            self.assertIn(f"{project_dir.name}/", memory_index)
            self.assertNotIn("](\\", root_index)
            self.assertFalse(list(run_dir.glob("*/*/*")))

    def test_no_project_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    (
                        "missing",
                        "ses_33333333",
                        {"cwd": None, "messages": (("user", "hello"),)},
                    )
                ],
            )

            result, _ = run_cli(
                [str(source), "--config", str(config), "--preset", "complete", "--json"]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            project_dirs = [path for path in run_dir.iterdir() if path.is_dir()]
            self.assertEqual(len(project_dirs), 1)
            self.assertRegex(
                project_dirs[0].name,
                r"^\d{4}-\d{2}-\d{2}_no-project_[0-9a-f]{12}$",
            )
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["sessions"][0]["project"], "no-project")
            self.assertRegex(
                metadata["sessions"][0]["project_slug"],
                r"^no-project_[0-9a-f]{12}$",
            )
            for product_name, paths in metadata["artifacts"].items():
                for relative in paths:
                    if product_name == "corpus":
                        self.assertEqual(relative, "corpus.jsonl")
                    else:
                        self.assertTrue(relative.startswith(f"{project_dirs[0].name}/"))

    def test_dry_run_reports_project_relative_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    (
                        "one",
                        "ses_44444444",
                        {"cwd": "C:\\work\\dry-project", "messages": (("user", "hello"),)},
                    )
                ],
            )

            result, stdout = run_cli(
                [str(source), "--config", str(config), "--preset", "complete", "--dry-run"]
            )

            self.assertEqual(result, 0)
            self.assertIn("dry-project_", stdout)
            self.assertIn(".memory.jsonl", stdout)
            self.assertIn("corpus.jsonl", stdout)
            self.assertRegex(stdout, r"corpus: -> [^\n]*Z_complete/corpus\.jsonl")
            self.assertRegex(stdout, r"Would write: [^\n]*Z_complete/corpus\.jsonl")
            self.assertIsNone(
                re.search(r"Would write: [^\n]*Z_complete/[^/]+\.memory\.jsonl", stdout)
            )
            self.assertFalse(output.exists())

    def test_memory_nests_subagents_and_corpus_flattens_child_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    (
                        "root",
                        "root-1",
                        {
                            "cwd": "/work/nested",
                            "messages": (
                                ("user", "root question"),
                                ("assistant", "root answer"),
                            ),
                        },
                    ),
                    (
                        "child",
                        "child-1",
                        {
                            "cwd": "/work/nested",
                            "parent_thread_id": "root-1",
                            "messages": (
                                ("user", "child question"),
                                ("assistant", "child answer"),
                            ),
                        },
                    ),
                    (
                        "solo",
                        "solo-1",
                        {
                            "cwd": None,
                            "messages": (("user", "solo question"),),
                        },
                    ),
                ],
            )

            result, _ = run_cli(
                [str(source), "--config", str(config), "--preset", "complete", "--json"]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["counts"]["product_counts"]["memory"], 2)
            self.assertEqual(metadata["counts"]["product_counts"]["corpus"], 2)

            memory_files = sorted(run_dir.rglob("*.memory.jsonl"))
            corpus_file = run_dir / "corpus.jsonl"
            self.assertEqual(len(memory_files), 2)
            self.assertTrue(corpus_file.is_file())
            self.assertFalse(any("child" in path.name for path in memory_files + [corpus_file]))

            memory_records = [json.loads(path.read_text(encoding="utf-8")) for path in memory_files]
            memory_by_id = {record["session_id"]: record for record in memory_records}
            self.assertEqual(set(memory_by_id), {"root-1", "solo-1"})
            root_memory = memory_by_id["root-1"]
            self.assertEqual(root_memory["record_type"], "session_memory")
            self.assertEqual(len(root_memory["children"]), 1)
            child_memory = root_memory["children"][0]
            self.assertEqual(child_memory["session_id"], "child-1")
            self.assertEqual(child_memory["record_type"], "session_memory")
            for key in ("events", "messages", "parts", "usage", "children"):
                self.assertIn(key, child_memory)
            self.assertIn("child question", [message["text"] for message in child_memory["messages"]])
            self.assertEqual(memory_by_id["solo-1"]["children"], [])

            corpus_records = [
                json.loads(line)
                for line in corpus_file.read_text(encoding="utf-8").splitlines()
                if line
            ]
            corpus_by_id = {record["session_id"]: record for record in corpus_records}
            self.assertEqual(set(corpus_by_id), {"root-1", "solo-1"})
            root_corpus = corpus_by_id["root-1"]
            self.assertEqual(root_corpus["record_type"], "corpus_document")
            self.assertIsInstance(root_corpus["text"], str)
            self.assertIsInstance(root_corpus["content"], str)
            self.assertIn("root question", root_corpus["text"])
            self.assertIn("child question", root_corpus["text"])
            self.assertIn("child answer", root_corpus["content"])
            self.assertEqual(root_corpus["child_session_ids"], ["child-1"])
            self.assertNotIn("child question", corpus_by_id["solo-1"]["text"])

            child_record = next(
                session
                for session in metadata["sessions"]
                if session["id"] == "child-1"
            )
            self.assertEqual(child_record["nested_in"], "root-1")
            self.assertNotIn("memory", child_record["outputs"])
            self.assertNotIn("corpus", child_record["outputs"])

    def test_same_basename_roots_get_distinct_project_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    (
                        "posix",
                        "ses_posix01",
                        {"cwd": "/one/shared", "messages": (("user", "posix"),)},
                    ),
                    (
                        "windows",
                        "ses_windows01",
                        {"cwd": "C:\\two\\shared", "messages": (("user", "windows"),)},
                    ),
                ],
            )

            result, _ = run_cli(
                [str(source), "--config", str(config), "--preset", "complete", "--json"]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            project_dirs = [path.name for path in run_dir.iterdir() if path.is_dir()]
            self.assertEqual(len(project_dirs), 2)
            self.assertEqual(
                [name.split("_")[1] for name in project_dirs],
                ["shared", "shared"],
            )
            self.assertTrue(
                all(re.fullmatch(r"\d{4}-\d{2}-\d{2}_shared_[0-9a-f]{12}", name) for name in project_dirs)
            )
            self.assertNotEqual(project_dirs[0], project_dirs[1])

    def test_memory_preserves_nested_subagent_levels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    ("root", "tree-root", {"cwd": "/work/tree", "messages": (("user", "top"),)}),
                    (
                        "child",
                        "tree-child",
                        {
                            "cwd": "/work/tree",
                            "parent_thread_id": "tree-root",
                            "messages": (("user", "middle"),),
                        },
                    ),
                    (
                        "grandchild",
                        "tree-grandchild",
                        {
                            "cwd": "/work/tree",
                            "parent_thread_id": "tree-child",
                            "messages": (("user", "deep"),),
                        },
                    ),
                ],
            )

            result, _ = run_cli(
                [str(source), "--config", str(config), "--preset", "memory", "--json"]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            memory_files = list(run_dir.rglob("*.memory.jsonl"))
            self.assertEqual(len(memory_files), 1)
            record = json.loads(memory_files[0].read_text(encoding="utf-8"))
            self.assertEqual(record["session_id"], "tree-root")
            self.assertEqual(len(record["children"]), 1)
            child = record["children"][0]
            self.assertEqual(child["session_id"], "tree-child")
            self.assertEqual(len(child["children"]), 1)
            self.assertEqual(child["children"][0]["session_id"], "tree-grandchild")

    def test_complete_writes_titled_session_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "codex"
            sessions_dir = source / "sessions" / "2026" / "11"
            sessions_dir.mkdir(parents=True, exist_ok=True)
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
                    + "".join(
                        json.dumps(
                            {
                                "type": "response_item",
                                "timestamp": timestamp,
                                "payload": {
                                    "type": "message",
                                    "role": role,
                                    "content": [{"type": "input_text", "text": text}],
                                },
                            }
                        )
                        + "\n"
                        for role, text in (("user", "hello"), ("assistant", "world"))
                    )
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
            ):
                result, _ = run_cli(
                    [
                        str(source),
                        "--config",
                        str(config),
                        "--preset",
                        "complete",
                        "--quiet",
                    ]
                )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["product_artifacts"], {})
            self.assertEqual(metadata["counts"]["files_written"], 7)

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
            self.assertFalse(list(run_dir.glob("*.memory.jsonl")))
            self.assertTrue((run_dir / "corpus.jsonl").is_file())

    def test_mirrored_message_records_are_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "codex"
            write_mirrored_session(
                source / "sessions" / "2026" / "11" / "mirror.jsonl",
                "mirror-1",
                "mirrored prompt",
            )
            output = root / "exports"
            config = root / "codex_export.ini"
            config.write_text(
                f"[codex]\ndir = {source}\n[output]\ndir = {output}\n",
                encoding="utf-8",
            )

            result, _ = run_cli(
                [str(source), "--config", str(config), "--preset", "complete", "--quiet"]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            memory = json.loads(
                next(run_dir.rglob("*.memory.jsonl")).read_text(encoding="utf-8")
            )
            corpus = json.loads(
                (run_dir / "corpus.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(len(memory["events"]), 1)
            self.assertEqual([message["text"] for message in memory["messages"]], ["mirrored prompt"])
            self.assertEqual(len(memory["parts"]), 1)
            self.assertEqual(corpus["message_count"], 1)
            self.assertEqual(corpus["content"].splitlines(), ["mirrored prompt"])

    def test_recent_turns_filters_structured_messages_and_parts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    (
                        "turns",
                        "turns-1",
                        {
                            "cwd": "/work/turns",
                            "messages": (
                                ("user", "first prompt"),
                                ("assistant", "first answer"),
                                ("user", "second prompt"),
                                ("assistant", "second answer"),
                                ("user", "third prompt"),
                                ("assistant", "third answer"),
                            ),
                        },
                    )
                ],
            )

            result, _ = run_cli(
                [
                    str(source),
                    "--config",
                    str(config),
                    "--products",
                    "memory",
                    "corpus",
                    "--recent-turns",
                    "1",
                    "--quiet",
                ]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            memory = json.loads(
                next(run_dir.rglob("*.memory.jsonl")).read_text(encoding="utf-8")
            )
            corpus = json.loads(
                (run_dir / "corpus.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [event.get("text") for event in memory["events"]],
                ["third prompt", "third answer"],
            )
            self.assertEqual(
                [message["text"] for message in memory["messages"]],
                ["third prompt", "third answer"],
            )
            self.assertEqual(
                [part.get("text") for part in memory["parts"]],
                ["third prompt", "third answer"],
            )
            self.assertEqual(corpus["message_count"], 2)
            self.assertIn("third prompt", corpus["content"])
            self.assertNotIn("first prompt", corpus["content"])
            self.assertNotIn("second prompt", corpus["content"])

    def test_sessions_without_content_have_no_empty_structured_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [("empty", "empty-1", {"cwd": "/work/empty"})],
            )

            result, _ = run_cli(
                [str(source), "--config", str(config), "--preset", "complete", "--json"]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["counts"]["product_counts"],
                {"faithful": 1, "transcript": 0, "memory": 0, "corpus": 0},
            )
            self.assertEqual(metadata["counts"]["files_written"], 1)
            self.assertEqual(metadata["counts"]["product_omitted_counts"]["memory"], 1)
            self.assertEqual(metadata["counts"]["product_omitted_counts"]["corpus"], 1)
            self.assertEqual(metadata["artifacts"].get("memory", []), [])
            self.assertEqual(metadata["artifacts"].get("corpus", []), [])
            record = metadata["sessions"][0]
            self.assertIn("memory", record["skipped_products"])
            self.assertIn("corpus", record["skipped_products"])
            self.assertFalse(list(run_dir.rglob("*.memory.jsonl")))
            self.assertFalse((run_dir / "corpus.jsonl").exists())

    def test_orphan_subagent_is_emitted_without_root_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output, config = setup_export(
                root,
                [
                    (
                        "orphan",
                        "orphan-1",
                        {
                            "cwd": "/work/orphans",
                            "parent_thread_id": "missing-parent",
                            "messages": (("user", "orphan prompt"),),
                        },
                    ),
                    (
                        "unrelated",
                        "root-1",
                        {
                            "cwd": "/work/orphans",
                            "messages": (("user", "unrelated prompt"),),
                        },
                    ),
                ],
            )

            result, _ = run_cli(
                [
                    str(source),
                    "--config",
                    str(config),
                    "--products",
                    "memory",
                    "corpus",
                    "--quiet",
                ]
            )

            self.assertEqual(result, 0)
            run_dir = next(output.iterdir())
            memory_files = sorted(run_dir.rglob("*.memory.jsonl"))
            corpus_file = run_dir / "corpus.jsonl"
            self.assertEqual(len(memory_files), 2)
            self.assertTrue(corpus_file.is_file())
            memory_records = {
                json.loads(path.read_text(encoding="utf-8"))["session_id"]: json.loads(
                    path.read_text(encoding="utf-8")
                )
                for path in memory_files
            }
            corpus_records = {
                json.loads(line)["session_id"]: json.loads(line)
                for line in corpus_file.read_text(encoding="utf-8").splitlines()
                if line
            }
            self.assertEqual(set(memory_records), {"orphan-1", "root-1"})
            self.assertTrue(memory_records["orphan-1"]["parent_unresolved"])
            self.assertEqual(
                memory_records["orphan-1"]["parent_thread_id"], "missing-parent"
            )
            self.assertEqual(memory_records["orphan-1"]["children"], [])
            self.assertNotIn("parent_unresolved", memory_records["root-1"])
            self.assertTrue(corpus_records["orphan-1"]["parent_unresolved"])
            self.assertNotIn("unrelated prompt", corpus_records["orphan-1"]["content"])
            self.assertNotIn("orphan prompt", corpus_records["root-1"]["content"])
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            orphan_record = next(
                session for session in metadata["sessions"] if session["id"] == "orphan-1"
            )
            self.assertTrue(orphan_record["parent_unresolved"])


if __name__ == "__main__":
    unittest.main()
