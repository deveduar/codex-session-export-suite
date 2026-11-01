"""Configuration loading for Codex Session Exporter.

Reads an INI file (no third-party dependencies) so the tool works on
Python 3.8+ on both Linux and Windows.
"""

from __future__ import annotations

import configparser
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


CONFIG_FILENAME = "codex_export.ini"

DEFAULTS: Dict[str, Any] = {
    "codex_dir": None,
    "output_dir": "./codex_exports",
    "layout": "run",
    "include_archived": False,
    "preset": None,
    "products": None,
    "role": None,
    "include_developer": False,
    "truncate": None,
    "recent_turns": None,
    "timestamps": True,
}


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


_PERCENT_VAR = re.compile(r"%([^%]+)%")


def _expand_percent_vars(text: str) -> str:
    """Expand Windows-style %NAME% variables on every platform."""
    return _PERCENT_VAR.sub(lambda match: os.environ.get(match.group(1), match.group(0)), text)


def expand_path(value: Optional[str]) -> Optional[Path]:
    """Expand ~ and environment variables in a path.

    Works with ``~/.codex``, ``$HOME/.codex`` and ``%USERPROFILE%\\.codex``.
    """
    if value is None:
        return None

    text = os.path.expandvars(_expand_percent_vars(str(value)))
    return Path(text).expanduser()


def user_config_path() -> Path:
    """Return the per-user configuration path for the current OS."""
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")

    return Path(base) / "codex_exporter" / "config.ini"


def find_config(explicit: Optional[str] = None) -> Optional[Path]:
    """Find the configuration file to use.

    Order:
        1. Explicit ``--config`` path.
        2. ``./codex_export.ini`` in the current directory.
        3. Per-user config (``%APPDATA%`` on Windows, ``~/.config`` elsewhere).
    """
    if explicit:
        path = expand_path(explicit)
        if path is None or not path.is_file():
            raise ConfigError(f"Configuration file not found: {explicit}")
        return path

    local_config = Path.cwd() / CONFIG_FILENAME
    if local_config.is_file():
        return local_config

    per_user_config = user_config_path()
    if per_user_config.is_file():
        return per_user_config

    return None


def detect_codex_dir() -> Optional[Path]:
    """Auto-detect the Codex data directory.

    Precedence:
        1. ``CODEX_HOME`` environment variable.
        2. ``~/.codex`` (``%USERPROFILE%\\.codex`` on Windows).
        3. ``$XDG_CONFIG_HOME/codex`` on non-Windows systems.
    """
    candidates: List[Path] = []

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        expanded = expand_path(codex_home)
        if expanded:
            candidates.append(expanded)

    candidates.append(Path.home() / ".codex")

    if os.name != "nt":
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            candidates.append(Path(xdg_config_home) / "codex")

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return candidates[0] if candidates else None


def _get(parser: configparser.ConfigParser, section: str, *keys: str) -> Optional[str]:
    """Read the first non-empty value from a section."""
    if not parser.has_section(section):
        return None

    for key in keys:
        if parser.has_option(section, key):
            value = parser.get(section, key).strip()
            if value:
                return value
    return None


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"Invalid boolean value: {value!r}")


def _parse_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid numeric value: {value!r}") from exc

    if number < 0:
        raise ConfigError(f"Value cannot be negative: {value!r}")
    return number


def _parse_layout(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in ("run", "flat"):
        return normalized
    raise ConfigError(f"Invalid layout value: {value!r}. Use run or flat.")


def _parse_products(value: str) -> Optional[List[str]]:
    """Parse a comma/space separated product list."""
    products = value.replace(",", " ").split()
    return products or None


def load_config(explicit: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration merged over built-in defaults.

    Command-line arguments override the values returned here, and these
    values override the internal defaults.
    """
    config = dict(DEFAULTS)
    config_path = find_config(explicit)

    if config_path is None:
        return config

    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error) as exc:
        raise ConfigError(f"Could not read {config_path}: {exc}") from exc

    codex_dir = _get(parser, "codex", "dir", "path")
    if codex_dir:
        config["codex_dir"] = codex_dir

    output_dir = _get(parser, "output", "dir", "path", "destination")
    if output_dir:
        config["output_dir"] = output_dir

    layout = _get(parser, "output", "layout")
    if layout:
        config["layout"] = _parse_layout(layout)

    preset = _get(parser, "export", "preset", "default_preset")
    if preset:
        config["preset"] = preset

    products = _get(parser, "export", "products")
    if products:
        config["products"] = _parse_products(products)

    role = _get(parser, "export", "role")
    if role:
        config["role"] = role

    include_developer = _get(parser, "export", "include_developer")
    if include_developer is not None:
        config["include_developer"] = _parse_bool(include_developer)

    truncate = _get(parser, "export", "truncate")
    if truncate is not None:
        config["truncate"] = _parse_int(truncate)

    recent_turns = _get(parser, "export", "recent_turns")
    if recent_turns is not None:
        config["recent_turns"] = _parse_int(recent_turns)

    timestamps = _get(parser, "export", "timestamps")
    if timestamps is not None:
        config["timestamps"] = _parse_bool(timestamps)

    include_archived = _get(parser, "export", "include_archived")
    if include_archived is not None:
        config["include_archived"] = _parse_bool(include_archived)

    # Also accept a flat [codex_export] / [defaults] section for convenience.
    for section in ("codex_export", "defaults"):
        flat_codex_dir = _get(parser, section, "codex_dir")
        if flat_codex_dir:
            config["codex_dir"] = flat_codex_dir

        flat_output_dir = _get(parser, section, "output_dir")
        if flat_output_dir:
            config["output_dir"] = flat_output_dir

        flat_layout = _get(parser, section, "layout")
        if flat_layout:
            config["layout"] = _parse_layout(flat_layout)

        flat_preset = _get(parser, section, "preset")
        if flat_preset:
            config["preset"] = flat_preset

        flat_products = _get(parser, section, "products")
        if flat_products:
            config["products"] = _parse_products(flat_products)

        flat_role = _get(parser, section, "role")
        if flat_role:
            config["role"] = flat_role

        flat_include_developer = _get(parser, section, "include_developer")
        if flat_include_developer is not None:
            config["include_developer"] = _parse_bool(flat_include_developer)

        flat_truncate = _get(parser, section, "truncate")
        if flat_truncate is not None:
            config["truncate"] = _parse_int(flat_truncate)

        flat_recent_turns = _get(parser, section, "recent_turns")
        if flat_recent_turns is not None:
            config["recent_turns"] = _parse_int(flat_recent_turns)

        flat_timestamps = _get(parser, section, "timestamps")
        if flat_timestamps is not None:
            config["timestamps"] = _parse_bool(flat_timestamps)

        flat_include_archived = _get(parser, section, "include_archived")
        if flat_include_archived is not None:
            config["include_archived"] = _parse_bool(flat_include_archived)

    config["_config_path"] = config_path
    return config
