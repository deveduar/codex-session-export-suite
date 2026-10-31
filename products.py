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
        truncate_chars: Optional[int] = None,
        role: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.role_filter = role_filter or []
        self.truncate_chars = truncate_chars
        self.role = role

    def clone(self, **overrides: Any) -> "ProductConfig":
        """Return a copy with optional overrides."""
        values = {
            "name": self.name,
            "description": self.description,
            "role_filter": list(self.role_filter),
            "truncate_chars": self.truncate_chars,
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
            if self.truncate_chars and len(text) > self.truncate_chars:
                text = text[: self.truncate_chars] + "..."

            out = {
                "role": role,
                "timestamp": msg.get("timestamp", ""),
                "text": text,
            }

            result.append(out)

        return result


# ---------------------------------------------------------------------------
# Base products
# ---------------------------------------------------------------------------

transcript = ProductConfig(
    name="transcript",
    description="Chronological Markdown transcript with tool calls and results",
    role_filter=None,
)

conversation = ProductConfig(
    name="conversation",
    description="Markdown conversation messages only, excluding tool activity",
    role_filter=None,
)

memory = ProductConfig(
    name="memory",
    description="One structured JSON line per message, tool call, and tool result for RAG",
    role_filter=None,
)

faithful = ProductConfig(
    name="faithful",
    description="Byte-for-byte copy of the original Codex session JSONL",
    role_filter=None,
)

PRODUCTS: Dict[str, ProductConfig] = {
    "transcript": transcript,
    "conversation": conversation,
    "memory": memory,
    "faithful": faithful,
}


# ---------------------------------------------------------------------------
# Presets: named combinations of products
# ---------------------------------------------------------------------------

PRESETS: Dict[str, Dict[str, Any]] = {
    "archive": {
        "description": "Lossless source JSONL plus a chronological Markdown transcript with tool activity",
        "products": {
            "transcript": {},
            "faithful": {},
        },
    },
    "source": {
        "description": "Source-only lossless byte-for-byte JSONL copy",
        "product": "faithful",
    },
    "markdown": {
        "description": "Lossy: chronological Markdown transcript including tool activity",
        "product": "transcript",
    },
    "conversation": {
        "description": "Lossy: Markdown dialogue only; explicitly excludes tool activity",
        "product": "conversation",
    },
    "prompts": {
        "description": "Lossy: user messages only",
        "product": "conversation",
        "role": "user",
    },
    "rag": {
        "description": "Lossy: structured messages and tool events for retrieval",
        "product": "memory",
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
    unknown_options = set(options) - {"truncate", "role"}
    if unknown_options:
        unknown = ", ".join(sorted(unknown_options))
        raise ValueError(f"Unknown preset option(s): {unknown}")

    if "truncate" in options:
        value = options["truncate"]
        if value is None:
            overrides["truncate_chars"] = None
        elif isinstance(value, int):
            overrides["truncate_chars"] = value if value > 0 else None
        else:
            raise ValueError(f"Invalid truncate option: {value!r}")

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
conversation_product = conversation
memory_product = memory
faithful_product = faithful
