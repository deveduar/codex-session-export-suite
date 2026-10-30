"""Products and presets for Codex export modes.

Products are the actual output formats. Presets are named combinations of one
or more products, with optional per-product settings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ProductConfig:
    """Configuration for a single export product."""

    def __init__(
        self,
        name: str,
        description: str,
        role_filter: Optional[List[str]] = None,
        include_tool_output: bool = True,
        truncate_tool_output: Optional[int] = None,
        no_reasoning: bool = False,
        role: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.role_filter = role_filter or []
        self.include_tool_output = include_tool_output
        self.truncate_tool_output = truncate_tool_output
        self.no_reasoning = no_reasoning
        self.role = role

    def clone(self, **overrides: Any) -> "ProductConfig":
        """Return a copy with optional overrides."""
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
        """Apply product filtering to a list of messages."""
        result = []

        for msg in messages:
            role = msg["role"]

            if self.role and role != self.role:
                continue

            if self.role_filter and role not in self.role_filter:
                continue

            text = msg["text"]
            if self.truncate_tool_output and len(text) > self.truncate_tool_output:
                text = text[: self.truncate_tool_output] + "..."

            out = {
                "role": role,
                "timestamp": msg.get("timestamp", ""),
                "text": text,
            }

            if self.include_tool_output and not self.no_reasoning:
                out["raw_payload"] = msg.get("raw_payload", {})

            result.append(out)

        return result


# ---------------------------------------------------------------------------
# Base products
# ---------------------------------------------------------------------------

transcript = ProductConfig(
    name="transcript",
    description="Conversation messages in Markdown, in chronological order",
    role_filter=None,
    include_tool_output=True,
    truncate_tool_output=None,
    no_reasoning=False,
)

memory = ProductConfig(
    name="memory",
    description="One JSON line per message for RAG or another AI",
    role_filter=None,
    include_tool_output=False,
    truncate_tool_output=None,
    no_reasoning=True,
)

digest = ProductConfig(
    name="digest",
    description="Short extractive summaries of conversation messages",
    role_filter=None,
    include_tool_output=False,
    truncate_tool_output=500,
    no_reasoning=True,
)

faithful = ProductConfig(
    name="faithful",
    description="Lossless machine archive: one native JSON file per session",
    role_filter=None,
    include_tool_output=True,
    truncate_tool_output=None,
    no_reasoning=False,
)

PRODUCTS: Dict[str, ProductConfig] = {
    "transcript": transcript,
    "memory": memory,
    "faithful": faithful,
    "digest": digest,
}


# ---------------------------------------------------------------------------
# Presets: named combinations of products
# ---------------------------------------------------------------------------

PRESETS: Dict[str, Dict[str, Any]] = {
    "archive": {
        "description": "Full backup: transcript, memory corpus and faithful raw session (heavy)",
        "products": {
            "transcript": {"tool_output": "full"},
            "memory": {"files": True},
            "faithful": {},
        },
    },
    "quick": {
        "description": "Faithful raw session only — one native JSON file per session (fast, compact)",
        "product": "faithful",
    },
    "study": {
        "description": "Readable transcript plus searchable memory corpus, no raw copy (medium)",
        "products": {
            "transcript": {"tool_output": "truncated"},
            "memory": {"files": True},
        },
    },
    "review": {
        "description": "Transcript without reasoning plus faithful raw session (does not redact)",
        "products": {
            "transcript": {"no_reasoning": True},
            "faithful": {},
        },
    },
    "notes": {
        "description": "Plain transcript with text truncated to ~500 chars (light)",
        "product": "transcript",
        "tool_output": "truncated",
    },
    "conversation": {
        "description": "Dialogue only: no tools, patches or reasoning (light)",
        "product": "transcript",
        "tool_output": "omit",
        "patch": "omit",
        "no_reasoning": True,
    },
    "prompts": {
        "description": "User prompts only: no answers, reasoning or tools (task log)",
        "product": "transcript",
        "role": "user",
    },
    "rag": {
        "description": "Searchable memory corpus for retrieval (one JSON line per message)",
        "product": "memory",
    },
    "digest": {
        "description": "Short extractive summaries of conversation messages",
        "product": "digest",
    },
}


def get_product(name: str) -> ProductConfig:
    """Get a base product by name."""
    if name not in PRODUCTS:
        available = ", ".join(PRODUCTS.keys())
        raise KeyError(f"Unknown product '{name}'. Available: {available}")
    return PRODUCTS[name]


def get_preset(name: str) -> Dict[str, Any]:
    """Get a preset definition by name."""
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise KeyError(f"Unknown preset '{name}'. Available: {available}")
    return PRESETS[name]


def list_products() -> List[str]:
    """List all product names."""
    return list(PRODUCTS.keys())


def list_presets() -> List[str]:
    """List all preset names."""
    return list(PRESETS.keys())


def _apply_product_options(product: ProductConfig, options: Dict[str, Any]) -> ProductConfig:
    """Apply preset options to a product without mutating the base product."""
    options = options or {}
    overrides: Dict[str, Any] = {}

    tool_output = options.get("tool_output")
    if tool_output == "full":
        overrides["include_tool_output"] = True
        overrides["truncate_tool_output"] = None
    elif tool_output == "truncated":
        overrides["include_tool_output"] = True
        overrides["truncate_tool_output"] = 500
    elif tool_output == "omit":
        overrides["include_tool_output"] = False
        overrides["truncate_tool_output"] = None
    elif isinstance(tool_output, int):
        overrides["include_tool_output"] = True
        overrides["truncate_tool_output"] = tool_output if tool_output > 0 else None
    elif tool_output is not None:
        raise ValueError(f"Invalid tool_output option: {tool_output!r}")

    if "truncate" in options:
        value = options["truncate"]
        if value is None:
            overrides["truncate_tool_output"] = None
        elif isinstance(value, int):
            overrides["truncate_tool_output"] = value if value > 0 else None
        else:
            raise ValueError(f"Invalid truncate option: {value!r}")

    if "no_reasoning" in options:
        overrides["no_reasoning"] = bool(options["no_reasoning"])

    if "role" in options:
        role = str(options["role"]).strip().lower()
        if role == "both":
            overrides["role_filter"] = []
            overrides["role"] = None
        elif role in ("user", "assistant"):
            overrides["role_filter"] = [role]
            overrides["role"] = None
        else:
            raise ValueError(f"Invalid role option: {options['role']!r}")

    # "files" and "patch" are reserved for a future extraction phase.
    return product.clone(**overrides) if overrides else product


def resolve_preset(name: str) -> List[ProductConfig]:
    """Expand a preset into one or more concrete product configurations."""
    preset = get_preset(name)

    if "products" in preset and "product" in preset:
        raise ValueError(f"Preset '{name}' cannot define both 'product' and 'products'")

    if "products" in preset:
        product_specs = preset["products"]
    elif "product" in preset:
        product_name = preset["product"]
        options = {
            key: value
            for key, value in preset.items()
            if key not in ("description", "product", "products")
        }
        product_specs = {product_name: options}
    else:
        raise ValueError(f"Preset '{name}' does not define a product")

    resolved = []
    for product_name, options in product_specs.items():
        product = get_product(product_name)
        resolved.append(_apply_product_options(product, options or {}))

    return resolved


# Aliases for quick access
transcript_product = transcript
memory_product = memory
digest_product = digest
faithful_product = faithful
