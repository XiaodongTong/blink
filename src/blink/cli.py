from __future__ import annotations

import argparse
import os
import sys

import click

from blink.config import Config
from blink.scanner import Scanner, validate_git
from blink.store import Store
from blink.tui.app import BlinkApp


@click.group(invoke_without_command=True)
@click.option("--rescan", is_flag=True, default=False, help="Force a full rescan before launching TUI.")
@click.pass_context
def main(ctx: click.Context, rescan: bool) -> None:
    if ctx.invoked_subcommand is not None:
        return
    validate_git()
    config = Config()
    store = Store(config.db_path())
    store.init_db()

    is_first_run = store.repo_count() == 0

    if is_first_run or rescan:
        scanner = Scanner(roots=config.scan_paths, excludes=config.exclude_dirs)
        if is_first_run:
            print("First run — scanning for git repositories...")
        elif rescan:
            print("Rescanning...")

        def on_progress(count: int) -> None:
            print(f"\r  Found {count} repos...", end="", flush=True)

        app = BlinkApp(store=store, scanner=scanner, config=config, is_first_run=is_first_run)
        app.run_scan_blocking(on_progress=on_progress)
        print(f"\r  Found {store.repo_count()} repos.      ")
    else:
        existing = store.get_all_repos()
        existing_paths = {r.path for r in existing}
        valid_paths: set[str] = set()
        for p in existing_paths:
            if os.path.isdir(p):
                valid_paths.add(p)
        if len(valid_paths) < len(existing_paths):
            store.delete_stale_repos(valid_paths)

        scanner = Scanner(roots=config.scan_paths, excludes=config.exclude_dirs)
        app = BlinkApp(store=store, scanner=scanner, config=config, is_first_run=False)

    app.run()
    store.close()


@main.command()
@click.option("--status", "-s", is_flag=True, help="Show task status")
@click.option("--reset", is_flag=True, help="Reset all tasks to pending")
@click.option("--only", type=int, default=None, help="Run only task #N (1-based)")
@click.option("--continue", "-c", "continue_on_fail", is_flag=True, help="Continue even if a task fails")
@click.option("--review", "-r", is_flag=True, help="Run post-task code review after each task")
def run(status: bool, reset: bool, only: int | None, continue_on_fail: bool, review: bool) -> None:
    """Run tasks defined in ~/.blink/loop/tasks.yaml."""
    from blink.loop.cmd_run import handle
    args = argparse.Namespace(
        status=status,
        reset=reset,
        only=only,
        continue_on_fail=continue_on_fail,
        review=review,
    )
    handle(args)


@main.command()
@click.argument("path", required=False, default=None)
@click.option("--editor", default=None, help="Override editor command for this session")
def edit(path: str | None, editor: str | None) -> None:
    """Open ~/.blink/loop/tasks.yaml in editor, optionally add a task."""
    from blink.loop.cmd_edit import handle
    args = argparse.Namespace(
        path=path,
        editor=editor,
    )
    handle(args)


@main.command()
@click.option("-p", "--path", "repo_path", default=".", help="Path to the git repository (default: current directory)")
@click.option("-m", "--model", type=click.Choice(["haiku", "sonnet", "opus"]), default="haiku", help="Claude model to use for auto-commit (default: haiku)")
def commit(repo_path: str, model: str) -> None:
    """Auto-commit changes in the working tree."""
    from blink.loop.cmd_commit import handle
    args = argparse.Namespace(
        path=repo_path,
        model=model,
    )
    handle(args)


@main.command()
@click.argument("task_number", required=False, type=int, default=None)
def log(task_number: int | None) -> None:
    """View task logs."""
    from blink.loop.cmd_log import handle
    args = argparse.Namespace(
        task_number=task_number,
    )
    handle(args)


@main.command("config-task")
@click.option("--add", "add_path", required=False, default=None, metavar="PATH",
              help="Add a task entry to tasks.yaml for the given repo path")
def config_task(add_path: str | None) -> None:
    """Configure blink loop tasks."""
    if add_path:
        from blink.loop.cmd_edit import _add_task
        _add_task(add_path)
