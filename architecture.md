# Architecture Overview

## Purpose

This project turns local Codex session JSONL files into exportable, readable artifacts. The CLI supports different output modes, from lossless source copies to derived transcripts and structured JSONL for retrieval pipelines.

## High-level structure

- `cli.py` — command-line entry point and orchestration
- `config.py` — configuration parsing and validation
- `extract.py` — source parsing, role detection, content cleanup, and event filtering
- `products.py` — product definitions and preset metadata
- `output.py` — formatting for Markdown and JSONL export files
- `organize.py` — run directory creation, metadata writing, and run/index generation
- `README.md` — user-facing quick start and usage notes

## Export model

The tool works in two layers:

1. Product selection
   - A product is a concrete output format, such as `conversation`, `transcript`, `memory`, or `faithful`.
   - Each product defines what kind of events are included and how they are formatted.

2. Preset selection
   - A preset combines products and filters into a common use case.
   - Examples include `archive`, `conversation`, `prompts`, `rag`, and `instructions`.

This separation keeps the system flexible: users can pick a preset for common workflows or compose a custom product list when they need a specific output.

## Event processing pipeline

The main flow is:

1. Discover JSONL session files from the Codex directory
2. Read the source content and metadata
3. Extract events from each session
4. Apply role, developer, and boilerplate rules
5. Optionally trim recent turns or truncate long content
6. Generate each product file
7. Collect session summaries and write run metadata/index files

## Product behavior

### Source-faithful products

- `faithful` copies the original JSONL file without transformation.
- `source` also keeps byte-for-byte copies in the export set.

These are the lossless outputs used for backups and audits.

### Derived products

- `transcript` writes a chronological Markdown transcript with tool activity.
- `conversation` writes a cleaned dialogue view and omits tool activity and developer instructions by default.
- `prompts` exports only relevant user-authored prompt text.
- `instructions` exports explicit developer instruction records.
- `memory` writes structured JSONL events for retrieval or indexing workflows.

## Filtering and cleanup policies

The exporter intentionally distinguishes between:

- source fidelity
- user-facing readability
- retrieval-oriented structured output

Some cleanup is default in derived output:

- generated environment context is removed from conversational exports
- boilerplate is stripped only when explicitly requested for some products
- developer instructions are excluded from default conversation output unless requested

This keeps raw session data available in source-faithful products while producing cleaner artifacts for human review and indexing.

## Runs and metadata

Each export creates a run directory under `codex_exports/` containing:

- `metadata.json` — machine-readable summary of the run
- `index.md` — human-readable summary of the export
- per-product subfolders and generated files

The metadata captures:

- selected preset and products
- filters such as role, recent turns, and developer inclusion
- whether archived sessions were included
- session-level output counts and product skips
- source fingerprints for change detection

## Change detection

The `--check-updates` command compares the current Codex scan with the latest export run by using source fingerprints from session records. This helps determine whether sessions are new, modified, unchanged, or missing from the current scan without relying on a fragile timestamp-only heuristic.

## Layout policy

The exporter supports two filesystem layouts:

- `run` — default, creates a timestamped run directory
- `flat` — writes files directly into the output directory

This layout setting is internal to the on-disk structure and is not surfaced in the public run summary or metadata JSON because it is not part of the exported content semantics.

## Notes on skipped products

A product may be marked as skipped for a session when it has no exportable content for that specific product. This does not mean the session is dropped from the run. It means only that the selected export format had no relevant data in that session.

For example, a session may contain metadata and initialization records but no visible transcript content. It can still be included in the run while `transcript` remains skipped for that session.

## Future growth

The current code is intentionally compact and CLI-first. If the project later needs packaging or reuse as a library, it can be moved into a standard `src/` package layout while keeping the CLI as the public entry point.
