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
| `archive` | Source JSONL and chronological transcript with tool activity | **Lossless source copy** plus a readable derived view. |
| `source` | Source JSONL only | **Lossless.** Copies each source file byte-for-byte. |
| `markdown` | Chronological Markdown of messages, tool calls, and results | **Lossy.** Omits source records and metadata that are not represented in the transcript. |
| `conversation` | Clean dialogue only; excludes tool activity, generated context, and developer instructions by default | **Lossy.** Omits tool calls, tool results, context blocks, and developer instructions unless `--include-developer` is used. |
| `prompts` | Human-authored user prompts only | **Lossy.** Removes generated context, environment blocks, automated review messages, and all assistant/tool records. |
| `rag` | Structured JSONL of messages and tool activity | **Lossy.** Keeps useful event fields; developer instructions are opt-in. `faithful` remains the complete source. |
| `instructions` | Explicit developer instructions only | **Lossy.** Exports only records with `role: developer`; user, assistant, and tool events are omitted. |

`archive` includes the same byte-for-byte source copies as `source`, then adds a chronological Markdown transcript with tool activity. Choose `source` for a source-only backup and `archive` when you also want the readable view. Use `conversation` for a clean dialogue-only Markdown export. `rag` writes messages, tool calls, tool results, and structured file-change/web-search events as separate JSONL records. `instructions` exports only explicit Codex `developer` records.

Explicit `developer` records are labeled **Developer instruction** in `archive`, `markdown`, and `conversation` when included. They are not treated as assistant messages and are never reclassified from message text. Generated `<environment_context>…</environment_context>` blocks are removed from derived products while `source`/`faithful` keeps the original bytes. Known user-role boilerplate such as `AGENTS.md instructions`, `<recommended_plugins>`, IDE context envelopes, and automated approval/review prompts is removed from `prompts` and `conversation`; unknown prose is preserved rather than guessed away. Recognized XML-like context blocks are handled generically, so new Codex wrappers with the same shape are detected without changing the code.

The `faithful` product copies the original session `.jsonl` byte-for-byte. It keeps all records, including metadata and tool events; role filters, recency selection, and truncation do not change this copy. Presets that include `faithful` (`archive` and `source`) therefore preserve the source, while their Markdown products remain derived views. With no preset selected, the exporter writes the same full activity transcript as `--preset markdown`.

| Product | Output |
|---|---|
| `transcript` | Chronological Markdown with messages and tool activity |
| `conversation` | Clean Markdown conversation without tool activity or generated context |
| `memory` | JSONL with one structured message or activity event per line |
| `instructions` | Markdown containing only explicit developer instructions |
| `faithful` | Unmodified source JSONL |

Examples:

```bash
python3 cli.py --preset markdown
python3 cli.py --preset source
python3 cli.py --products transcript memory
python3 cli.py --preset prompts
python3 cli.py --preset conversation
python3 cli.py --preset conversation --include-developer
python3 cli.py --preset instructions
python3 cli.py --products transcript faithful
python3 cli.py --preset markdown --recent-turns 10
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

Session filenames include the session date, thread or project name, and a short ID. Each product groups its session files in project-named subfolders (for example, `transcript/<project>/…` and `faithful/<project>/…`). The run-level `index.md` groups sessions by project and links to each product file; it also shows parent sessions when Codex provides parent-thread metadata. Product indexes list files, item counts, and any sessions omitted from that product. No per-project folders or indexes are created outside the product folders. Windows drive paths and their WSL `/mnt/<drive>/...` equivalents are normalized to the same project key. The run-level index shows per-session developer instruction counts and token usage when available; usage values are ordered as input, cached input, cache-write input, output, reasoning output, and total. `metadata.json` contains the complete usage objects and run summary, alongside export settings, source fingerprints, counts, selected session metadata, and relative output paths. Usage is cumulative for the source thread, including with `--recent-turns`; unavailable values mean Codex did not record a usable snapshot. Metadata omits account identifiers and full instruction payloads. Counts distinguish sessions with any output from sessions with derived outputs, and source-only sessions from sessions skipped entirely; per-product omitted counts are also recorded. Existing flat exports are not moved.

`metadata.json` stores the latest cumulative `thread_token_usage` snapshot found in each rollout. It includes input, cached input, cache-write input, output, reasoning output, total tokens, and a count of source usage records. The run-level `usage_summary` sums one latest snapshot per unique session ID and reports the number of sessions with and without usage. Missing data is marked unavailable, not zero; totals may therefore be partial. Cached input is included in input tokens, and reasoning output is included in output tokens. These local counters describe recorded token usage and are not a bill or an account-plan meter. Token usage metadata does not alter Markdown or RAG content.

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
include_developer = false
truncate =
recent_turns =
timestamps = true
include_archived = false
```

Leave `codex.dir` empty for auto-detection. Set either `preset` or `products`; when both are set, `products` takes precedence. `layout` accepts `run` or `flat`. Set `include_archived = true` to include Codex's `archived_sessions` directory. Paths support `~`, `$HOME`, and Windows `%USERPROFILE%` variables.

Use a different config file with `--config PATH`. Other useful options:

```text
--role user|assistant|both   Filter messages and events by role
--include-developer         Include developer instructions in products that exclude them by default
--truncate N                Keep the first N characters of each message or tool body; 0 disables truncation
--recent-turns N            Keep the last N whole user turns and their tool events
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

`--recent-turns N` treats each user message as the start of a turn and keeps the last N turns with all following assistant/tool events, without cutting individual messages. It applies to derived products; `faithful` still copies the complete source file. No preset truncates text by default. `--truncate N` is an explicit per-body prefix limit.

`prompts` and `conversation` remove recognized generated context, but they remain lossy. If you need every byte of context, use `source`, `faithful`, or `archive`; unrecognized prose is preserved in those products. The `faithful` source copy is intentionally unredacted and can contain IDs, local paths, instructions, tool data, and other metadata present in Codex's original file. The `transcript` and `memory` products include tool inputs and outputs, which may themselves contain sensitive data. Derived exports and run metadata can also contain conversation text and local paths. Review generated files before sharing them.

## License

This project is available under the MIT License; see [LICENSE](LICENSE).
