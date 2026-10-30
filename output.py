"""Output formatting for Codex export products.

Handles Markdown, JSONL, and faithful JSON output formats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    lines.append(f"# Historial Codex: `{filename}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # Keep the original chronological order: user/assistant turns interleaved.
    for msg in messages:
        role = msg.get("role")
        if not show_role:
            header = ">"
        else:
            label = "Usuario" if role == "user" else "Codex" if role == "assistant" else str(role or "Mensaje")
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


def format_markdown_conversation(
    messages: List[dict],
    filename: str = "session",
) -> str:
    """Format conversation-only transcript (no tools, no reasoning).
    
    Args:
        messages: List of message dicts
        filename: Session filename for the header
    
    Returns:
        Markdown-formatted string
    """
    lines = [f"# Historial Codex: `{filename}`"]
    lines.append("")
    lines.append("---\n")
    
    for i, msg in enumerate(messages, 1):
        role_emoji = "👤" if msg.get("role") == "user" else "🤖"
        timestamp_part = f" *({msg.get('timestamp', '')})*" if msg.get("timestamp") else ""
        lines.append(f"### {role_emoji} Mensaje {i}{timestamp_part}\n\n")
        lines.append(f"{msg['text']}\n\n")
        lines.append("---\n")
    
    return "\n".join(lines)


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


def format_faithful_json(
    messages: List[dict],
    session_name: str,
    include_raw_payload: bool = True,
) -> str:
    """Format messages as a faithful lossless JSON archive.
    
    Args:
        messages: List of message dicts
        session_name: Name of the session
        include_raw_payload: Whether to include raw payload data
    
    Returns:
        JSON-formatted string
    """
    archive = {
        "session": session_name,
        "messages": messages,
        "metadata": {
            "total_messages": len(messages),
            "user_messages": sum(1 for m in messages if m.get("role") == "user"),
            "assistant_messages": sum(1 for m in messages if m.get("role") == "assistant"),
        },
    }
    
    if include_raw_payload:
        # Include filtered raw payloads
        archive["raw_payloads"] = [
            m.get("raw_payload", {}) for m in messages if m.get("raw_payload")
        ]
    
    return json.dumps(archive, ensure_ascii=False, indent=2)


def format_digest_summary(
    messages: List[dict],
    session_name: str,
    max_chars: int = 500,
) -> str:
    """Create a digest summary of a session.
    
    Args:
        messages: List of message dicts
        session_name: Name of the session
        max_chars: Maximum characters per message summary
    
    Returns:
        Digest-formatted string
    """
    # Simple extractive summarization: take first N chars of each message
    summaries = []
    for msg in messages:
        text = msg.get("text", "")[:max_chars]
        if len(msg.get("text", "")) > max_chars:
            text += "..."
        summaries.append(text)
    
    return f"## Sesión: {session_name}\n\n" + "\n\n".join(summaries)