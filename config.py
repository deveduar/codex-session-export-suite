"""Configuration loading for Codex Extension Exporter.

Reads an INI file (no third-party dependencies) so the tool works on
Python 3.8+ on both Linux and Windows.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_FILENAME = "codex_export.ini"

DEFAULTS: Dict[str, Any] = {
    "codex_dir": "~/.codex",
    "output_dir": "./codex_exports",
    "preset": None,
    "role": None,
    "truncate": None,
    "timestamps": True,
}


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


def expand_path(value: Optional[str]) -> Optional[Path]:
    """Expand ~ and environment variables in a path.

    Works with ``~/.codex``, ``$HOME/.codex`` and ``%USERPROFILE%\\.codex``.
    """
    if value is None:
        return None

    text = os.path.expandvars(str(value))
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
            raise ConfigError(f"No existe el archivo de configuración: {explicit}")
        return path

    local_config = Path.cwd() / CONFIG_FILENAME
    if local_config.is_file():
        return local_config

    per_user_config = user_config_path()
    if per_user_config.is_file():
        return per_user_config

    return None


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
    if normalized in ("1", "true", "yes", "on", "si", "sí"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"Valor booleano no válido: {value!r}")


def _parse_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"Valor numérico no válido: {value!r}") from exc

    if number < 0:
        raise ConfigError(f"El valor no puede ser negativo: {value!r}")
    return number


def load_config(explicit: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration merged over built-in defaults.

    Precedence is handled by the CLI: command-line arguments override the
    values returned here, and these values override the internal defaults.
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
        raise ConfigError(f"No se pudo leer {config_path}: {exc}") from exc

    codex_dir = _get(parser, "codex", "dir", "path")
    if codex_dir:
        config["codex_dir"] = codex_dir

    output_dir = _get(parser, "output", "dir", "path", "destination")
    if output_dir:
        config["output_dir"] = output_dir

    preset = _get(parser, "export", "preset", "default_preset")
    if preset:
        config["preset"] = preset

    role = _get(parser, "export", "role")
    if role:
        config["role"] = role

    truncate = _get(parser, "export", "truncate")
    if truncate is not None:
        config["truncate"] = _parse_int(truncate)

    timestamps = _get(parser, "export", "timestamps")
    if timestamps is not None:
        config["timestamps"] = _parse_bool(timestamps)

    # Also accept a flat [codex_export] / [defaults] section for convenience.
    for section in ("codex_export", "defaults"):
        flat_codex_dir = _get(parser, section, "codex_dir")
        if flat_codex_dir:
            config["codex_dir"] = flat_codex_dir

        flat_output_dir = _get(parser, section, "output_dir")
        if flat_output_dir:
            config["output_dir"] = flat_output_dir

        flat_preset = _get(parser, section, "preset")
        if flat_preset:
            config["preset"] = flat_preset

        flat_role = _get(parser, section, "role")
        if flat_role:
            config["role"] = flat_role

        flat_truncate = _get(parser, section, "truncate")
        if flat_truncate is not None:
            config["truncate"] = _parse_int(flat_truncate)

        flat_timestamps = _get(parser, section, "timestamps")
        if flat_timestamps is not None:
            config["timestamps"] = _parse_bool(flat_timestamps)

    config["_config_path"] = config_path
    return config
