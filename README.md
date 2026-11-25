# Codex Session Export Suite

Export local Codex sessions with control over fidelity and format. A single CLI provides byte-for-byte source copies, titled Markdown transcripts, session-structured memory JSONL with nested subagents, and flattened corpus documents.

## Requirements

- Python 3.10+
- No external dependencies
- Windows, Linux, or mac

## Presets at a glance

| Preset | Use it when you want... |
|---|---|
| `source` | A byte-for-byte backup |
| `complete` | Source copy, full transcript, nested session memory, and flattened corpus documents |
| `markdown` | A chronological human-readable log |
| `conversation` | Clean dialogue only |
| `prompts` | Just the human prompts |
| `memory` | One JSONL record per root session with nested subagent records |
| `corpus` | One flattened text document per root session |
| `instructions` | Only developer instructions 

## Quick start

Run the portable entry point from the repository root. The examples below are
the command cheatsheet; comments distinguish session selection from per-session
turn filtering and faithful source copies from derived JSONL.

```bash
# No preset in the CLI or INI means the transcript product for all sessions.
python codexexport.py

# The broad bundle includes faithful source, transcript, nested memory, corpus.
python codexexport.py --preset complete

# Keep only original source files, or export one derived JSONL product.
python codexexport.py --preset source
python codexexport.py --preset memory
python codexexport.py --preset corpus

# Markdown views: full activity, clean conversation, or prompts only.
python codexexport.py --preset markdown
python codexexport.py --preset prompts
python codexexport.py --preset conversation
python codexexport.py --preset conversation --include-developer

# Presets can be combined with runtime overrides; products can be selected directly.
python codexexport.py --preset corpus --strip-boilerplate
python codexexport.py --products transcript memory --role assistant --truncate 2000

# Select sessions, then optionally trim turns inside each selected session.
python codexexport.py --sessions 01a17f02 01a087aa --preset complete
python codexexport.py --preset conversation --last 5 --recent-turns 5

# List sessions without exporting; --json is machine-readable.
python codexexport.py --list-sessions
python codexexport.py --list-sessions --last 5 --json

# Preview without writes, inspect a plan, or compare the latest run.
python codexexport.py --preset complete --dry-run --json
python codexexport.py --list-presets --json
python codexexport.py --check-updates --json

# Override source, config, or destination for one invocation.
python codexexport.py /path/to/.codex --config ./codex_export.ini --preset complete --output ./exports
```

Replace `python` with the interpreter command used by your environment (for
example, `python3` or `py`). `complete` keeps the original source per session;
`memory` and `corpus` are distinct derived JSONL products written beside the
other session files in each project folder, not faithful source archives.

## Input and output paths

The Codex input path is optional. If you omit it, the tool auto-detects the local Codex install (`CODEX_HOME`, `~/.codex`, or `%USERPROFILE%\.codex` on Windows).

You can pass the Codex root, its `sessions` directory, a subdirectory, or one
`.jsonl` file as the positional source. Resolution order is positional source,
`codex_export.ini`, `CODEX_HOME`, `~/.codex`, then XDG. `--output` overrides the
configured destination, which defaults to `./exports`.

## Output layout

Every run creates one `<timestamp>_<label>` folder directly under the output directory. `--run-label` overrides the default label derived from the preset or product list. Session artifacts are grouped directly in a project folder named `<YYYY-MM-DD>_<project>_<hash12>`; the date is the newest included session in that project and the suffix is the first 12 hex digits of SHA-256 over the canonical cwd/workspace-root key. A missing path uses `no-project_<hash12>`. Windows drive paths and their `/mnt/<drive>` WSL forms hash to the same ID.

```
exports/
  20261112T192843Z_complete/
    index.md                     # root index, grouped by project
    metadata.json                # machine-readable run metadata
    index.memory.md              # per-product session index
    index.corpus.md              # per-product session index
    corpus.jsonl                 # one flat document per root session
    memory.jsonl                 # one nested document per root session
    2026-10-27_example-project_a289bbc5b59c/
      2026-10-27_example_01a17f02.faithful.jsonl
      2026-10-27_example_01a17f02.transcript.md
    2026-10-26_no-project_5f1c0aa9b2d3/
      2026-10-26_session_02b3c4d5.faithful.jsonl
      2026-10-26_session_02b3c4d5.transcript.md
```

There is no date-only folder above the project folder and no per-session folder. Each session file name keeps the `{date}_{slug}_{short-id}` shape, where the date comes from the source JSONL mtime in UTC, then the session timestamp, then a filename date, otherwise `unknown-date`. `memory` writes one `memory.jsonl` at the run root with one nested record per root session and subagent sessions as children; nested children do not receive their own memory file. `corpus` writes one `corpus.jsonl` file at the run root with one flattened document per root session, including child text.
 `source` remains one byte-faithful original JSONL file per session. Markdown transcripts include YAML frontmatter and a session-title H1. Sessions with no extractable content do not receive empty `memory` or `corpus` lines; they remain listed as skipped in run metadata. A selected subagent whose parent is not selected is emitted as its own record with `parent_unresolved: true` instead of being promoted to a root; it is not treated as a parent of unrelated sessions. The old `archive` and `rag` preset/product names are removed; use `complete` and `corpus` respectively.


`--check-updates` only compares against runs under the selected output directory.

## Selecting sessions

`--sessions` matches the session ID, short ID, or source filename. `--last N`
selects the most recent whole sessions. These differ from `--recent-turns`,
which limits turns *within* each selected session.

`--recent-turns` retains the last N user turns and the following assistant and
tool events; developer context before that window is preserved. The run-level
`recent_turns` value and each session's pre-filter `source_message_count` are
recorded in `metadata.json` when the option is active.

## Machine-readable output and exit codes

`--json` prints a single JSON object on stdout (and implies `--quiet`). `-q` / `--quiet` suppresses per-file and informational lines but keeps errors and a final summary. Errors go to stderr.

`--list-sessions --json` includes canonical `created_at` and `updated_at` timestamps in UTC ISO 8601 (`Z`) form, plus a `revision` taken from the source JSONL file's `mtime_ns`. `started_at` remains the original source timestamp. The revision is a lightweight comparison token, not a timestamp for display. Export bundles separately record source size, mtime, and SHA-256 fingerprints for Codex's own update comparison; the listing token does not change that metadata. Session names use the source JSONL file's last-modified date in UTC; run folders use UTC `YYYYMMDDTHHMMSSZ` stamps. Export envelopes and `metadata.json` list per-product `artifacts` as paths relative to the run root.

Exit codes: `0` success, `1` configuration or source error, `2` no data (source valid but no sessions matched).
 
## Products and presets

Products are output formats. Presets are named recipes that choose a product set and default filter policy. A preset is not the final runtime state of a run: when the CLI passes flags like `--include-developer`, `--role`, `--truncate`, or `--strip-boilerplate`, those values override the preset for that run only.

| Preset | Products and filtering | Data retention |
|---|---|---|
| `complete` | Source JSONL + transcript + nested memory JSONL + flattened corpus JSONL | Lossless source plus distinct derived views |
| `source` | Source JSONL only | Lossless |
| `markdown` | Human-readable transcript | Derived view |
| `conversation` | Clean dialogue | Derived, excludes tool activity and developer text by default |
| `prompts` | User prompts only | Derived |
| `memory` | Session-structured events, messages, parts, usage, and nested subagents | Derived, includes developer records by default |
| `corpus` | One flattened corpus document per root session | Derived, excludes developer text by default |
| `instructions` | Developer instructions only | Derived |

For the full behavior matrix, cleanup rules, and architecture notes, see [architecture.md](architecture.md).

## Configuration file

The CLI auto-detects `./codex_export.ini` (or a per-user config). Use
`--config` to choose another file; explicit CLI flags override its values.

For the full precedence rules, preset-vs-runtime behavior, and metadata semantics, see [architecture.md](architecture.md).

## Check for updates

`--check-updates` compares the current scan with the latest run under the
configured output directory (default `./exports/`) and reports new, modified,
unchanged, or not-found sessions.

## CLI help

Run `python codexexport.py --help` for the complete flag reference.

## Disclaimer

This is an unofficial community tool. It is not affiliated with, endorsed by, or sponsored by OpenAI. "Codex" is used descriptively to refer to local Codex session files. OpenAI and Codex are trademarks of their respective owners.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
