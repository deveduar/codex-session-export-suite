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
   - Examples: `transcript`, `memory`, `rag`, `faithful`.
   - It defines what the format is, not how a given export is filtered.

2. Preset
   - A named export recipe that combines one or more base products with a concrete policy.
   - Examples: `archive`, `source`, `markdown`, `conversation`, `prompts`, `instructions`.
   - A preset is not a product; it is a use-case bundle.

3. ResolvedProduct
   - The effective runtime state for one product in one export run.
   - This is where role filtering, developer inclusion, boilerplate stripping, truncation, and recent-turn trimming actually live.

This separation avoids the classic bug where product identity and export policy were mixed together.

## Base products

These are the real base output formats:

- `transcript` — chronological Markdown transcript with tool activity and context
- `memory` — raw structured JSONL for retrieval/debugging pipelines
- `rag` — normalized message JSONL for embeddings/vector stores
- `faithful` — byte-for-byte copy of the original session JSONL

A product is not “clean” or “raw” by default. Its behavior is defined by the runtime policy that is applied when it is exported.

## Presets

Presets are the user-facing export modes. They are recipes, not product identities.

- `archive` — source JSONL + transcript
- `source` — source-only lossless copy
- `markdown` — transcript view
- `conversation` — clean dialogue-only transcript; excludes developer text and tool activity by default
- `prompts` — user prompts only
- `memory` — raw retrieval/debugging events, includes developer records by default
- `rag` — normalized message documents for embeddings; excludes developer text by default
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

Each export creates a run under `codex_exports/` containing:

- `metadata.json` — machine-readable run summary
- `index.md` — human-readable summary
- generated product files and folders

The metadata records the effective run configuration, including the selected preset and the resolved filters, so the real behavior is always traceable.

## Layout policy

The exporter supports two on-disk layouts:

- `run` — default, timestamped run folder
- `flat` — direct-write output directory

This is an internal storage choice and is not treated as part of the exported content semantics.

## Change detection

`--check-updates` compares the current Codex scan against the latest export run using session fingerprints and output metadata. This helps detect new, modified, unchanged, or missing sessions without relying only on file timestamps.

## Configuration files and CLI overrides

The exporter supports configuration defaults through an INI file, but those defaults are not treated as the final truth of a run. The input path to the Codex session source is optional and is auto-detected when omitted.

The resolution order is:

1. explicit `--config <path>`
2. local `./codex_export.ini`
3. per-user config in the OS config directory
4. built-in defaults

The INI file is a default source for values such as:

- `codex_dir`
- `output_dir`
- `layout`
- `preset`
- `products`
- `role`
- `include_developer`
- `strip_boilerplate`
- `truncate`
- `recent_turns`
- `timestamps`
- `include_archived`

These values are then overridden at runtime by explicit CLI flags. In other words:

- config file = default recipe and run defaults
- CLI flags = final runtime override for this execution
- metadata = effective state of the resulting export

This is why a run created with `--preset conversation --include-developer` is not the same as a run whose preset is literally mutated. The preset still defines the base recipe, but the final resolved product state for that run is the truth that gets exported and recorded.


The following options are available in the configuration file (`codex_export.ini`) under the `[export]` section:

```ini
[export]
preset = archive
products =
role =
include_developer = false
strip_boilerplate = false
layout = run
truncate =
recent_turns =
timestamps = true
include_archived = false
```

- `preset`: Default export preset recipe.
- `products`: Comma-separated product list.
- `role`: Optional filter (`user`, `assistant`, `both`).
- `include_developer`: Include developer instructions in default-clean products for this run.
- `strip_boilerplate`: Drop recognized generated boilerplate from derived outputs for this run.
- `layout`: Internal filesystem mode: `run` (default) or `flat`.
- `truncate`: Max characters kept in message/tool bodies before truncation for this run.
- `recent_turns`: Keep only the most recent user turns for this run.
- `timestamps`: Include timestamps in Markdown output for this run.
- `include_archived`: Include archived sessions for this run.

These values act as defaults for the local configuration and may be overridden by CLI flags for a specific export run. The run summary and `metadata.json` track the effective export state for that run; `layout` remains an internal filesystem detail and does not appear in the public export summary.

## CLI combinations and constraints

The CLI supports several valid ways to choose the export behavior, but they are not semantically equivalent.

### 1. Preset only

Example:

```bash
python3 cli.py --preset conversation --output ./exports
```

This uses the preset as the base recipe. The selected product set and default policy come from that preset.

### 2. Products only

Example:

```bash
python3 cli.py --products transcript memory --output ./exports
```

This bypasses presets and resolves directly from the base product list.

### 3. Preset + runtime overrides

Examples:

```bash
python3 cli.py --preset conversation --include-developer --output ./exports
python3 cli.py --preset rag --strip-boilerplate --output ./exports
```

These are valid runs. The preset provides the base recipe, and the CLI flags override the effective policy for that export run only.

### 4. Direct product + runtime overrides

Example:

```bash
python3 cli.py --products transcript --role user --truncate 2000 --output ./exports
```

This bypasses preset resolution entirely and applies the override directly to the base product configuration.

### Constraints and semantics

- `--preset` and `--products` are mutually exclusive in intent: one selects a recipe, the other selects an explicit product list.
- `--role`, `--truncate`, `--include-developer`, and `--strip-boilerplate` are product/runtime overrides.
- `--recent-turns`, `--no-timestamps`, and `--include-archived` are run-level settings and affect the session scan/export as a whole.
- Values from the INI file are defaults only. A CLI flag always wins for that execution.
- The exported metadata must describe the resolved, effective run state, not the unmodified preset defaults.

In short: the preset is the starting recipe, the CLI is the override layer, and the metadata records the final effective state of the run.

## Notes

The project is intentionally compact and CLI-first. The code remains easy to inspect, but the architecture is explicit: product identity is real, preset composition is policy-driven, and the resolved runtime configuration is the final truth for each exported file.
