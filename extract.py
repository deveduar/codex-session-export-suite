"""Core extraction logic for Codex session JSONL files."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Keys that indicate technical/metadata events to filter out
NOISE_KEYS = {
    "session_meta",
    "timestamp",
    "time",
    "id",
    "uuid",
    "type",
    "role",
    "status",
    "event",
    "name",
    "namespace",
    "cwd",
    "cli_version",
    "source",
    "originator",
    "model_provider",
    "history_mode",
    "context_window",
    "git",
    "provenance",
    "content_item_kinds",
    "content_item_metadata",
    "metadata",
    "internal_chat_message_metadata_passthrough",
    "client_authored",
    "user_input_order",
    "mcp_attribution",
    "retained_source",
}


def is_noise_key(key: str) -> bool:
    """Check if a key is a technical/metadata key to filter out."""
    key_lower = key.lower().strip()
    return key_lower in NOISE_KEYS


def detect_role(obj: dict) -> Optional[str]:
    """Detect the role from a Codex JSONL payload object.

    Returns 'user', 'assistant' (Codex), or None.
    """
    # Try 'role' field first
    role = obj.get("role") or obj.get("author")
    if role:
        role_lower = str(role).lower().strip()
        if any(word in role_lower for word in ["user", "usuario", "human"]):
            return "user"
        elif any(word in role_lower for word in ["assistant", "asistente", "ai", "codex", "developer", "gpt"]):
            return "assistant"

    # Try payload.role
    payload = obj.get("payload", {})
    if isinstance(payload, dict):
        payload_role = payload.get("role")
        if payload_role:
            role_lower = str(payload_role).lower().strip()
            if any(word in role_lower for word in ["user", "usuario", "human"]):
                return "user"
            elif any(word in role_lower for word in ["assistant", "asistente", "ai", "codex", "developer", "gpt"]):
                return "assistant"

    # Fallback: check if it's a user message based on content starting with #
    content = obj.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "input_text":
                text = block.get("text", "")
                if text.startswith("# "):
                    return "user"

    return None


def extract_text_from_content(content: Any) -> str:
    """Extract plain text from content blocks, filtering out noise."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                text = block.get("text", "")
                if text and btype in ("input_text", "output_text", "text"):
                    parts.append(text)
                elif text and isinstance(block.get(""), dict):
                    parts.append(extract_text_from_content(text))
        return " ".join(parts).strip()
    return ""


def filter_payload(obj: dict, exclude_roles: bool = True) -> dict:
    """Filter a payload dict to remove technical keys and noise.

    Args:
        obj: The JSON object (dict) from a JSONL line
        exclude_roles: Whether to exclude role/timestamp/id keys

    Returns:
        A filtered dict with only conversational content
    """
    filtered = {}

    for key, value in obj.items():
        # Skip known noise keys
        if is_noise_key(key):
            continue

        # Skip empty values
        if value is None or value == "":
            continue

        # Skip role, timestamp, id when excluding roles
        if exclude_roles and key.lower() in ("role", "timestamp", "id", "uuid"):
            continue

        # Recursively filter nested dicts
        if isinstance(value, dict):
            filtered_value = filter_payload(value, exclude_roles)
            if filtered_value:  # Only add if non-empty
                filtered[key] = filtered_value
        elif isinstance(value, list):
            # Filter list items
            filtered_items = []
            for item in value:
                if isinstance(item, dict):
                    item_filtered = filter_payload(item, exclude_roles)
                    if item_filtered:
                        filtered_items.append(item_filtered)
                else:
                    # Skip noise items (timestamps, ids, etc.)
                    if not is_noise_key(str(item)) if isinstance(item, str) else False:
                        filtered_items.append(item)
            if filtered_items:
                filtered[key] = filtered_items
        else:
            filtered[key] = value

    return filtered


def parse_jsonl_line(line: str) -> Optional[dict]:
    """Parse a single JSONL line and return the dict, or None if invalid."""
    try:
        data = json.loads(line.strip())
        return data
    except (json.JSONDecodeError, ValueError):
        return None


def extract_messages_from_jsonl(
    file_path: Path,
    include_roles: Tuple[str, ...] = ("user", "assistant"),
    filter_noise: bool = True,
) -> List[dict]:
    """Extract user and assistant messages from a Codex JSONL session file.

    Args:
        file_path: Path to the .jsonl file
        include_roles: Which roles to include
        filter_noise: Whether to filter technical noise

    Returns:
        List of dicts with 'role', 'timestamp', 'text' keys
    """
    messages = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            data = parse_jsonl_line(line)
            if data is None:
                continue

            # Skip session_meta entries
            if data.get("type") == "session_meta":
                continue

            # Handle response_item type (most common for messages)
            if data.get("type") == "response_item":
                payload = data.get("payload", {})
                if isinstance(payload, dict):
                    role = detect_role(payload)
                    if role and role in include_roles:
                        # Extract text content
                        content = payload.get("content", [])
                        text = extract_text_from_content(content) if content else ""

                        # Get timestamp
                        timestamp = data.get("timestamp", "")
                        if not timestamp:
                            timestamp = payload.get("timestamp", "")

                        messages.append({
                            "role": role,
                            "timestamp": timestamp,
                            "text": text.strip(),
                            "raw_payload": payload,
                        })

            # Handle turn_context type
            elif data.get("type") == "turn_context":
                payload = data.get("payload", {})
                if isinstance(payload, dict):
                    role = detect_role(payload)
                    if role and role in include_roles:
                        content = payload.get("content", [])
                        text = extract_text_from_content(content) if content else ""
                        timestamp = data.get("timestamp", "")
                        messages.append({
                            "role": role,
                            "timestamp": timestamp,
                            "text": text.strip(),
                            "raw_payload": payload,
                        })

    return messages