# Codex Session Export Suite

Export local Codex sessions with control over fidelity and format. A single CLI provides byte-for-byte source copies, titled Markdown transcripts, run-wide event JSONL, and a normalized message corpus.

## Requirements

- Python 3.10+
- No external dependencies
- Windows, Linux, or mac

## Presets at a glance

| Preset | Use it when you want... |
|---|---|
| `source` | A byte-for-byte backup |
| `complete` | Source copy, full transcript, event memory, and normalized corpus |
| `markdown` | A chronological human-readable log |
| `conversation` | Clean dialogue only |
| `prompts` | Just the human prompts |
| `memory` | One run-wide JSONL of raw session events |
| `corpus` | One run-wide JSONL of normalized messages |
| `instructions` | Only developer instructions 

## Quick start

Run the portable entry point from the repository root. The examples below are
the command cheatsheet; comments distinguish session selection from per-session
turn filtering and faithful source copies from derived JSONL.

```bash
# No preset in the CLI or INI means the transcript product for all sessions.
python codexexport.py

# The broad bundle includes faithful source, transcript, event memory, corpus.
python codexexport.py --preset complete

# Keep only original source files, or export one run-wide derived JSONL.
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
`memory` and `corpus` are derived run-wide JSONL files, not faithful source
archives.

## Input and output paths

The Codex input path is optional. If you omit it, the tool auto-detects the local Codex install (`CODEX_HOME`, `~/.codex`, or `%USERPROFILE%\.codex` on Windows).

You can pass the Codex root, its `sessions` directory, a subdirectory, or one
`.jsonl` file as the positional source. Resolution order is positional source,
`codex_export.ini`, `CODEX_HOME`, `~/.codex`, then XDG. `--output` overrides the
configured destination, which defaults to `./exports`.

## Output layout

Every run creates one timestamped folder directly under the output directory. Run-wide JSONL artifacts live at its root; each session folder contains its faithful source copy and any Markdown transcript:

```
exports/
  2026-11-12_19-28-43_complete/
    index.md                     # root index, grouped by project
    metadata.json                # machine-readable run metadata
    index.memory.md              # per-product session index
    index.corpus.md              # per-product session index
    memory.jsonl                 # all raw events, tagged with session id/title
    corpus.jsonl                 # all normalized messages, tagged with session id/title
    2026-10-27_example_01a17f02/
      2026-10-27_example_01a17f02.faithful.jsonl
      2026-10-27_example_01a17f02.transcript.md
```

`memory.jsonl` and `corpus.jsonl` are each one file per run, not one file per session. Every line includes the session slug, ID, and title. `source` remains one byte-faithful original JSONL file per session. Markdown transcripts include YAML frontmatter and a session-title H1. The old `archive` and `rag` preset/product names are removed; use `complete` and `corpus` respectively.

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

`--list-sessions --json` includes canonical `created_at` and `updated_at` timestamps in UTC ISO 8601 (`Z`) form, plus a `revision` taken from the source JSONL file's `mtime_ns`. `started_at` remains the original source timestamp. The revision is a lightweight comparison token, not a timestamp for display. Export bundles separately record source size, mtime, and SHA-256 fingerprints for Codex's own update comparison; the listing token does not change that metadata. Session names use the source JSONL file's last-modified date in UTC; run folders use UTC `YYYYMMDDTHHMMSSZ` stamps.

Exit codes: `0` success, `1` configuration or source error, `2` no data (source valid but no sessions matched).
 
## Products and presets

Products are output formats. Presets are named recipes that choose a product set and default filter policy. A preset is not the final runtime state of a run: when the CLI passes flags like `--include-developer`, `--role`, `--truncate`, or `--strip-boilerplate`, those values override the preset for that run only.

| Preset | Products and filtering | Data retention |
|---|---|---|
| `complete` | Source JSONL + transcript + memory JSONL + corpus JSONL | Lossless source plus derived views |
| `source` | Source JSONL only | Lossless |
| `markdown` | Human-readable transcript | Derived view |
| `conversation` | Clean dialogue | Derived, excludes tool activity and developer text by default |
| `prompts` | User prompts only | Derived |
| `memory` | Run-wide raw structured events | Derived, includes developer records by default |
| `corpus` | Run-wide normalized message documents | Derived, excludes developer text by default |
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
