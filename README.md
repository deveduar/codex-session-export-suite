# Codex Extension Exporter

Export readable and machine friendly views of local Codex sessions. The tool uses Python's standard library and runs on Windows, Linux, and macOS.

## Quick start

```bash
python3 cli.py --preset archive
```

On Windows, use `py cli.py --preset archive`. The tool looks for Codex under `CODEX_HOME` or `~/.codex` (`%USERPROFILE%\.codex` on Windows). To select an input explicitly, pass the Codex directory, its `sessions` directory, a subdirectory, or one `.jsonl` file:

```bash
python3 cli.py /path/to/.codex --preset archive
```

Preview the planned paths without writing files:

```bash
python3 cli.py --preset archive --dry-run
```

## Products and presets

Products are output formats; presets combine products and filters.

| Preset | Products and filtering | Data retention compared with source JSONL |
|---|---|---|
| `archive` | Transcript, memory, and faithful-message JSON | **Lossy overall.** The JSON product preserves raw payloads only for extracted messages; the other products contain transformed text. |
| `quick` | Faithful-message JSON | **Lossy.** Preserves raw payloads for extracted messages, but not the complete source file. |
| `study` | Truncated transcript and memory | **Lossy.** Transcript text is truncated; memory omits raw payloads. |
| `review` | Transcript and faithful-message JSON | **Lossy overall.** The JSON product keeps raw payloads for extracted messages; the transcript is a transformed view. |
| `notes` | Transcript with text truncated to about 500 characters | **Lossy.** Text is truncated. |
| `conversation` | Transcript with extracted user and assistant text | **Lossy.** Message structure and non-text records are omitted. |
| `prompts` | User messages only | **Lossy.** Assistant messages and non-text records are omitted. |
| `rag` | Memory JSONL | **Lossy.** Keeps extracted role, timestamp, and text only. |
| `digest` | Short extractive digest | **Lossy.** Text is shortened and source structure is omitted. |

**No preset is a lossless copy of the source JSONL.** The `faithful` product stores original payloads for recognized user or assistant messages that contain extractable text. It does not preserve every event, metadata record, or line in the original session file. Keep the original Codex JSONL files when exact source preservation is required. The `review` preset does not redact the raw payloads in its faithful JSON output.

| Product | Output |
|---|---|
| `transcript` | Markdown conversation |
| `memory` | JSONL with one extracted message per line |
| `faithful` | JSON containing extracted messages and their raw payloads |
| `digest` | Markdown with short text excerpts |

Examples:

```bash
python3 cli.py --preset notes
python3 cli.py --products transcript memory
python3 cli.py --preset prompts
python3 cli.py --list-presets
```

## Output layout

By default, each invocation creates a timestamped run directory. Product files are grouped by format, with a run index, product indexes, and `metadata.json`:

```text
codex_exports/
└── 2026-10-30_20-45-12_archive/
    ├── metadata.json
    ├── index.md
    ├── transcript/
    ├── memory/
    └── faithful/
```

Session filenames include the session date, thread or project name, and a short ID. Metadata contains export settings, counts, selected session metadata, and relative output paths; it omits account identifiers and full instruction payloads. Product directories are created only when they contain files. Existing flat exports are not moved.

To write new exports directly into the output directory, use `--flat` or set `layout = flat` in the config. The output directory defaults to `./codex_exports`; choose another with `-o/--output`.

## Configuration

The optional `codex_export.ini` file controls defaults. CLI arguments take precedence.

```ini
[codex]
dir =

[output]
dir = ./codex_exports
layout = run

[export]
preset =
products =
role =
truncate =
timestamps = true
```

Leave `codex.dir` empty for auto-detection. Set either `preset` or `products`; when both are set, `products` takes precedence. `layout` accepts `run` or `flat`. Paths support `~`, `$HOME`, and Windows `%USERPROFILE%` variables.

Use a different config file with `--config PATH`. Other useful options:

```text
--role user|assistant|both   Filter exported messages
--truncate N                Truncate text to N characters; 0 disables truncation
--no-timestamps             Omit timestamps from Markdown output
--flat                      Write directly in the output directory
--dry-run                   Preview paths without writing
--output DIR                Choose the output directory
```

Run `python3 cli.py --help` for the full command reference.

## Input and privacy

The exporter reads `.jsonl` files under `sessions/` by default. Archived sessions are not included automatically; pass the archived directory or a specific session file as the input path.

Exports may contain conversation text and raw message payloads. Run indexes and metadata can include local paths such as the session working directory. Review generated files before sharing them.

## License

This project is available under the MIT License; see [LICENSE](LICENSE).
