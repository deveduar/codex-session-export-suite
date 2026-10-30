"""Product presets and configurations for Codex export modes.

Based on the "four products" matrix: transcript, memory, digest, faithful.
Each product defines how to transform raw messages into the desired output format.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from extract import detect_role, extract_text_from_content, filter_payload


# ---------------------------------------------------------------------------
# Product definitions – what each product type extracts and how
# ---------------------------------------------------------------------------

class ProductConfig:
    """Configuration for a single export product type."""

    def __init__(
        self,
        name: str,
        description: str,
        role_filter: Optional[List[str]] = None,
        include_tool_output: bool = True,
        truncate_tool_output: Optional[int] = None,
        no_reasoning: bool = False,
        role: Optional[str] = None,  # Force specific role (e.g. "user" only)
    ):
        self.name = name
        self.description = description
        self.role_filter = role_filter or []  # e.g. ["user"], ["assistant"]
        self.include_tool_output = include_tool_output
        self.truncate_tool_output = truncate_tool_output  # chars, None = full
        self.no_reasoning = no_reasoning  # strip tool/output reasoning blocks
        self.role = role  # Force single role filter

    def clone(self, **overrides: Any) -> "ProductConfig":
        """Return a copy with optional overrides.

        Used so CLI flags do not mutate the global preset objects.
        """
        values = {
            "name": self.name,
            "description": self.description,
            "role_filter": list(self.role_filter),
            "include_tool_output": self.include_tool_output,
            "truncate_tool_output": self.truncate_tool_output,
            "no_reasoning": self.no_reasoning,
            "role": self.role,
        }
        values.update(overrides)
        return ProductConfig(**values)

    def apply(self, messages: List[dict]) -> List[dict]:
        """Apply product filtering to a list of messages.

        Returns a filtered list suitable for this product type.
        """
        result = []

        for msg in messages:
            role = msg["role"]

            # Force single-role filter if configured
            if self.role and role != self.role:
                continue

            # Role filter inclusion
            if self.role_filter and role not in self.role_filter:
                continue

            # Extract and optionally truncate text
            text = msg["text"]
            if self.truncate_tool_output and len(text) > self.truncate_tool_output:
                text = text[: self.truncate_tool_output] + "..."

            # Build output message
            out = {
                "role": role,
                "timestamp": msg.get("timestamp", ""),
                "text": text,
            }

            # Include/exclude tool/output data based on product config
            if self.include_tool_output and not self.no_reasoning:
                # Keep raw payload for faithful/transcript modes
                out["raw_payload"] = msg.get("raw_payload", {})

            result.append(out)

        return result


# ---------------------------------------------------------------------------
# Pre-configured product presets (the "four products" matrix)
# ---------------------------------------------------------------------------

#: Transcript product – full conversation in Markdown
transcript = ProductConfig(
    name="transcript",
    description="Full conversation in Markdown (text + tools + patches + digests)",
    role_filter=None,  # Include all roles
    include_tool_output=True,
    truncate_tool_output=None,  # Full text
    no_reasoning=False,
)

#: Memory product – corpus.jsonl format for RAG/feeding another AI
memory = ProductConfig(
    name="memory",
    description="corpus.jsonl — one JSON line per root session (goal, outcome, digests, metadata)",
    role_filter=None,
    include_tool_output=False,
    truncate_tool_output=None,
    no_reasoning=True,  # Strip reasoning for clean corpus
)

#: Digest product – only compacted-context digests
digest = ProductConfig(
    name="digest",
    description="Only the compacted-context digests (knowledge arc)",
    role_filter=None,
    include_tool_output=False,
    truncate_tool_output=500,  # Truncated summaries
    no_reasoning=True,
)

#: Faithful product – lossless machine archive
faithful = ProductConfig(
    name="faithful",
    description="Lossless machine archive: one native JSON file per session (all messages, parts, reasoning)",
    role_filter=None,
    include_tool_output=True,
    truncate_tool_output=None,
    no_reasoning=False,
)

# Convenience presets matching the matrix from the design

PRESETS: Dict[str, ProductConfig] = {
    # Archive: full backup — complete tool outputs and the raw session
    "archive": ProductConfig(
        name="archive",
        description="Full backup — complete tool outputs and the raw session, with touched-file lists (heavy)",
        role_filter=None,
        include_tool_output=True,
        truncate_tool_output=None,
        no_reasoning=False,
    ),
    # Quick: raw session losslessly — one native-JSON file per session (fast, compact)
    "quick": ProductConfig(
        name="quick",
        description="The raw session, losslessly — one native-JSON file per session (fast, compact)",
        role_filter=None,
        include_tool_output=True,
        truncate_tool_output=None,
        no_reasoning=False,
    ),
    # Study: readable log plus searchable corpus, no raw copy (medium)
    "study": ProductConfig(
        name="study",
        description="A readable log plus a searchable corpus, no raw copy (medium)",
        role_filter=None,
        include_tool_output=False,
        truncate_tool_output=500,
        no_reasoning=True,
    ),
    # Review: readable log without reasoning, plus the raw session (does not redact)
    "review": ProductConfig(
        name="review",
        description="The readable log without reasoning, plus the raw session (does not redact)",
        role_filter=None,
        include_tool_output=True,
        truncate_tool_output=None,
        no_reasoning=True,
    ),
    # Notes: plain read — every message, tool output truncated to ~500 chars (light)
    "notes": ProductConfig(
        name="notes",
        description="Plain read — every message, tool output truncated to ~500 chars (light)",
        role_filter=None,
        include_tool_output=True,
        truncate_tool_output=500,
        no_reasoning=False,
    ),
    # Conversation: dialogue only — no tools, patches or reasoning (light)
    "conversation": ProductConfig(
        name="conversation",
        description="The dialogue only — no tools, patches or reasoning (light)",
        role_filter=None,
        include_tool_output=False,
        truncate_tool_output=None,
        no_reasoning=True,
    ),
    # Prompts: just your prompts — no answers, reasoning or tools (task log)
    "prompts": ProductConfig(
        name="prompts",
        description="Just your prompts — no answers, reasoning or tools (task log)",
        role_filter=["user"],  # Only user messages
        include_tool_output=False,
        truncate_tool_output=None,
        no_reasoning=True,
    ),
    # RAG: one line per session — tokens, asks, todos, tools and digests (summary)
    "rag": ProductConfig(
        name="rag",
        description="One line per session — tokens, asks, tools and digests (summary)",
        role_filter=None,
        include_tool_output=False,
        truncate_tool_output=200,
        no_reasoning=True,
    ),
    # Digest: only the compaction summaries (knowledge arc)
    "digest_only": ProductConfig(
        name="digest",
        description="Only the compaction summaries (knowledge arc)",
        role_filter=None,
        include_tool_output=False,
        truncate_tool_output=300,
        no_reasoning=True,
    ),
}


def get_preset(name: str) -> ProductConfig:
    """Get a product preset by name.

    Args:
        name: Preset name (archive, quick, study, review, notes, conversation, prompts, rag, digest)

    Returns:
        ProductConfig instance

    Raises:
        KeyError: If preset name is not found
    """
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise KeyError(f"Unknown preset '{name}'. Available: {available}")
    return PRESETS[name]


def list_presets() -> List[str]:
    """List all available preset names."""
    return list(PRESETS.keys())


# Alias for backwards compatibility / quick access
transcript_product = transcript
memory_product = memory
digest_product = digest
faithful_product = faithful