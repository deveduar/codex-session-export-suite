---
name: codex-session-export-suite
description: Export local Codex sessions, inspect available export presets and products, preview runs, or compare exports. Use when working with this repository's codexexport.py entry point or codex_export.ini configuration.
---

# Codex Session Exporter

Use this workflow to list options, preview, or export local Codex sessions.

## Procedure

1. Run the root-level `codexexport.py` with the Python interpreter active for this workspace. Do not guess the interpreter name; resolve it from the environment or project setup, and ask if it is ambiguous.
2. Read the CLI's current options or available export recipes when needed:

   ```text
   <python> codexexport.py --help
   <python> codexexport.py --list-presets
   ```

   Treat these outputs as the source of truth for supported flags, products, presets, descriptions, and preset recipes. Do not duplicate or guess them.
3. Use `--preset` for a named recipe, or `--products` for an explicit product selection. Do not pass both.
4. Use `--dry-run` when the user wants to inspect the planned export before writing files. Use `--check-updates` when they want to compare current sessions with the latest export. Add `--json` for machine-readable output and `--quiet` to reduce noise.
5. Use `--sessions <id...>` to export specific sessions, or `--last N` for the N most recent. This selects whole sessions; `--recent-turns` instead trims turns within each session.
6. Run the requested export and report the effective output location and any CLI errors. Each run produces one timestamped folder with per-session subfolders holding sibling product files.

## Output and exit codes

Each run writes one folder under `--output` containing `metadata.json`, `index.md`, and `index.<product>.md`, plus one folder per session holding that session's product files as siblings (for example `<slug>.rag.jsonl` and `<slug>.transcript.md`). Exit codes are `0` success, `1` configuration/source error, and `2` no data.

## Configuration

`codex_export.ini` in this repository is the example for reusable defaults. The CLI auto-detects it from the current directory; use `--config <path>` to select a different config file. Config values are defaults, and CLI flags take precedence for that run.

Use the config for reusable settings such as the Codex input directory, output directory, preset or products, session selection (`sessions`, `last`), and export filters. Consult the file and `--help` for the supported settings and flags rather than reproducing their full reference here.
