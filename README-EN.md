# Blink

**A repo manager that lives in your terminal.**

Blink is a lightweight terminal toolkit that helps developers manage local Git repositories and orchestrate AI-powered automation tasks. Dual-pane interactive UI — open it and go, never leave your terminal.

---

## What Does It Do?

### Repository Manager (TUI)

Browse, search, and manage all your Git repos in a beautiful terminal interface:

- **Auto-discovery** — Scans specified directories, automatically identifies all Git repos, and persists results to a local database
- **Real-time status** — Parallel fetching of branch name, dirty file count, ahead/behind info at a glance
- **Full-text search** — Instantly filter by name, path, remote URL, tags, or description
- **One-click actions** — Open in IDE, terminal, Finder, or jump to the remote repo in your browser
- **Quick push/pull** — No need to type git commands — push or pull with a single keystroke
- **Personalization** — Pin repos, set aliases, tags, and descriptions for quick identification

```
┌───────────────────────┬──────────────────────────────────────────┐
│ ── Repos ──────────   │ ── Detail ────────────────────────────── │
│   ▸ ★ name [tag]     │     Name      repo-name                  │
│     /path/to/repo    │     Path      /path/to/repo              │
│                      │     Repo      https://github.com/...      │
│                      │     Status    main ●                     │
│                      │ ───────────────────────────────────────── │
│                      │   ▸ Terminal  Open in Terminal   [Shift+1]│
│                      │     IDE       Open with IDE      [Shift+2]│
│                      │     Finder    Open in Finder      [Shift+3]│
│                      │ ───────────────────────────────────────── │
│                      │     Git       Open in Browser     [Shift+4]│
│                      │     Push      Push Changes         [Shift+5]│
│                      │     Pull      Pull Changes         [Shift+6]│
│                      │ ───────────────────────────────────────── │
│                      │     Task      Add todo task        [Shift+7]│
│                      │     Review    AI Code Review       [Shift+8]│
└───────────────────────┴──────────────────────────────────────────┘
```

### AI Task Engine (Loop)

Orchestrate AI-powered automation tasks through a YAML config file:

- **Auto-commit** — AI analyzes code changes and generates semantic commit messages automatically
- **Task orchestration** — Define tasks in `tasks.yaml`, executed in sequence — code writing, testing, committing
- **AI Code Review** — Structured review of teammates' branches, outputting APPROVE / DENY reports
- **Git safety** — Auto-commits dirty working trees before tasks, auto-creates feature branches
- **Multiple runners** — Supports both Claude CLI and Cybervisor as AI execution backends

---

## Why Blink?

|  |  |
|---|---|
| **Zero config** | `pip install` and run — first scan is automatic, no setup needed |
| **Stay in terminal** | Everything happens in your terminal — no window switching |
| **Keyboard-first** | Every action has a shortcut — `Shift+number` for one-key triggers |
| **Persistent cache** | Repo info stored in local SQLite — instant loading on subsequent starts |
| **AI-native** | Auto-commit, task orchestration, code review — all AI-powered |
| **Lightweight** | Core dependencies: only prompt-toolkit, click, and pyyaml |

---

## Quick Start

### Install

```bash
pip install blink-repo
```

### Launch

```bash
blink              # Launch the repo manager
```

On first launch, Blink scans your home directory for Git repos and opens the TUI when done. Subsequent launches use cached data and auto-clean stale entries.

### Common Commands

```bash
blink                          # Launch TUI
blink -R                       # Force rescan
blink commit -p .              # AI auto-commit changes in current directory
blink review <branch>          # AI Code Review for a branch
blink review <branch> -d       # Diff-only mode (no temp branch)
blink review -l                # List past review reports
blink run -s                   # Show task status
blink edit                     # Edit task file
blink log                      # View task logs
```

> Auto-commit and Code Review features require [Claude CLI](https://docs.anthropic.com/en/docs/claude-code).

---

## Keyboard Shortcuts

All shortcuts work in both the list and detail panels:

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate |
| `Enter` | Open in IDE (list) / Execute action (detail) |
| `/` | Search (works from any focus) |
| `Tab` / `→` | Switch to detail panel |
| `Esc` / `←` | Switch back to list |
| `Shift+1` | Open in terminal |
| `Shift+2` | Open in IDE |
| `Shift+3` | Open in Finder |
| `Shift+4` | Open remote repo in browser |
| `Shift+5` | Push changes |
| `Shift+6` | Pull latest |
| `Shift+7` | Add todo task |
| `Shift+8` | AI Code Review |
| `Shift+R` | Rescan |
| `Ctrl+C` ×2 | Quit |

### Search

Press `/` to open the search bar and filter repos in real time. Search scope: name, alias, description, path, remote URL, tags. Enter hides the search bar keeping results; Esc clears and restores all repos.

---

## Configuration

A default config is created at `~/.blink/config.json` on first run:

```json
{
  "scan_paths": ["~"],
  "exclude_dirs": [".Trash", ".cache", ".npm", ".docker", "Library", "node_modules"],
  "editor": "code",
  "preferred_ide": null,
  "auto_sync_days": 0,
  "nerd_fonts": false
}
```

| Field | Description |
|-------|-------------|
| `scan_paths` | Root directories to scan for Git repos |
| `exclude_dirs` | Directory names to skip during scan |
| `editor` | Default editor |
| `preferred_ide` | Preferred IDE (`v` VSCode / `u` Cursor / `a` Antigravity) |
| `auto_sync_days` | Auto-rescan interval in days (0 to disable) |
| `nerd_fonts` | Enable Nerd Font icons |

All data is stored in `~/.blink/`.

---

## Development

Blink is built with Python 3.9+ and [uv](https://docs.astral.sh/uv/). For setup, testing, debugging, and architecture details, see the [Development Guide](docs/development-EN.md).

Quick start:

```bash
git clone <repo-url> blink && cd blink
uv sync                    # Install dependencies
uv run blink               # Launch TUI
uv run pytest              # Run tests
```

---

## License

MIT
