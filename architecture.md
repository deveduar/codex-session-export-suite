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

## Notes

The project is intentionally compact and CLI-first. The code remains easy to inspect, but the architecture is explicit: product identity is real, preset composition is policy-driven, and the resolved runtime configuration is the final truth for each exported file.
