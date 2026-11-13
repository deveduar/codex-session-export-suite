# Codex Session Export Suite

Export local Codex sessions with control over fidelity and format. A single CLI with presets for every need—from byte-for-byte source archives to clean dialogue transcripts to structured JSONL built for RAG pipelines.

## Requirements

- Python 3.10+
- No external dependencies
- Windows, Linux, or mac

## Presets at a glance

| Preset | Use it when you want... |
|---|---|
| `source` | A byte-for-byte backup |
| `archive` | Backup + readable transcript |
| `markdown` | A chronological human-readable log |
| `conversation` | Clean dialogue only |
| `prompts` | Just the human prompts |
| `memory` | Raw retrieval/debugging JSONL |
| `rag` | Normalized message JSONL for embeddings |
| `instructions` | Only developer instructions 

## Quick start

Run the portable entry point from the repository root with your active Python interpreter:

```bash
# Default behavior: export the transcript product for all discovered sessions.
# An INI preset/products setting changes this default.
python codexexport.py

# Export the readable transcript product or the lossless archive preset.
python codexexport.py --preset markdown
python codexexport.py --preset archive

# Create a lossless source copy and structured retrieval products.
python codexexport.py --preset source
python codexexport.py --preset memory
python codexexport.py --preset rag
python codexexport.py --preset rag --strip-boilerplate

# Export only prompts or clean dialogue; optionally keep developer text.
python codexexport.py --preset prompts
python codexexport.py --preset conversation
python codexexport.py --preset conversation --include-developer
```

Replace `python` with the interpreter command used by your environment (for example, `python3` or `py`).

## Input and output paths

The Codex input path is optional. If you omit it, the tool auto-detects the local Codex install (`CODEX_HOME`, `~/.codex`, or `%USERPROFILE%\.codex` on Windows).

If you want to point to a specific source explicitly, you can pass the Codex directory, its `sessions` directory, a subdirectory, or a single `.jsonl` file:

```bash
python codexexport.py /path/to/.codex --preset archive
```

The source is resolved in this order: the positional argument, then the `dir` value in `codex_export.ini`, then `CODEX_HOME`, then `~/.codex`, then XDG auto-detection. The chosen source and its origin (`argument`, `config`, `env`, `home`, `xdg`) are reported and recorded in the run metadata.

The export destination is controlled with `-o` / `--output` and defaults to the configured output directory or `./exports`:

```bash
python codexexport.py --preset archive --output ./exports
python codexexport.py --preset conversation --output "C:\\tmp\\codex-export"
```

Preview the planned paths without writing files:

```bash
python codexexport.py --preset archive --dry-run
```

## List sessions

List discovered sessions without creating an export. The command accepts the
same source path and session selectors as an export, and `--json` emits
machine-readable session metadata:

```bash
python codexexport.py --list-sessions
python codexexport.py --list-sessions --last 5
python codexexport.py --list-sessions --json
```

## Output layout

Every run creates one timestamped folder directly under the output directory. Inside it, each session gets its own folder holding all of that session's product files as siblings:

```
exports/
  2026-11-12_19-28-43_rag/
    index.md                     # root index, grouped by project
    metadata.json                # machine-readable run metadata
    index.rag.md                 # per-product index
    2026-10-27_sistema-asus_01a17f02/
      2026-10-27_sistema-asus_01a17f02.rag.jsonl
      2026-10-27_sistema-asus_01a17f02.memory.jsonl
      2026-10-27_sistema-asus_01a17f02.transcript.md
```

Product extensions: `transcript` → `.md`, `memory` → `.jsonl`, `rag` → `.jsonl`, `faithful` → `.jsonl`. This is a breaking change from the older `<product>/<project>/` tree; the former `--flat` layout has been removed.

`--check-updates` only compares against runs under the selected output directory.

## Selecting sessions

Export only specific sessions, or only the most recent ones:

```bash
python codexexport.py --sessions 01a17f02 01a087aa
python codexexport.py --last 5
```

`--sessions` matches the session id, its short form, or the source filename. `--last N` keeps the N most recent sessions by session timestamp. This is distinct from `--recent-turns`, which trims turns *within* each selected session.

For example, export only the last five user turns from each of the five newest
sessions:

```bash
python codexexport.py --preset conversation --last 5 --recent-turns 5
```

`--recent-turns` retains the last N user turns and the following assistant and
tool events; developer context before that window is preserved. The run-level
`recent_turns` value and each session's pre-filter `source_message_count` are
recorded in `metadata.json` when the option is active.

## Machine-readable output and exit codes

```bash
python codexexport.py --preset rag --dry-run --json
python codexexport.py --check-updates --json
```

`--json` prints a single JSON object on stdout (and implies `--quiet`). `-q` / `--quiet` suppresses per-file and informational lines but keeps errors and a final summary. Errors go to stderr.

Exit codes: `0` success, `1` configuration or source error, `2` no data (source valid but no sessions matched).
 
## Products and presets

Products are output formats. Presets are named recipes that choose a product set and default filter policy. A preset is not the final runtime state of a run: when the CLI passes flags like `--include-developer`, `--role`, `--truncate`, or `--strip-boilerplate`, those values override the preset for that run only.

| Preset | Products and filtering | Data retention |
|---|---|---|
| `archive` | Source JSONL + transcript | Lossless source + readable derived view |
| `source` | Source JSONL only | Lossless |
| `markdown` | Human-readable transcript | Derived view |
| `conversation` | Clean dialogue | Derived, excludes tool activity and developer text by default |
| `prompts` | User prompts only | Derived |
| `memory` | Raw structured retrieval events | Derived, includes developer records by default |
| `rag` | Normalized message documents | Derived, excludes developer text by default |
| `instructions` | Developer instructions only | Derived |

For the full behavior matrix, cleanup rules, and architecture notes, see [architecture.md](architecture.md).

## Configuration file

The CLI auto-detects `./codex_export.ini` (or a per-user config) when present. Use `--config` to select a specific file explicitly.

Example:

```bash
python codexexport.py --config ./codex_export.ini --preset archive
```

CLI flags override config values for the current execution.

For the full precedence rules, preset-vs-runtime behavior, and metadata semantics, see [architecture.md](architecture.md).

## Check for updates

Compare the current Codex session set with the newest export run:

```bash
python codexexport.py --check-updates
```

This inspects the latest export metadata under the configured output directory (default `./exports/`) and reports which sessions are new, modified, unchanged, or missing from the current scan. It is useful when you want to confirm whether a fresh Codex export has already been captured or whether anything changed since the last run.

## CLI help

```bash
python codexexport.py --help
python codexexport.py --list-presets
```

## Disclaimer

This is an unofficial community tool. It is not affiliated with, endorsed by, or sponsored by OpenAI. "Codex" is used descriptively to refer to local Codex session files. OpenAI and Codex are trademarks of their respective owners.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
