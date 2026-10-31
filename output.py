"""Output formatting for Codex export products.

Formats Markdown and derived JSONL products. The faithful product copies its
source JSONL directly in the CLI.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List


def format_markdown_transcript(
    messages: List[dict],
    filename: str = "session",
    include_timestamps: bool = True,
    show_role: bool = True,
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
    lines = []
    
    # Header
    lines.append(f"# Codex History: `{filename}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Keep the original chronological order: user/assistant turns interleaved.
    for msg in messages:
        role = msg.get("role")
        if not show_role:
            header = ">"
        else:
            label = "User" if role == "user" else "Codex" if role == "assistant" else str(role or "Message")
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


def format_markdown_activity_transcript(
    events: List[dict],
    filename: str = "session",
    include_timestamps: bool = True,
) -> str:
    """Format messages and tool activity as one chronological Markdown transcript."""
    lines = [f"# Codex History: `{filename}`", "", "---", ""]

    for event in events:
        kind = event.get("kind")
        timestamp = event.get("timestamp")
        if kind == "message":
            role = event.get("role")
            label = "User" if role == "user" else "Codex"
            heading = f"### {label}"
            if include_timestamps and timestamp:
                heading += f" · {timestamp}"
            lines.extend([heading, ""])
            text = str(event.get("text", ""))
            lines.extend([f"> {line}" if line else ">" for line in text.splitlines()] or [">"])
        elif kind == "tool_call":
            tool = str(event.get("tool") or "tool")
            heading = f"### Tool call: `{tool}`"
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
            heading = f"### Tool output: `{tool}`"
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
            heading = f"### {activity}"
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
) -> str:
    """Format messages and tool activity as structured JSONL for RAG.
    
    Args:
        events: Chronological message and activity event dicts
        session_name: Name of the session
    
    Returns:
        JSONL-formatted string
    """
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
        for field in fields[1:]:
            value = event.get(field)
            if value not in (None, "", [], {}):
                entry[field] = value
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)
