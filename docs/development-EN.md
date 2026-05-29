# Blink Development Guide

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [git](https://git-scm.com/) — Version control
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) (optional, for AI feature development)

## Setup

```bash
git clone <repo-url> blink && cd blink
uv sync
```

## Running

```bash
uv run blink              # Launch TUI
uv run blink -R           # Force rescan
```

## Testing

```bash
uv run pytest                              # All tests
uv run pytest tests/test_scanner.py        # Single file
uv run pytest -k test_scan_paths_finds_git_repos  # Single test
```

## Debugging

Insert `breakpoint()` anywhere in the source code and run `uv run blink`. The program will enter pdb at the breakpoint.

## Building

```bash
uv build    # Build distribution packages
```

## Project Structure

```
src/
  cli.py              Entry point, click group
  models.py           Repo/Remote/RepoStatus data classes
  logger.py           Daily rotating logger
  config.py           JSON config loading
  scanner.py          Repo scanning + parallel git status fetching
  store.py            SQLite persistence (WAL), full-text search
  tui/                TUI module
    app.py            Main application class
    styles.py         Style definitions
    layout.py         Dual-pane layout
    key_bindings.py   Key bindings
    status_bar.py     Status bar
    repo_list.py      List widget
    detail.py         Detail panel
    search.py         Search bar
    actions.py        IDE detection/launch, clipboard
    icons.py          Nerd Font icon constants
  loop/               Loop task engine
    cmd_run.py        run subcommand
    cmd_edit.py       edit subcommand
    cmd_commit.py     commit subcommand
    cmd_log.py        log subcommand
    cmd_review.py     review subcommand
    task.py           Task orchestration
    state.py          State management
    git_ops.py        Git operations
    runner/           Runner abstractions
tests/                Test files
docs/                 Documentation
  agents/             AI collaboration docs
```

## Data Directory

```
~/.blink/
  config.json         User configuration
  blink.db            SQLite database
  loop/               Task system
    tasks.yaml        Task definitions
    state.json        Runtime state
    logs/             Execution logs
    archive/          Completed task archives
  logs/               Application logs
```

## Detailed Documentation

| Document | Content |
|----------|---------|
| [Loop Module](agents/loop.md) | Loop product overview, architecture, task config, runners, state management, Code Review |
| [Architecture & Data Flow](agents/architecture.md) | Entry points, module responsibilities, complete data flow |
| [TUI Details](agents/tui.md) | TUI module responsibilities, focus management, edit mode, exit mechanism |
| [UI Spec & Shortcuts](agents/ui-spec.md) | Layout diagrams, area specs, shortcut table, narrow terminal fallback |
| [Key Development Patterns](agents/key-patterns.md) | Store lazy connection, scan modes, IDE selection, commit/pull, testing |
| [Review Flow](agents/review-flow.md) | Complete AI Code Review flow |
