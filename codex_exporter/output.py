"""Output formatting for Codex export products.

Formats Markdown and derived JSONL products. The faithful product copies its
source JSONL directly in the CLI.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def format_markdown_transcript(
    messages: List[dict],
    filename: str = "session",
    include_timestamps: bool = True,
    show_role: bool = True,
    title: Optional[str] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Format messages as a Markdown transcript.
    
    Args:
        messages: List of message dicts with 'role', 'timestamp', 'text' keys
        filename: Session filename for the header
        include_timestamps: Whether to include timestamps
        show_role: Whether to show role labels (USER/CODEX)
    
    Returns:
        Markdown-formatted string
    """
    lines = _markdown_frontmatter(filename, title, session_metadata)
    
    # Keep the original chronological order: user/assistant turns interleaved.
    for msg in messages:
        role = msg.get("role")
        if not show_role:
            header = ">"
        else:
            labels = {
                "user": "User",
                "assistant": "Codex",
                "developer": "Developer instruction",
            }
            label = labels.get(role, str(role or "Message"))
            header = f"> **{label}**"

        if include_timestamps and msg.get("timestamp"):
            header += f" · {msg['timestamp']}"

        lines.append(header)
        text = str(msg.get("text", ""))
        quoted_lines = [f"> {line}" if line else ">" for line in text.splitlines()]
        lines.extend(quoted_lines or [">"])
        lines.append("")
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines).rstrip() + "\n"


def _code_block(text: str, language: str = "text") -> List[str]:
    """Return a fenced code block whose fence cannot be closed by its content."""
    longest = max((len(match) for match in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}{language}", text, fence]


def _markdown_frontmatter(
    filename: str,
    title: Optional[str],
    session_metadata: Optional[Dict[str, Any]],
) -> List[str]:
    metadata = session_metadata or {}
    resolved_title = str(title or metadata.get("thread_name") or filename or "session")
    heading = " ".join(resolved_title.splitlines()).strip() or "session"
    fields = [
        ("title", resolved_title),
        ("session_id", metadata.get("id")),
        ("date", metadata.get("started_at")),
        ("project", metadata.get("project")),
        ("source_file", metadata.get("source_file")),
    ]
    lines = ["---"]
    lines.extend(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in fields
        if value not in (None, "")
    )
    lines.extend(["---", "", f"# {heading}", ""])
    return lines


def format_markdown_activity_transcript(
    events: List[dict],
    filename: str = "session",
    include_timestamps: bool = True,
    title: Optional[str] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Format messages and tool activity as one chronological Markdown transcript."""
    lines = _markdown_frontmatter(filename, title, session_metadata)

    for event in events:
        kind = event.get("kind")
        timestamp = event.get("timestamp")
        if kind == "message":
            role = event.get("role")
            labels = {
                "user": "User",
                "assistant": "Codex",
                "developer": "Developer instruction",
            }
            label = labels.get(role, str(role or "Message"))
            heading = f"## {label}"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            text = str(event.get("text", ""))
            lines.extend([f"> {line}" if line else ">" for line in text.splitlines()] or [">"])
        elif kind == "tool_call":
            tool = str(event.get("tool") or "tool")
            heading = f"## Tool call: `{tool}`"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            if event.get("call_id"):
                lines.append(f"Call ID: `{event['call_id']}`")
            if event.get("status"):
                lines.append(f"Status: `{event['status']}`")
            if event.get("arguments"):
                lines.extend(["", "Arguments:"])
                lines.extend(_code_block(str(event["arguments"])))
        elif kind == "tool_output":
            tool = str(event.get("tool") or "tool")
            heading = f"## Tool output: `{tool}`"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            if event.get("call_id"):
                lines.append(f"Call ID: `{event['call_id']}`")
            details = event.get("details") or {}
            if details:
                lines.extend(["", "Details:"])
                lines.extend(_code_block(json.dumps(details, ensure_ascii=False, indent=2), "json"))
            if event.get("output"):
                lines.extend(["", "Output:"])
                lines.extend(_code_block(str(event["output"])))
        elif kind == "activity":
            activity = str(event.get("activity") or "activity").replace("_", " ").title()
            heading = f"## {activity}"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            if event.get("event_id"):
                lines.append(f"Event ID: `{event['event_id']}`")
            if event.get("output"):
                lines.extend(["", "Details:"])
                lines.extend(_code_block(str(event["output"]), "json"))
        else:
            continue

        lines.extend(["", "---", ""])

    return "\n".join(lines).rstrip() + "\n"


def format_jsonl_memory(
    events: List[dict],
    session_name: str,
    session_id: Optional[str] = None,
    session_title: Optional[str] = None,
) -> str:
    """Format messages and tool activity as structured JSONL for raw retrieval/debugging."""
    lines = []
    fields = (
        "kind",
        "role",
        "timestamp",
        "turn_id",
        "ordinal",
        "tool",
        "call_id",
        "event_id",
        "status",
        "activity",
        "text",
        "arguments",
        "output",
        "details",
    )
    for event in events:
        entry = {
            "schema_version": 1,
            "session": session_name,
            "type": event.get("kind", ""),
        }
        if session_id:
            entry["session_id"] = session_id
        if session_title:
            entry["session_title"] = session_title
        for field in fields[1:]:
            value = event.get(field)
            if value not in (None, "", [], {}):
                entry[field] = value
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)


def format_jsonl_corpus(
    messages: List[dict],
    session_name: str,
    session_id: Optional[str] = None,
    session_title: Optional[str] = None,
) -> str:
    """Format normalized message records for the run-wide JSONL corpus.

    This product is intentionally message-oriented: it keeps user, assistant, and
    optional developer snippets in a single schema suitable for downstream
    indexing and retrieval. The raw event stream remains in `memory`.
    """
    lines = []
    for message in messages:
        role = message.get("role")
        if role not in ("user", "assistant", "developer"):
            continue
        text = message.get("text")
        if text is None:
            continue
        payload = {
            "schema_version": 1,
            "session": session_name,
            "type": "message",
            "role": role,
            "timestamp": message.get("timestamp"),
            "turn_id": message.get("turn_id"),
            "ordinal": message.get("ordinal"),
            "text": text,
        }
        if session_id:
            payload["session_id"] = session_id
        if session_title:
            payload["session_title"] = session_title
        lines.append(json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines)
