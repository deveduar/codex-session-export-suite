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
python codexexport.py --preset markdown
python codexexport.py --preset source
python codexexport.py --preset archive

python codexexport.py --preset memory
python codexexport.py --preset rag
python codexexport.py --preset rag --strip-boilerplate

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

The export destination is controlled with `-o` / `--output` and defaults to the configured output directory or `./codex_exports`:

```bash
python codexexport.py --preset archive --output ./exports
python codexexport.py --preset conversation --output "C:\\tmp\\codex-export"
```

Preview the planned paths without writing files:

```bash
python codexexport.py --preset archive --dry-run
```
 
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

This inspects the latest export metadata under `codex_exports/` and reports which sessions are new, modified, unchanged, or missing from the current scan. It is useful when you want to confirm whether a fresh Codex export has already been captured or whether anything changed since the last run.

## CLI help

```bash
python codexexport.py --help
python codexexport.py --list-presets
```

## Disclaimer

This is an unofficial community tool. It is not affiliated with, endorsed by, or sponsored by OpenAI. "Codex" is used descriptively to refer to local Codex session files. OpenAI and Codex are trademarks of their respective owners.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
