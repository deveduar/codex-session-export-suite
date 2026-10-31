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
                elif isinstance(item, str):
                    # Skip noise items (timestamps, ids, etc.)
                    if not is_noise_key(item):
                        filtered_items.append(item)
                else:
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


def read_session_metadata(file_path: Path) -> Dict[str, Any]:
    """Read safe session metadata from the first session_meta record."""
    with open(file_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            data = parse_jsonl_line(line)
            if not isinstance(data, dict):
                continue

            if data.get("type") != "session_meta":
                continue

            payload = data.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            workspace_roots = payload.get("runtime_workspace_roots") or []
            if not isinstance(workspace_roots, list):
                workspace_roots = []

            git = payload.get("git") or {}
            if not isinstance(git, dict):
                git = {}

            return {
                "id": payload.get("id") or payload.get("session_id"),
                "timestamp": payload.get("timestamp") or data.get("timestamp"),
                "cwd": payload.get("cwd"),
                "workspace_roots": [str(root) for root in workspace_roots],
                "source": payload.get("source"),
                "thread_source": payload.get("thread_source"),
                "parent_thread_id": payload.get("parent_thread_id"),
                "agent_role": payload.get("agent_role"),
                "agent_nickname": payload.get("agent_nickname"),
                "originator": payload.get("originator"),
                "cli_version": payload.get("cli_version"),
                "model_provider": payload.get("model_provider"),
                "git": {
                    key: git.get(key)
                    for key in ("branch", "commit_hash")
                    if git.get(key)
                },
            }

    return {}


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
    seen_keys = set()

    def add_message(role, timestamp, text, dedupe=False):
        text = (text or "").strip()
        if not role or role not in include_roles or not text:
            return

        key = (role, text)
        if dedupe and key in seen_keys:
            return

        seen_keys.add(key)
        messages.append({
            "role": role,
            "timestamp": timestamp or "",
            "text": text,
        })

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
                    content = payload.get("content", [])
                    text = extract_text_from_content(content) if content else ""
                    timestamp = data.get("timestamp", "") or payload.get("timestamp", "")
                    add_message(role, timestamp, text)

            # Handle turn_context type
            elif data.get("type") == "turn_context":
                payload = data.get("payload", {})
                if isinstance(payload, dict):
                    role = detect_role(payload)
                    content = payload.get("content", [])
                    text = extract_text_from_content(content) if content else ""
                    timestamp = data.get("timestamp", "") or payload.get("timestamp", "")
                    add_message(role, timestamp, text)

            # Handle event_msg type used by some Codex versions.
            elif data.get("type") == "event_msg":
                payload = data.get("payload", {})
                if isinstance(payload, dict):
                    event_type = str(payload.get("type", "")).lower()
                    if event_type in ("user_message", "agent_message"):
                        role = "user" if event_type == "user_message" else "assistant"
                        text = payload.get("message") or payload.get("text") or ""
                        if not isinstance(text, str):
                            text = extract_text_from_content(text)
                        timestamp = data.get("timestamp", "") or payload.get("timestamp", "")
                        add_message(role, timestamp, text, dedupe=True)

    return messages


def _event_payload_text(value: Any) -> str:
    """Convert a tool payload to readable text without dropping structure."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def extract_session_events_from_jsonl(file_path: Path) -> List[dict]:
    """Extract a chronological view of messages and tool activity.

    The original JSONL remains the authoritative lossless source. This derived
    view includes visible messages, tool calls/results, and structured command,
    file-change, and web-search activity when available.
    """
    events: List[dict] = []
    seen_messages = set()
    tool_names: Dict[str, str] = {}
    command_details: Dict[str, dict] = {}
    web_search_events: List[dict] = []
    file_change_events: List[dict] = []

    def turn_id_from(payload: dict) -> str:
        metadata = payload.get("internal_chat_message_metadata_passthrough") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        return str(payload.get("turn_id") or metadata.get("turn_id") or "")

    def add_message(
        role: Optional[str],
        timestamp: Any,
        text: Any,
        ordinal: int,
        turn_id: str = "",
    ) -> None:
        if role not in ("user", "assistant"):
            return
        body = _event_payload_text(text).strip()
        if not body:
            return
        stamp = str(timestamp or "")
        dedupe_key = (role, stamp, body)
        if dedupe_key in seen_messages:
            return
        seen_messages.add(dedupe_key)
        events.append({
            "kind": "message",
            "role": role,
            "timestamp": stamp,
            "text": body,
            "turn_id": turn_id,
            "ordinal": ordinal,
        })

    with open(file_path, "r", encoding="utf-8") as handle:
        for ordinal, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            data = parse_jsonl_line(line)
            if not isinstance(data, dict):
                continue

            timestamp = data.get("timestamp", "")
            record_type = data.get("type")
            payload = data.get("payload", {})
            if not isinstance(payload, dict):
                continue

            if record_type in ("response_item", "turn_context"):
                item_type = str(payload.get("type", "")).lower()
                if record_type == "turn_context" or item_type == "message":
                    role = detect_role(payload)
                    text = extract_text_from_content(payload.get("content", []))
                    add_message(
                        role,
                        timestamp or payload.get("timestamp"),
                        text,
                        ordinal,
                        turn_id_from(payload),
                    )
                    continue

                if item_type in ("function_call", "custom_tool_call"):
                    call_id = str(payload.get("call_id") or "")
                    tool = str(payload.get("name") or item_type)
                    if call_id:
                        tool_names[call_id] = tool
                    arguments = payload.get("arguments", payload.get("input", ""))
                    events.append({
                        "kind": "tool_call",
                        "role": "assistant",
                        "timestamp": str(timestamp or ""),
                        "turn_id": turn_id_from(payload),
                        "tool": tool,
                        "call_id": call_id,
                        "event_id": str(payload.get("id") or ""),
                        "arguments": _event_payload_text(arguments),
                        "status": str(payload.get("status") or ""),
                        "ordinal": ordinal,
                    })
                    continue

                if item_type in ("function_call_output", "custom_tool_call_output"):
                    call_id = str(payload.get("call_id") or "")
                    events.append({
                        "kind": "tool_output",
                        "role": "assistant",
                        "timestamp": str(timestamp or ""),
                        "turn_id": turn_id_from(payload),
                        "tool": tool_names.get(call_id, ""),
                        "call_id": call_id,
                        "event_id": str(payload.get("id") or ""),
                        "output": _event_payload_text(payload.get("output")),
                        "ordinal": ordinal,
                    })
                    continue

                if item_type == "web_search_call":
                    events.append({
                        "kind": "tool_call",
                        "role": "assistant",
                        "timestamp": str(timestamp or ""),
                        "turn_id": turn_id_from(payload),
                        "tool": "web_search",
                        "call_id": str(payload.get("call_id") or ""),
                        "event_id": str(payload.get("id") or ""),
                        "arguments": _event_payload_text(payload.get("action", {})),
                        "status": str(payload.get("status") or ""),
                        "ordinal": ordinal,
                    })
                    continue

            if record_type == "event_msg":
                event_type = str(payload.get("type", "")).lower()
                if event_type in ("user_message", "agent_message"):
                    role = "user" if event_type == "user_message" else "assistant"
                    text = payload.get("message") or payload.get("text") or ""
                    if not isinstance(text, str):
                        text = extract_text_from_content(text)
                    add_message(
                        role,
                        timestamp or payload.get("timestamp"),
                        text,
                        ordinal,
                        turn_id_from(payload),
                    )
                    continue

                if event_type == "item_completed":
                    item = payload.get("item")
                    if not isinstance(item, dict):
                        continue
                    item_type = str(item.get("type", ""))
                    if item_type == "CommandExecution":
                        call_id = str(item.get("id") or "")
                        details = {
                            key: item.get(key)
                            for key in ("command", "cwd", "duration", "exit_code", "status")
                            if item.get(key) not in (None, "")
                        }
                        if call_id:
                            command_details[call_id] = {
                                "details": details,
                                "output": _event_payload_text(
                                    item.get("aggregated_output") or item.get("stdout")
                                ),
                                "timestamp": str(timestamp or ""),
                                "turn_id": turn_id_from(payload),
                                "ordinal": ordinal,
                            }
                    elif item_type in ("FileChange", "WebSearch"):
                        activity = {
                            key: value
                            for key, value in item.items()
                            if key not in ("id", "type") and value not in (None, "", [], {})
                        }
                        event = {
                            "kind": "activity",
                            "role": "assistant",
                            "timestamp": str(timestamp or ""),
                            "turn_id": turn_id_from(payload),
                            "activity": "file_change" if item_type == "FileChange" else "web_search",
                            "event_id": str(item.get("id") or ""),
                            "output": _event_payload_text(activity),
                            "ordinal": ordinal,
                        }
                        if item_type == "WebSearch":
                            web_search_events.append(event)
                        else:
                            file_change_events.append(event)

    events.extend(web_search_events)
    events.extend(file_change_events)
    events.sort(key=lambda event: event.get("ordinal", -1))

    outputs_by_call_id = {
        event.get("call_id"): event
        for event in events
        if event.get("kind") == "tool_output" and event.get("call_id")
    }
    for call_id, command in command_details.items():
        output_event = outputs_by_call_id.get(call_id)
        if output_event is not None:
            output_event["details"] = command["details"]
            if not output_event.get("output") and command.get("output"):
                output_event["output"] = command["output"]
        elif command.get("output") or command["details"]:
            events.append({
                "kind": "tool_output",
                "role": "assistant",
                "timestamp": command["timestamp"],
                "turn_id": command["turn_id"],
                "tool": tool_names.get(call_id, "shell_command"),
                "call_id": call_id,
                "output": command.get("output", ""),
                "details": command["details"],
                "ordinal": command["ordinal"],
            })

    events.sort(key=lambda event: event.get("ordinal", -1))

    return events


def retain_recent_turns(events: List[dict], recent_turns: Optional[int]) -> List[dict]:
    """Keep the final N user turns, including their assistant/tool events."""
    if recent_turns is None:
        return events
    if recent_turns <= 0:
        return []

    user_turn_starts = [
        index
        for index, event in enumerate(events)
        if event.get("kind") == "message" and event.get("role") == "user"
    ]
    if not user_turn_starts:
        return []

    start = user_turn_starts[max(0, len(user_turn_starts) - recent_turns)]
    return events[start:]
