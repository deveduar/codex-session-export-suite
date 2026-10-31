# Codex Session Exporter (Python)

Export readable and machine friendly views of local Codex sessions. This Python CLI reads Codex session JSONL files and runs on Windows, Linux, and macOS.

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
| `archive` | Source JSONL and transcript | **Lossless source copy** plus a readable derived view. |
| `source` | Source JSONL only | **Lossless.** Copies each source file byte-for-byte. |
| `markdown` | Markdown of extracted messages without character truncation | **Lossy.** Omits source records and structure that are not represented in the transcript. |
| `prompts` | User messages only | **Lossy.** Assistant messages and non-text records are omitted. |
| `rag` | Memory JSONL | **Lossy.** Keeps extracted role, timestamp, and text only. |

`archive` includes the same byte-for-byte source copies as `source`, then adds a Markdown transcript. Choose `source` for a source-only backup and `archive` when you also want the readable view. Use `rag` separately for the JSONL memory representation; it contains the same extracted message text in a machine-friendly schema.

The `faithful` product copies the original session `.jsonl` byte-for-byte. It keeps all records, including metadata and tool events; role filters and truncation do not change this copy. Presets that include `faithful` (`archive` and `source`) therefore preserve the source, while their transcript remains a derived view. With no preset selected, the exporter already writes the same Markdown transcript without character truncation as `--preset markdown`.

| Product | Output |
|---|---|
| `transcript` | Markdown conversation |
| `memory` | JSONL with one extracted message per line |
| `faithful` | Unmodified source JSONL |

Examples:

```bash
python3 cli.py --preset markdown
python3 cli.py --preset source
python3 cli.py --products transcript memory
python3 cli.py --preset prompts
python3 cli.py --list-presets
python3 cli.py --check-updates
```

## Output layout

By default, each invocation creates a timestamped run directory. Product files are grouped by format, with a run index, product indexes, and `metadata.json`:

```text
codex_exports/
└── 2026-10-30_20-45-12_archive/
    ├── metadata.json
    ├── index.md
    ├── transcript/
    │   └── <project>/
    └── faithful/
        └── <project>/
```

Session filenames include the session date, thread or project name, and a short ID. Each product groups its session files in project-named subfolders (for example, `transcript/<project>/…` and `faithful/<project>/…`). The run-level `index.md` groups sessions by project and links to each product file; it also shows parent sessions when Codex provides parent-thread metadata. Product indexes list all files in that product. No per-project folders or indexes are created outside the product folders. Windows drive paths and their WSL `/mnt/<drive>/...` equivalents are normalized to the same project key. Metadata contains export settings, source fingerprints, counts, selected session metadata, and relative output paths; it omits account identifiers and full instruction payloads. Existing flat exports are not moved.

To write new exports directly into the output directory, use `--flat` or set `layout = flat` in the config. Flat mode skips the timestamped run and product folders, as well as run metadata and indexes; it changes the layout, not which sessions or products are exported. The output directory defaults to `./codex_exports`; choose another with `-o/--output`.

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
include_archived = false
```

Leave `codex.dir` empty for auto-detection. Set either `preset` or `products`; when both are set, `products` takes precedence. `layout` accepts `run` or `flat`. Set `include_archived = true` to include Codex's `archived_sessions` directory. Paths support `~`, `$HOME`, and Windows `%USERPROFILE%` variables.

Use a different config file with `--config PATH`. Other useful options:

```text
--role user|assistant|both   Filter exported messages
--truncate N                Keep the first N characters of each extracted message; 0 disables truncation
--no-timestamps             Omit timestamps from Markdown output
--flat                      Write directly in the output directory
--include-archived          Include archived_sessions when scanning the Codex root
--check-updates             Compare current source files with the latest run
--dry-run                   Preview paths without writing
--output DIR                Choose the output directory
```

Run `python3 cli.py --help` for the full command reference.

## Input and privacy

The exporter reads `.jsonl` files under `sessions/` by default. Use `--include-archived` or the matching INI setting to also include `archived_sessions`; you can still pass either folder directly as the input path. `--check-updates` compares session IDs and SHA-256 fingerprints with the latest run under the selected output directory. If a run has no fingerprints, comparison stops and asks for a new export; it does not guess from message counts or timestamps. “Not found in scan” means the session was outside the selected input path or absent; it does not by itself prove deletion.

The `faithful` source copy is intentionally unredacted and can contain IDs, local paths, instructions, tool data, and other metadata present in Codex's original file. Derived exports and run metadata can also contain conversation text and local paths. Review generated files before sharing them.

## License

This project is available under the MIT License; see [LICENSE](LICENSE).
