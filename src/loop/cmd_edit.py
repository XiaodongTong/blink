"""blink edit — open ~/.blink/loop/tasks.yaml in editor, optionally add a task via --add PATH."""

import argparse
import re

import yaml

from blink.loop import config

EDIT_HELP = """\
Open ~/.blink/loop/tasks.yaml in your editor.

Uses the same IDE selection as the TUI (VSCode, Cursor, Antigravity, IntelliJ, PyCharm, etc).
The choice is saved to ~/.blink/config.json as editor.

Task file format (~/.blink/loop/tasks.yaml):

  tasks:
    - name: My task
      dir: ~/projects/my-project
      prompt: |
        Describe what Claude should do.
      # OR:
      prompt_file: ./prompts/my-task.md
      branch: true           # true=auto, "custom/name", false=skip
      task_review: false     # true=post-task self-review for code quality
      use: cybervisor        # cybervisor (default) or claude
      max_rounds: 5          # only for use: claude
      commit-model: haiku    # haiku, sonnet, or opus

  Each task runs in the specified directory. Completed tasks are
  archived to ~/.blink/loop/archive/ after each run cycle.

  Project-level AI instructions can be placed in ./docs/blink/constitution.md
  within the project directory. If present, blink will auto-load them as
  constitutional rules when running tasks with the claude runner.

  Use --task-review (or -r) flag to enable post-task code review for all tasks,
  or set task_review: true on individual tasks.
"""


def _prompt_ide_choice():
    from blink.config import Config
    from blink.tui.actions import detect_editors, IDE_CHOICES

    cfg = Config()
    editors = detect_editors()
    available = [(key, name) for key, name in IDE_CHOICES
                 if key in editors and editors[key].available]
    if not available:
        print("No IDE found. Install VSCode, Cursor, IntelliJ, PyCharm, or another supported IDE.")
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
                cfg.set("editor", key)
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
    p.add_argument("--add", dest="add_path", metavar="PATH",
                   help="Add a task entry for PATH to tasks.yaml, then open editor")
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
        f"{inner}task_review: false     # true=post-task self-review for code quality\n"
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

    add_path = getattr(args, "add_path", None)
    if add_path:
        msg = _add_task(add_path)
        if msg:
            print(f"{config.GREEN}{msg}{config.RESET}")

    config.TLOOP_HOME.mkdir(exist_ok=True)
    if not config.TASKS_FILE.exists():
        config.TASKS_FILE.write_text(config.SAMPLE_TASKS_YAML)

    cfg = Config()
    editors = detect_editors()

    if cfg.editor:
        info = editors.get(cfg.editor)
        if not info or not info.available:
            cfg.set("editor", None)

    if not cfg.editor:
        _prompt_ide_choice()

    if cfg.editor:
        open_in_editor(str(config.TASKS_FILE), cfg.editor, editors)
    else:
        print("No IDE selected.")
