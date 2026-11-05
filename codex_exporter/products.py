"""Products and presets for Codex export modes.

The model is split into three layers:
- ProductSpec: concrete output format
- Preset: named recipe with export policy
- ResolvedProduct: runtime configuration applied to a product in an export run
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ProductSpec:
    """Concrete output format without runtime policy leakage."""

    def __init__(self, name: str, description: str, *, kind: str = "markdown"):
        self.name = name
        self.description = description
        self.kind = kind

    def clone(self, **overrides: Any) -> "ProductSpec":
        values = {"name": self.name, "description": self.description, "kind": self.kind}
        values.update(overrides)
        return ProductSpec(**values)

    def allows_role(self, role: Optional[str]) -> bool:
        return True


class ResolvedProduct(ProductSpec):
    """Effective runtime configuration for one exported product."""

    def __init__(
        self,
        product: ProductSpec,
        *,
        role: Optional[str] = None,
        role_filter: Optional[List[str]] = None,
        developer: Optional[str] = None,
        message_only: Optional[bool] = False,
        clean_user_prompts: Optional[bool] = False,
        strip_boilerplate: Optional[bool] = False,
        truncate_chars: Optional[int] = None,
    ):
        super().__init__(name=product.name, description=product.description, kind=product.kind)
        self.role = role
        self.role_filter = list(role_filter or [])
        self.developer = developer
        self.message_only = bool(message_only)
        self.clean_user_prompts = bool(clean_user_prompts)
        self.strip_boilerplate = bool(strip_boilerplate)
        self.truncate_chars = truncate_chars

    def clone(self, **overrides: Any) -> "ResolvedProduct":
        values = {
            "product": ProductSpec(name=self.name, description=self.description, kind=self.kind),
            "role": self.role,
            "role_filter": list(self.role_filter),
            "developer": self.developer,
            "message_only": self.message_only,
            "clean_user_prompts": self.clean_user_prompts,
            "strip_boilerplate": self.strip_boilerplate,
            "truncate_chars": self.truncate_chars,
        }
        values.update(overrides)
        return ResolvedProduct(**values)

    def allows_role(self, role: Optional[str]) -> bool:
        normalized = str(role or "")
        if self.role_filter:
            return normalized in self.role_filter
        if self.role and normalized != self.role:
            return False
        if self.developer == "exclude":
            return normalized != "developer"
        if self.developer == "only":
            return normalized == "developer"
        return True

    def select_events(self, events: List[dict]) -> List[dict]:
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
                from .extract import extract_user_prompt

                text = extract_user_prompt(filtered.get("text", ""))
                if not text:
                    continue
                filtered["text"] = text

            if self.strip_boilerplate and filtered.get("kind") == "message":
                from .extract import extract_user_prompt

                if filtered.get("role") == "user":
                    text = extract_user_prompt(filtered.get("text", ""))
                    if not text:
                        continue
                    filtered["text"] = text

            selected.append(filtered)
        return selected

    def apply(self, messages: List[dict]) -> List[dict]:
        result = []
        for msg in messages:
            role = msg.get("role")
            if not self.allows_role(role):
                continue

            text = msg.get("text", "")
            if self.clean_user_prompts and role == "user":
                from .extract import extract_user_prompt

                text = extract_user_prompt(text)
                if not text:
                    continue

            if self.strip_boilerplate and role == "user":
                from .extract import extract_user_prompt

                text = extract_user_prompt(text)
                if not text:
                    continue

            if self.truncate_chars and len(text) > self.truncate_chars:
                text = text[: self.truncate_chars] + "..."

            result.append({"role": role, "timestamp": msg.get("timestamp", ""), "text": text})
        return result


class Preset:
    """Named export recipe with product selection and view policy."""

    def __init__(self, name: str, description: str, products: Optional[List[str]] = None, **filters: Any):
        self.name = name
        self.description = description
        self.products = list(products or [])
        self.filters = dict(filters)

    def as_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"description": self.description, "products": list(self.products)}
        result.update(self.filters)
        return result

    def resolve(
        self,
        *,
        role: Optional[str] = None,
        truncate: Optional[int] = None,
        include_developer: bool = False,
        strip_boilerplate: Optional[bool] = None,
    ) -> List[ResolvedProduct]:
        resolved: List[ResolvedProduct] = []
        for product_name in self.products:
            product = get_product(product_name)
            config = ResolvedProduct(
                product,
                role=self.filters.get("role"),
                developer=self.filters.get("developer"),
                message_only=bool(self.filters.get("message_only", False)),
                clean_user_prompts=bool(self.filters.get("clean_user_prompts", False)),
                strip_boilerplate=bool(self.filters.get("strip_boilerplate", False)),
                truncate_chars=self.filters.get("truncate_chars"),
            )

            if role:
                normalized = str(role).strip().lower()
                if normalized == "both":
                    config.role = None
                    config.role_filter = []
                elif normalized in ("user", "assistant"):
                    config.role = None
                    config.role_filter = [normalized]
                else:
                    raise ValueError(f"Invalid role: '{role}'. Use user, assistant or both.")

            if include_developer and config.developer == "exclude":
                config.developer = "include"

            if strip_boilerplate is not None:
                config.strip_boilerplate = bool(strip_boilerplate)

            if truncate is not None:
                config.truncate_chars = truncate if truncate > 0 else None

            resolved.append(config)

        return resolved


transcript = ProductSpec(
    name="transcript",
    description="Chronological Markdown transcript with tool calls, results, context, and developer instructions",
    kind="markdown",
)

memory = ProductSpec(
    name="memory",
    description="Raw structured JSONL for retrieval/debugging: message, tool, context, and output events in source order",
    kind="raw_jsonl",
)

rag = ProductSpec(
    name="rag",
    description="Normalized JSONL for embedding/indexing pipelines; user/assistant text only, developer content excluded by default",
    kind="normalized_jsonl",
)

faithful = ProductSpec(
    name="faithful",
    description="Byte-for-byte copy of the original Codex session JSONL",
    kind="source_jsonl",
)

PRODUCTS: Dict[str, ProductSpec] = {
    "transcript": transcript,
    "memory": memory,
    "rag": rag,
    "faithful": faithful,
}

PRESETS: Dict[str, Preset] = {
    "archive": Preset(
        "archive",
        "Lossless source JSONL plus a chronological Markdown transcript with tool activity",
        products=["faithful", "transcript"],
    ),
    "source": Preset(
        "source",
        "Source-only lossless byte-for-byte JSONL copy",
        products=["faithful"],
    ),
    "markdown": Preset(
        "markdown",
        "Lossy: chronological Markdown transcript including tool activity",
        products=["transcript"],
    ),
    "conversation": Preset(
        "conversation",
        "Lossy: clean Markdown dialogue only; excludes tool activity, generated context, and developer instructions",
        products=["transcript"],
        developer="exclude",
        message_only=True,
        clean_user_prompts=True,
        strip_boilerplate=True,
    ),
    "prompts": Preset(
        "prompts",
        "Lossy: human-authored user prompts only",
        products=["transcript"],
        role="user",
        developer="exclude",
        message_only=True,
        clean_user_prompts=True,
        strip_boilerplate=True,
    ),
    "memory": Preset(
        "memory",
        "Lossy: raw structured message, tool, and context events for retrieval/debugging",
        products=["memory"],
        developer="include",
    ),
    "rag": Preset(
        "rag",
        "Lossy: normalized message documents for LangChain, embeddings, and vector stores",
        products=["rag"],
        developer="exclude",
        message_only=True,
        clean_user_prompts=True,
        strip_boilerplate=True,
    ),
    "instructions": Preset(
        "instructions",
        "Lossy: explicit developer instructions only",
        products=["transcript"],
        developer="only",
        message_only=True,
    ),
}


def get_product(name: str) -> ProductSpec:
    if name not in PRODUCTS:
        available = ", ".join(PRODUCTS.keys())
        raise KeyError(f"Unknown product '{name}'. Available: {available}")
    return PRODUCTS[name]


def get_preset(name: str) -> Dict[str, Any]:
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise KeyError(f"Unknown preset '{name}'. Available: {available}")
    return PRESETS[name].as_dict()


def list_products() -> List[str]:
    return list(PRODUCTS.keys())


def list_presets() -> List[str]:
    return list(PRESETS.keys())


def _apply_product_options(product: ProductSpec, options: Dict[str, Any]) -> ResolvedProduct:
    options = options or {}

    developer = options.get("developer")
    if developer in {"default", "None", "", None}:
        developer = None

    role = None
    role_filter: Optional[List[str]] = None
    if "role" in options:
        role_value = str(options["role"]).strip().lower()
        if role_value == "both":
            role = None
            role_filter = []
        elif role_value in ("user", "assistant"):
            role = None
            role_filter = [role_value]
        else:
            raise ValueError(f"Invalid role option: {options['role']!r}")

    if developer is not None:
        developer = str(developer).strip().lower()
        if developer not in {"include", "exclude", "only"}:
            raise ValueError(f"Invalid developer option: {developer!r}")

    truncate_chars = None
    if "truncate" in options:
        value = options["truncate"]
        truncate_chars = None if value is None else value if isinstance(value, int) and value > 0 else None

    return ResolvedProduct(
        product,
        role=role,
        role_filter=role_filter,
        developer=developer,
        message_only=bool(options.get("message_only", False)),
        clean_user_prompts=bool(options.get("clean_user_prompts", False)),
        strip_boilerplate=bool(options.get("strip_boilerplate", False)),
        truncate_chars=truncate_chars,
    )


def resolve_preset(name: str) -> List[ResolvedProduct]:
    preset = get_preset(name)
    preset_filters = {
        key: value for key, value in preset.items() if key not in ("description", "product", "products")
    }

    if "products" in preset:
        product_specs = preset["products"]
    elif "product" in preset:
        product_specs = {preset["product"]: preset_filters}
    else:
        raise ValueError(f"Preset '{name}' does not define a product")

    resolved = []
    if isinstance(product_specs, dict):
        items = [(product_name, {**preset_filters, **(options or {})}) for product_name, options in product_specs.items()]
    else:
        items = [(product_name, dict(preset_filters)) for product_name in product_specs]

    for product_name, options in items:
        resolved.append(_apply_product_options(get_product(product_name), options or {}))

    return resolved


transcript_product = transcript
memory_product = memory
rag_product = rag
faithful_product = faithful
