"""Output formatting for Codex export products.

Formats Markdown and derived JSONL products. The faithful product copies its
source JSONL directly in the CLI.
"""

from __future__ import annotations

import json
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


def format_jsonl_memory(
    messages: List[dict],
    session_name: str,
) -> str:
    """Format messages as JSONL for memory/RAG corpus.
    
    Each line is a JSON object with role, timestamp, and text.
    
    Args:
        messages: List of message dicts
        session_name: Name of the session
    
    Returns:
        JSONL-formatted string
    """
    lines = []
    for msg in messages:
        entry = {
            "session": session_name,
            "role": msg.get("role", ""),
            "timestamp": msg.get("timestamp", ""),
            "text": msg.get("text", ""),
        }
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)
