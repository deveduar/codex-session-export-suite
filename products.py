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
        developer: str = "include",
        message_only: bool = False,
        clean_user_prompts: bool = False,
        strip_boilerplate: bool = False,
    ):
        self.name = name
        self.description = description
        self.role_filter = role_filter or []
        self.truncate_chars = truncate_chars
        self.role = role
        self.developer = developer
        self.message_only = message_only
        self.clean_user_prompts = clean_user_prompts
        self.strip_boilerplate = strip_boilerplate

    def clone(self, **overrides: Any) -> "ProductConfig":
        """Return a copy with optional overrides."""
        values = {
            "name": self.name,
            "description": self.description,
            "role_filter": list(self.role_filter),
            "truncate_chars": self.truncate_chars,
            "role": self.role,
            "developer": self.developer,
            "message_only": self.message_only,
            "clean_user_prompts": self.clean_user_prompts,
            "strip_boilerplate": self.strip_boilerplate,
        }
        values.update(overrides)
        return ProductConfig(**values)

    def allows_role(self, role: Optional[str]) -> bool:
        """Return True if this product includes the given role."""
        role = str(role or "")

        if self.role_filter:
            return role in self.role_filter

        if self.role and role != self.role:
            return False

        if role == "developer":
            return self.developer != "exclude"

        if self.developer == "only":
            return False

        return True

    def select_events(self, events: List[dict]) -> List[dict]:
        """Filter events by kind and role without mutating the source list."""
        selected = []
        for event in events:
            if self.message_only and event.get("kind") != "message":
                continue
            if not self.allows_role(event.get("role")):
                continue

            filtered = dict(event)
            if (
                self.clean_user_prompts
                and filtered.get("kind") == "message"
                and filtered.get("role") == "user"
            ):
                from extract import extract_user_prompt

                text = extract_user_prompt(filtered.get("text", ""))
                if not text:
                    continue
                filtered["text"] = text

            if self.strip_boilerplate and filtered.get("kind") == "message":
                from extract import extract_user_prompt

                if filtered.get("role") == "user":
                    text = extract_user_prompt(filtered.get("text", ""))
                    if not text:
                        continue
                    filtered["text"] = text

            selected.append(filtered)
        return selected

    def apply(self, messages: List[dict]) -> List[dict]:
        """Apply product filtering to a list of messages."""
        result = []

        for msg in messages:
            role = msg["role"]

            if not self.allows_role(role):
                continue

            text = msg["text"]
            if self.clean_user_prompts and role == "user":
                from extract import extract_user_prompt

                text = extract_user_prompt(text)
                if not text:
                    continue

            if self.strip_boilerplate and role == "user":
                from extract import extract_user_prompt

                text = extract_user_prompt(text)
                if not text:
                    continue

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
    description="Chronological Markdown transcript with tool calls, results, context, and developer instructions",
    role_filter=None,
    developer="include",
)

conversation = ProductConfig(
    name="conversation",
    description="Clean Markdown dialogue without tool activity, generated context, or developer instructions",
    role_filter=None,
    developer="exclude",
    message_only=True,
    clean_user_prompts=True,
    strip_boilerplate=True,
)

memory = ProductConfig(
    name="memory",
    description="One structured JSON line per message, tool call, context block, and tool result for RAG",
    role_filter=None,
    developer="include",
    strip_boilerplate=False,
)

instructions = ProductConfig(
    name="instructions",
    description="Developer instructions only, with no user or assistant messages",
    role_filter=["developer"],
    message_only=True,
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
    "instructions": instructions,
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
        "description": "Lossy: clean Markdown dialogue only; excludes tool activity, generated context, and developer instructions",
        "product": "conversation",
    },
    "prompts": {
        "description": "Lossy: human-authored user prompts only",
        "product": "conversation",
        "role": "user",
    },
    "rag": {
        "description": "Lossy: structured messages and tool events for retrieval",
        "product": "memory",
    },
    "instructions": {
        "description": "Lossy: explicit developer instructions only",
        "product": "instructions",
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
instructions_product = instructions
faithful_product = faithful
