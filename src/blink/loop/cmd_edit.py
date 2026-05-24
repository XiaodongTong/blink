"""blink edit — open ~/.blink/loop/tasks.yaml in editor, optionally add a task."""

import argparse
import re
import subprocess

import yaml

from blink.loop import config

EDIT_HELP = """\
Open ~/.blink/loop/tasks.yaml in your editor.

Uses the same IDE selection as the TUI (VSCode, Cursor, Antigravity).
The choice is saved to ~/.blink/config.json as preferred_ide.
Override anytime with: blink edit --editor <command>

Task file format (~/.blink/loop/tasks.yaml):

  tasks:
    - name: My task
      dir: ~/projects/my-project
      prompt: |
        Describe what Claude should do.
      # OR:
      prompt_file: ./prompts/my-task.md
      branch: true           # true=auto, "custom/name", false=skip
      review: false          # true=post-task self-review for code quality
      use: cybervisor        # cybervisor (default) or claude
      max_rounds: 5          # only for use: claude
      commit-model: haiku    # haiku, sonnet, or opus

  Each task runs in the specified directory. Completed tasks are
  archived to ~/.blink/loop/archive/ after each run cycle.

  Project-level AI instructions can be placed in ./docs/tloop/constitution.md
  within the project directory. If present, blink will auto-load them as
  constitutional rules when running tasks with the claude runner.

  Use --review (or -r) flag to enable post-task code review for all tasks,
  or set review: true on individual tasks.
"""


def _prompt_ide_choice():
    from blink.config import Config
    from blink.tui.actions import detect_editors, IDE_CHOICES

    cfg = Config()
    editors = detect_editors()
    available = [(key, name) for key, name in IDE_CHOICES
                 if key in editors and editors[key].available]
    if not available:
        print("No IDE found. Install VSCode, Cursor, or Antigravity.")
        return None

    print(f"{config.BOLD}Choose your IDE:{config.RESET}\n")
    for i, (_, name) in enumerate(available, 1):
        print(f"  {i}) {name}")
    print()

    while True:
        choice = input(f"Enter number [1-{len(available)}]: ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(available):
                key, name = available[idx - 1]
                cfg.set("preferred_ide", key)
                print(f"{config.GREEN}Default IDE set to {name}.{config.RESET}\n")
                return key
        print("Invalid choice, try again.")


def add_parser(subparsers):
    p = subparsers.add_parser(
        "edit",
        help="Open ~/.blink/loop/tasks.yaml in editor",
        description=EDIT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("path", nargs="?", help="Add a task with this dir and open the file")
    p.add_argument("--editor", help="Override editor command for this session")
    p.set_defaults(func=handle)


def _add_task(path):
    """Append a guided task entry with dir=path to tasks.yaml."""
    config.TLOOP_HOME.mkdir(exist_ok=True)
    if not config.TASKS_FILE.exists():
        config.TASKS_FILE.write_text(config.SAMPLE_TASKS_YAML)

    try:
        data = yaml.safe_load(config.TASKS_FILE.read_text()) or {}
    except yaml.YAMLError:
        data = {}

    tasks = data.get("tasks") or []
    task_num = len(tasks) + 1

    raw = config.TASKS_FILE.read_text()

    # Detect indentation of existing task entries (default: 2 spaces)
    indent = "  "
    m = re.search(r'^(\s*)- \w', raw, re.MULTILINE)
    if m:
        indent = m.group(1)
    inner = indent + "  "

    new_entry = (
        f"{indent}- name: Task {task_num}\n"
        f"{inner}dir: {path}\n"
        f"{inner}prompt: |\n"
        f"{inner}  Describe what Claude should do.\n"
        f"{inner}# prompt_file: ./prompts/my-task.md\n"
        f"{inner}branch: true           # true=auto, \"custom/name\", false=skip\n"
        f"{inner}review: false          # true=post-task self-review for code quality\n"
        f"{inner}use: cybervisor        # cybervisor (default) or claude\n"
        f"{inner}max_rounds: 5          # only for use: claude\n"
        f"{inner}commit-model: haiku    # haiku, sonnet, or opus\n"
    )

    stripped = raw.rstrip()

    if stripped.endswith("tasks: []"):
        raw = stripped[: -len("tasks: []")] + "tasks:\n" + new_entry
    else:
        raw = stripped + "\n\n" + new_entry

    config.TASKS_FILE.write_text(raw + "\n")
    return f"Added task 'Task {task_num}' with dir={path}"


def handle(args):
    from blink.config import Config
    from blink.tui.actions import detect_editors, open_in_editor

    path = getattr(args, "path", None)
    if path:
        msg = _add_task(path)
        if msg:
            print(f"{config.GREEN}{msg}{config.RESET}")

    config.TLOOP_HOME.mkdir(exist_ok=True)
    if not config.TASKS_FILE.exists():
        config.TASKS_FILE.write_text(config.SAMPLE_TASKS_YAML)

    cli_editor = getattr(args, "editor", None)
    if cli_editor:
        subprocess.run([cli_editor, str(config.TASKS_FILE)])
        return

    cfg = Config()
    editors = detect_editors()

    if not cfg.preferred_ide:
        _prompt_ide_choice()

    if cfg.preferred_ide:
        open_in_editor(str(config.TASKS_FILE), cfg.preferred_ide, editors)
    else:
        print("No IDE selected.")
