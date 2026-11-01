# Codex Session Exporter (Python)

Export readable and machine friendly views of local Codex sessions. This Python CLI reads Codex session JSONL files and runs on Windows, Linux, and macOS.

## Quick start

```bash
python3 cli.py --preset archive
python3 cli.py --preset markdown
python3 cli.py --preset source

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
| `archive` | Source JSONL and chronological transcript with tool activity | **Lossless source copy** plus a readable derived view. |
| `source` | Source JSONL only | **Lossless.** Copies each source file byte-for-byte. |
| `markdown` | Chronological Markdown of messages, tool calls, and results | **Lossy.** Omits source records and metadata that are not represented in the transcript. |
| `conversation` | Clean dialogue only; excludes tool activity, generated context, and developer instructions by default | **Lossy.** Omits tool calls, tool results, context blocks, and developer instructions unless `--include-developer` is used. |
| `prompts` | Human-authored user prompts only | **Lossy.** Removes generated context, environment blocks, automated review messages, and all assistant/tool records. |
| `rag` | Structured JSONL of messages and tool activity | **Lossy.** Keeps useful event fields; developer instructions are included by default because retrieval benefits from explicit instructions, while raw boilerplate remains in the structured event log unless you opt into cleaning with `--strip-boilerplate`. `faithful` remains the complete source. |
| `instructions` | Explicit developer instructions only | **Lossy.** Exports only records with `role: developer`; user, assistant, and tool events are omitted. |

`archive` includes the same byte-for-byte source copies as `source`, then adds a chronological Markdown transcript with tool activity. Choose `source` for a source-only backup and `archive` when you also want the readable view. Use `conversation` for a clean dialogue-only Markdown export. `rag` writes messages, tool calls, tool results, and structured file-change/web-search events as separate JSONL records; developer records are included by default, and boilerplate is stripped only when you explicitly opt into `--strip-boilerplate`. `instructions` exports only explicit Codex `developer` records.

Explicit `developer` records are labeled **Developer instruction** in `archive`, `markdown`, and `conversation` when included. They are not treated as assistant messages and are never reclassified from message text. Generated `<environment_context>…</environment_context>` blocks are removed from derived products while `source`/`faithful` keeps the original bytes. Known user-role boilerplate such as `AGENTS.md instructions`, `<recommended_plugins>`, IDE context envelopes, and automated approval/review prompts is removed from `prompts` and `conversation`; unknown prose is preserved rather than guessed away. In structured `rag` output, those blocks are kept by default so the raw event log remains faithful to the session; use `--strip-boilerplate` when you want the cleaned version.

## Configuration

The following options are available in the configuration file (`codex-export.ini`) under the `[export]` section:

```ini
[export]
preset = archive
products =
role =
include_developer = false
strip_boilerplate = false
truncate =
recent_turns =
timestamps = true
include_archived = false
```

- `preset`: The preset to use for exporting. Default is `archive`.
- `products`: A comma-separated list of products to include in the export.
- `role`: The role to filter by (e.g., `user`, `assistant`, `developer`).
- `include_developer`: Whether to include developer instructions in the export. Default is `false`.
- `strip_boilerplate`: Whether to strip boilerplate text from the export. Default is `false`.
- `truncate`: The number of turns to include in the export. Default is all turns.
- `recent_turns`: Whether to include only the most recent turns in the export. Default is `false`.
- `timestamps`: Whether to include timestamps in the export. Default is `true`.
- `include_archived`: Whether to include archived sessions in the export. Default is `false`.

## Check for updates

Compare the current Codex session set with the newest export run:

```bash
python3 cli.py --check-updates
```

This inspects the latest export metadata under `codex_exports/` and reports which sessions are new, modified, unchanged, or missing from the current scan. It is useful when you want to confirm whether a fresh Codex export has already been captured or whether anything changed since the last run.

## Examples

```bash
python3 cli.py --preset rag
python3 cli.py --preset rag --strip-boilerplate
python3 cli.py --preset prompts
python3 cli.py --preset conversation
python3 cli.py --preset conversation --include-developer
python3 cli.py --check-updates
```

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
