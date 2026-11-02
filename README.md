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

```bash
python3 cli.py --preset markdown
python3 cli.py --preset source
python3 cli.py --preset archive

python3 cli.py --preset memory
python3 cli.py --preset rag
python3 cli.py --preset rag --strip-boilerplate

python3 cli.py --preset prompts
python3 cli.py --preset conversation
python3 cli.py --preset conversation --include-developer

```

On Windows, use `py cli.py --preset archive`.

## Input and output paths

The Codex input path is optional. If you omit it, the tool auto-detects the local Codex install (`CODEX_HOME`, `~/.codex`, or `%USERPROFILE%\.codex` on Windows).

If you want to point to a specific source explicitly, you can pass the Codex directory, its `sessions` directory, a subdirectory, or a single `.jsonl` file:

```bash
python3 cli.py /path/to/.codex --preset archive
```

The export destination is controlled with `-o` / `--output` and defaults to the configured output directory or `./codex_exports`:

```bash
python3 cli.py --preset archive --output ./exports
python3 cli.py --preset conversation --output "C:\\tmp\\codex-export"
```

Preview the planned paths without writing files:

```bash
python3 cli.py --preset archive --dry-run
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

The INI file is optional. It is only used when you explicitly tell the CLI which file to load via `--config`.

Example:

```bash
python3 cli.py --config ./codex_export.ini --preset archive
```

The exporter will also auto-detect a local `./codex_export.ini` if present, but a custom `--config` path is the clearest way to force a specific configuration for one run. CLI flags still override the config values for the current execution.

For the full precedence rules, preset-vs-runtime behavior, and metadata semantics, see [architecture.md](architecture.md).

## Check for updates

Compare the current Codex session set with the newest export run:

```bash
python3 cli.py --check-updates
```

This inspects the latest export metadata under `codex_exports/` and reports which sessions are new, modified, unchanged, or missing from the current scan. It is useful when you want to confirm whether a fresh Codex export has already been captured or whether anything changed since the last run.

## CLI Usage

```
Usage: cli.py [OPTIONS] [PATH]

  Export readable and machine-friendly views of local Codex sessions.

Options:
  --preset TEXT              Preset to use for exporting
  --products TEXT            Comma-separated list of products to include
  --role TEXT                Filter by role (e.g., user, assistant, developer)
  --include-developer         Include developer instructions in products that exclude them by default
  --strip-boilerplate        Remove recognized boilerplate from derived prompts/conversation output
  --truncate N                Keep the first N characters of each message or tool body; 0 disables truncation
  --recent-turns             Include only the most recent turns in the export
  --timestamps               Include timestamps in the export
  --include-archived         Include archived sessions in the export
  --check-updates            Compare current Codex sessions with the latest export run
  --dry-run                  Preview the planned paths without writing files
  --list-presets             List available products and presets
  --help                     Show this message and exit.
```

## Disclaimer

This is an unofficial community tool. It is not affiliated with, endorsed by, or sponsored by OpenAI. "Codex" is used descriptively to refer to local Codex session files. OpenAI and Codex are trademarks of their respective owners.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
