# Architecture Overview

## Purpose

This project turns local Codex session JSONL files into exportable artifacts for humans, debugging, and indexing workflows. The CLI focuses on a clean split between:

- actual output formats (`products`)
- named export recipes (`presets`)
- effective runtime configuration (`ResolvedProduct`)

## Core model

The exporter uses three distinct layers:

1. ProductSpec
   - A real output format.
   - Examples: `transcript`, `memory`, `corpus`, `faithful`.
   - It defines what the format is, not how a given export is filtered.

2. Preset
   - A named export recipe that combines one or more base products with a concrete policy.
   - Examples: `complete`, `source`, `markdown`, `conversation`, `prompts`, `instructions`.
   - A preset is not a product; it is a use-case bundle.

3. ResolvedProduct
   - The effective runtime state for one product in one export run.
   - This is where role filtering, developer inclusion, boilerplate stripping, truncation, and recent-turn trimming actually live.

This separation avoids the classic bug where product identity and export policy were mixed together.

## Base products

These are the real base output formats:

- `transcript` — chronological Markdown transcript with tool activity and context
- `memory` — raw structured JSONL for retrieval/debugging pipelines
- `corpus` — normalized message JSONL for indexing and retrieval
- `faithful` — byte-for-byte copy of the original session JSONL

A product is not “clean” or “raw” by default. Its behavior is defined by the runtime policy that is applied when it is exported.

## Presets

Presets are the user-facing export modes. They are recipes, not product identities.

- `complete` — source JSONL + transcript + run-wide memory and corpus JSONL
- `source` — source-only lossless copy
- `markdown` — transcript view
- `conversation` — clean dialogue-only transcript; excludes developer text and tool activity by default
- `prompts` — user prompts only
- `memory` — raw retrieval/debugging events, includes developer records by default
- `corpus` — normalized message documents; excludes developer text by default
- `instructions` — developer instructions only

The important rule is simple:

- same product can be reused under different presets
- same preset can resolve to different effective runtime behavior depending on CLI/config overrides

## Export pipeline

The normal flow is:

1. Discover Codex session files
2. Parse each JSONL session into events
3. Apply session-level filtering and cleanup
4. Resolve the selected preset into concrete per-product runtime configs
5. Format each product
6. Write the run directory, metadata, and index files

## Runtime policy

The actual export policy is resolved at runtime and stored in each `ResolvedProduct`:

- role filter (`user`, `assistant`, `both`)
- developer inclusion mode (`include`, `exclude`, `only`)
- message-only mode
- prompt cleaning
- boilerplate stripping
- truncation length
- recent-turn retention

This is why a format like `transcript` can appear in several preset variants without the product itself pretending to know which policy is correct.

## Source fidelity vs derived output

The exporter intentionally separates different kinds of output:

- source-faithful output: original session copies and raw event data
- human-readable output: transcript and cleaned dialogue views
- retrieval-oriented output: memory and normalized message JSONL

These are different uses, not different “types of product truth”.

## Runs and metadata

Each export creates one timestamped run folder directly under the configured output directory (default `./exports/`). The run folder contains:

- `metadata.json` — machine-readable run summary (schema version 8)
- `index.md` — root index grouped by project
- `index.<product>.md` — one per-product index per exported product
- one folder per session, named after the session slug

Session-scoped files are siblings sharing the session slug. The raw memory and normalized corpus are run-wide files at the run root:

```
<run>/<session_slug>/
  <session_slug>.transcript.md
  <session_slug>.faithful.jsonl
<run>/memory.jsonl
<run>/corpus.jsonl
```

The session slug keeps the `{date}_{slugified-label}_{short_id}` form. Project information is metadata-only and used for grouping in the root index.

The metadata records the effective run configuration, including the resolved source and its origin, the selected preset, and the resolved filters, so the real behavior is always traceable.
Each JSONL record carries `session`, `session_id`, and `session_title`; `metadata.json` lists run-level files in `product_artifacts` and records which sessions contributed each product. `complete` resolves distinct policies per product, so the faithful source is untouched, `memory` retains developer events, and `corpus` excludes developer content and cleans user prompts by default.

`--list-sessions` uses the same discovery and selection rules but only reads
session metadata; it creates no run directory or export files. `--recent-turns`
trims events within each session, while `--last` and `--sessions` select whole
session files. The active `recent_turns` value and each filtered session's
`source_message_count` are recorded in run metadata.

Transcripts are currently one file per session and are not chunked. If chunking
is added, it should preserve complete events and produce an index rather than
splitting at arbitrary byte offsets.

## Layout policy

The exporter has a single on-disk layout: one timestamped run folder per invocation, with one sibling-file folder per session. The former `--flat` layout and its `layout` INI key have been removed. The run folder is always created directly under `--output`, which keeps launcher-style directory detection working.

## Machine-readable output and exit codes

- `--json` emits a single JSON object on stdout (and implies `--quiet`). The shape varies by mode: dry-run/export preflight, `--check-updates` comparison, and normal export result.
- `-q` / `--quiet` suppresses per-file and informational lines while keeping errors and one final summary.
- Exit codes: `0` success, `1` configuration or source error, `2` no data (source valid but no sessions matched).
- Human-readable errors go to stderr; data and progress go to stdout.

## Change detection

`--check-updates` compares the current Codex scan against the latest export run using session fingerprints and output metadata. This helps detect new, modified, unchanged, or missing sessions without relying only on file timestamps.
It uses the configured output directory; changing its default does not migrate
older runs from another directory.

## Configuration files and CLI overrides

Configuration values are defaults, not final truth. The exporter resolves settings in this order:

1. explicit `--config <path>`
2. local `./codex_export.ini`
3. per-user config in the OS config directory
4. built-in defaults

The Codex session input path itself is optional. When resolving it, the exporter uses this precedence: the positional argument, then the INI `codex_dir`, then `CODEX_HOME`, then `~/.codex`, then XDG auto-detection. The winning source and its origin (`argument`, `config`, `env`, `home`, `xdg`, or `none`) are recorded in `metadata.json`.

Example:

```bash
python codexexport.py --config ./codex_export.ini --preset complete
```

The INI file is a default source for values such as:

- `codex_dir`
- `output_dir`
- `preset`
- `products`
- `role`
- `include_developer`
- `strip_boilerplate`
- `truncate`
- `recent_turns`
- `sessions`
- `last`
- `timestamps`
- `include_archived`

These values are then overridden at runtime by explicit CLI flags. The final effective state for a run is what matters: preset defaults are a starting point, CLI flags define the actual export, and `metadata.json` records the real runtime configuration.

The following options are available in the config file under the `[export]` section:

```ini
[export]
preset = complete
products =
role =
include_developer = false
strip_boilerplate = false
truncate =
recent_turns =
sessions =
last =
timestamps = true
include_archived = false
```

- `preset`: Default export preset recipe.
- `products`: Comma-separated product list.
- `role`: Optional filter (`user`, `assistant`, `both`).
- `include_developer`: Include developer instructions in default-clean products for this run.
- `strip_boilerplate`: Drop recognized generated boilerplate from derived outputs for this run.
- `truncate`: Max characters kept in message/tool bodies before truncation for this run.
- `recent_turns`: Keep only the most recent user turns for this run.
- `sessions`: Export only these sessions (ids, short ids, or source filenames).
- `last`: Export only the N most recent sessions by session timestamp.
- `timestamps`: Include timestamps in Markdown output for this run.
- `include_archived`: Include archived sessions for this run.

## CLI combinations and constraints

The CLI supports several valid ways to choose the export behavior, but they are not semantically equivalent.

### 1. Preset only

Example:

```bash
python codexexport.py --preset conversation --output ./exports
```

This uses the preset as the base recipe. The selected product set and default policy come from that preset.

### 2. Products only

Example:

```bash
python codexexport.py --products transcript memory --output ./exports
```

This bypasses preset resolution and applies the product list directly.

### 3. Preset + runtime overrides

Examples:

```bash
python codexexport.py --preset conversation --include-developer --output ./exports
python codexexport.py --preset corpus --strip-boilerplate --output ./exports
```

These are valid runs. The preset provides the base recipe, and the CLI flags override the effective policy for that export run only.

### 4. Direct product + runtime overrides

Example:

```bash
python codexexport.py --products transcript --role user --truncate 2000 --output ./exports
```

This bypasses preset resolution entirely and applies the override directly to the base product configuration.

### Constraints and semantics

- `--preset` and `--products` are mutually exclusive in intent: one selects a recipe, the other selects an explicit product list.
- `--role`, `--truncate`, `--include-developer`, and `--strip-boilerplate` are product/runtime overrides.
- `--recent-turns`, `--no-timestamps`, and `--include-archived` are run-level settings and affect the session scan/export as a whole.
- `--sessions` and `--last` are session-selection settings: they choose whole sessions, whereas `--recent-turns` trims turns within every selected session.
- A CLI flag always wins over config defaults for that execution.
- The exported metadata must describe the resolved runtime state, not the unmodified preset defaults.

In short: the preset is the starting recipe, the CLI is the override layer, and the metadata records the final effective state of the run.

## Notes

The project is intentionally compact and CLI-first. The code remains easy to inspect, but the architecture is explicit: product identity is real, preset composition is policy-driven, and the resolved runtime configuration is the final truth for each exported file.

This is not a mathematically pure layering model in the strict sense: presets define default policy, but a specific run may still override those defaults via `--config` or CLI flags. The important invariant is that the base product remains neutral; the override happens on a resolved runtime copy, not by mutating the product definition itself.

For example, a preset such as `conversation` may default to `developer=exclude` and `strip_boilerplate=true`, but a single run can still resolve to a different effective state by passing `--include-developer` or a different `--role`. In other words, preset values are the default recipe, while `ResolvedProduct` is the actual truth for that export run.
