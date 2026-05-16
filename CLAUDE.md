# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Blink is a lightweight terminal TUI tool for scanning, searching, and managing local git repositories. Written in Python, it uses `prompt-toolkit` for the TUI and `click` for CLI. Data is stored in SQLite under `~/.blink/`.

## Commands

```bash
uv sync                    # Install dependencies
uv run blink               # Launch the TUI
uv run blink --rescan      # Force full rescan before TUI
uv run pytest              # Run all tests
uv run pytest tests/test_scanner.py  # Run a single test file
uv run pytest -k test_scan_paths_finds_git_repos  # Run a single test
uv build                   # Build distributable packages
```

Insert `breakpoint()` in source code and run `uv run blink` for pdb debugging.

## Architecture

**Entry point**: `src/blink/cli.py` — click command that wires together Config, Store, Scanner, and BlinkApp.

**Core modules** (all in `src/blink/`):

- `models.py` — `Repo` and `Remote` dataclasses
- `config.py` — JSON config loader (`~/.blink/config.json`), with defaults for scan paths, excludes, editor
- `scanner.py` — `Scanner` class that walks filesystem to find `.git` dirs, then fetches remotes/description via git subprocess. Uses `ThreadPoolExecutor` for parallel processing. Supports both blocking and background (threaded) scan modes.
- `store.py` — SQLite persistence layer (WAL mode). Tables: `repos`, `remotes`, `schema_version`. Upsert-based writes. Full-text search across name/alias/description/path/remote URL.

**TUI** (`src/blink/tui/`):

- `app.py` — Main `BlinkApp` class. Composes the full-screen layout (search bar → repo list → status → footer) via `prompt_toolkit`. Handles all key bindings and orchestrates background scanning.
- `repo_list.py` — Custom `UIControl`/`Window` for the scrollable repo list
- `search.py` — `SearchBar` wrapping a `prompt_toolkit.Buffer`
- `actions.py` — Editor detection and launch (VSCode, Cursor, Antigravity, system open), clipboard via `pbcopy`
- `detail.py` — Placeholder for P1 detail panel (not yet implemented)

**Data flow**: Scanner finds git dirs → creates `ScanResult(repo, remotes)` → Store upserts into SQLite → TUI loads from Store for display/search.

## Key Patterns

- Store uses lazy SQLite connection (`_connect()` on first access) with `check_same_thread=False` for background scan support
- Scanner's `run_scan(blocking=True/False)` toggles between synchronous and threaded execution
- TUI uses `app.invalidate()` to trigger re-renders after state changes
- Config falls back to defaults if the file is missing or corrupted, and rewrites it
- Tests create real git repos via subprocess in `tmp_path` fixtures

## Planned Work (P1)

See `docs/plan/p1-enhancement.md` for the enhancement plan: two-line repo display, alias editing, tag system, and detail panel.
