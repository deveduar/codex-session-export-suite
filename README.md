# Codex Extension Exporter

Portable Python tool to extract and export local Codex conversations as Markdown, JSONL, or JSON. It works on Linux and Windows and has no third-party dependencies.

There is no installation step and no console alias. Run `cli.py` directly:

- Linux/macOS: `python3 cli.py ...`
- Windows: `py cli.py ...`

---

## Quick start

Linux/macOS:

```bash
python3 cli.py --preset notes
```

Windows CMD:

```cmd
py cli.py --preset notes
```

Windows PowerShell:

```powershell
py cli.py --preset notes
```

By default, the tool auto-detects Codex in `CODEX_HOME` or `~/.codex` (`%USERPROFILE%\.codex` on Windows), so you do not need to pass a path every time.

---

## Input path

The first argument can be:

- the Codex root directory
- the `sessions` directory
- a year/month subdirectory
- a single `.jsonl` file

Linux/macOS:

```bash
python3 cli.py --preset notes
python3 cli.py ~/.codex --preset notes
python3 cli.py ~/.codex/sessions/2026/10 --preset notes
python3 cli.py ~/.codex/sessions/2026/10/30/rollout-2026-10-30T12-00-00-abc.jsonl
```

Windows CMD:

```cmd
py cli.py --preset notes
py cli.py "%USERPROFILE%\.codex" --preset notes
py cli.py "%USERPROFILE%\.codex\sessions\2026\10" --preset notes
py cli.py "%USERPROFILE%\.codex\sessions\2026\10\30\rollout-2026-10-30T12-00-00-abc.jsonl"
```

Windows PowerShell:

```powershell
py cli.py --preset notes
py cli.py "$env:USERPROFILE\.codex" --preset notes
py cli.py "$env:USERPROFILE\.codex\sessions\2026\10" --preset notes
```

> `~` is expanded by Python, but cmd and PowerShell do not expand it. In Windows use `%USERPROFILE%` in CMD, `$env:USERPROFILE` in PowerShell, or omit the path and let auto-detection find Codex.

---

## Output directory

Use `-o/--output` to choose where exported files are written:

Linux/macOS:

```bash
python3 cli.py --preset notes -o ./codex_exports
```

Windows CMD:

```cmd
py cli.py --preset notes -o "%USERPROFILE%\codex_exports"
```

Windows PowerShell:

```powershell
py cli.py --preset notes -o "$env:USERPROFILE\codex_exports"
```

---

## Products and presets

A **product** is a single output format. A **preset** is a named combination of one or more products.

### Products

| Product | Description | Output |
|---------|-------------|--------|
| `transcript` | Full conversation in Markdown, in chronological order | `.md` |
| `memory` | One JSON line per message for RAG or another AI | `.jsonl` |
| `faithful` | Lossless JSON archive per session | `.json` |
| `digest` | Short extractive summaries of conversation messages | `.md` |

### Presets

| Preset | Products | Description |
|--------|----------|-------------|
| `archive` | `transcript` + `memory` + `faithful` | Full backup: transcript, memory corpus and faithful raw session |
| `quick` | `faithful` | Faithful raw session only |
| `study` | `transcript` (truncated) + `memory` | Readable transcript plus searchable memory corpus |
| `review` | `transcript` (no reasoning) + `faithful` | Transcript without reasoning plus faithful raw session |
| `notes` | `transcript` (truncated) | Plain transcript with text truncated to ~500 chars |
| `conversation` | `transcript` (dialogue only) | Dialogue only: no tools, patches or reasoning |
| `prompts` | `transcript` (user only) | User prompts only |
| `rag` | `memory` | Searchable memory corpus for retrieval |
| `digest` | `digest` | Short extractive summaries of conversation messages |

Examples:

```bash
# Expand a preset into its products
python3 cli.py --preset archive

# Export specific products
python3 cli.py --products transcript memory faithful

# Only user prompts
python3 cli.py --products transcript --role user

# Truncate text
python3 cli.py --preset notes --truncate 300

# List products and presets
python3 cli.py --list-presets
```

`--products` accepts products only. `--preset` accepts presets only.

Each product writes its own file type (`session_....md`, `memory_....jsonl`, `faithful_....json`, `digest_....md`), so products in the same preset do not overwrite each other.

---

## Auto-detection

The Codex directory is resolved in this order:

1. Path passed as the first argument.
2. `dir` in `codex_export.ini`.
3. `CODEX_HOME` environment variable.
4. `~/.codex` (`%USERPROFILE%\.codex` on Windows).
5. `$XDG_CONFIG_HOME/codex` on non-Windows systems.

The detected directory is printed when the export starts. If the detected directory has no sessions, pass the correct path explicitly or set it in the config file.

---

## Configuration

`codex_export.ini` changes the defaults:

```ini
[codex]
# Leave empty to auto-detect CODEX_HOME or ~/.codex.
# Windows example: dir = %USERPROFILE%\.codex
dir =

[output]
dir = ./codex_exports

[export]
# Leave empty to use the transcript product.
preset =
# Explicit products, separated by commas or spaces.
products =
# user, assistant, or both. Leave empty for no filter.
role =
# Truncate text to N characters. Leave empty for no truncation.
truncate =
timestamps = true
```

Precedence: **CLI arguments > config file > built-in defaults**.

If both `preset` and `products` are set, `products` wins.

Configuration locations searched automatically:

1. `./codex_export.ini` in the current directory.
2. Per-user config:
   - Windows: `%APPDATA%\codex_exporter\config.ini`
   - Linux: `~/.config/codex_exporter/config.ini`

Use a specific file with:

```bash
python3 cli.py --config ./my_config.ini
```

Paths accept `~`, `$HOME`, and `%USERPROFILE%`. In INI files, write Windows paths without quotes.

---

## CLI options

```
positional arguments:
  codex_dir             Codex directory, sessions directory, subdirectory, or .jsonl file

options:
  -h, --help            Show help
  -o, --output DIR      Output directory (default: config or ./codex_exports)
  --config FILE         INI configuration file
  -p, --preset PRESET   Export preset
  --products NAME...    Products to export
  --role ROLE           user, assistant, or both
  --truncate N          Truncate text to N characters (0 disables truncation)
  --no-timestamps       Hide timestamps
  --dry-run             Show what would be done without writing files
  --list-presets        List products and presets
  --version             Show version
```

---

## Codex data locations

Linux:

```
~/.codex/
├── sessions/
│   └── 2026/10/27/rollout-....jsonl
├── archived_sessions/
├── session_index.jsonl
└── config.toml
```

Windows:

```
%USERPROFILE%\.codex\
├── sessions\
│   └── 2026\10\27\rollout-....jsonl
├── archived_sessions\
├── session_index.jsonl
└── config.toml
```

Only sessions under `sessions/` are read automatically. Archived conversations in `archived_sessions/` are not processed by default, but you can pass that directory or a specific `.jsonl` file as the first argument.

---

## Using the same repository on Windows and Linux

- There is no installation step; run `cli.py` from the repository on each system.
- `codex_exports/` is ignored by Git, so exported files are not committed.
- The default output is `./codex_exports`, relative to the directory where you run the command.
- Filenames are sanitized for Windows-invalid characters.

If both systems write to the same shared output directory and export the same session, the file is overwritten because the name is deterministic. Use a different output directory per system:

Linux/macOS:

```bash
python3 cli.py --preset notes -o ./codex_exports/linux
```

Windows CMD:

```cmd
py cli.py --preset notes -o "%USERPROFILE%\codex_exports\windows"
```

---

## Repository structure

```
codex_extension_exporter/
├── cli.py              # Entry point and CLI
├── config.py           # INI loading and Codex auto-detection
├── extract.py          # JSONL parsing and filtering
├── products.py         # Products and presets
├── output.py           # Markdown, JSONL, and JSON formatting
├── codex_export.ini    # Default configuration
└── README.md
```

---

## License

No license file is included in this repository.
