from __future__ import annotations

import argparse
import os
import sys

import click
from importlib.metadata import version as _pkg_version

from blink.config import Config, get_default_model
from blink.scanner import Scanner, validate_git
from blink.store import Store
from blink.tui.app import BlinkApp


@click.group(invoke_without_command=True)
@click.option("-R", "--rescan", is_flag=True, default=False, help="Force a full rescan before launching TUI.")
@click.version_option(_pkg_version("blink-repo"), "-v", "--version", prog_name="blink", message="%(prog)s %(version)s")
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
@click.option("-s", "--status", is_flag=True, help="Show task status")
@click.option("-e", "--reset", is_flag=True, help="Reset all tasks to pending")
@click.option("-o", "--only", type=int, default=None, help="Run only task #N (1-based)")
@click.option("-c", "--continue", "continue_on_fail", is_flag=True, help="Continue even if a task fails")
@click.option("-r", "--task-review", "task_review", is_flag=True, help="Run TaskReview after each task")
def run(status: bool, reset: bool, only: int | None, continue_on_fail: bool, task_review: bool) -> None:
    """Run tasks defined in ~/.blink/loop/tasks.yaml."""
    from blink.loop.cmd_run import handle
    args = argparse.Namespace(
        status=status,
        reset=reset,
        only=only,
        continue_on_fail=continue_on_fail,
        task_review=task_review,
    )
    handle(args)


@main.command()
@click.option("--add", "add_path", metavar="PATH", default=None,
              help="Add a task entry for PATH to tasks.yaml, then open editor")
def edit(add_path: str | None) -> None:
    """Open ~/.blink/loop/tasks.yaml in editor, optionally add a task."""
    from blink.loop.cmd_edit import handle
    args = argparse.Namespace(
        add_path=add_path,
    )
    handle(args)


@main.command()
@click.option("-p", "--path", "repo_path", default=".", help="Path to the git repository (default: current directory)")
@click.option("-m", "--model", type=click.Choice(["haiku", "sonnet", "opus"]), default=None, help="Claude model to use for auto-commit (default: from config)")
def commit(repo_path: str, model: str) -> None:
    """Auto-commit changes in the working tree."""
    from blink.loop.cmd_commit import handle
    args = argparse.Namespace(
        path=repo_path,
        model=model or get_default_model("commit"),
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


@main.command()
@click.argument("branch", required=False, default=None)
@click.option("-a", "--against", default=None, help="Base branch to compare against (default: auto-detect main)")
@click.option("-d", "--diff-only", is_flag=True, help="Skip temporary branch creation (faster, less context)")
@click.option("-l", "--list", "list_reports", is_flag=True, help="List existing review reports")
@click.option("-p", "--dir", "project_dir", default=".", help="Project directory (default: current directory)")
@click.option("-m", "--model", type=click.Choice(["haiku", "sonnet", "opus"]), default=None, help="Claude model to use (default: from config)")
@click.option("-i", "--init-rules", is_flag=True, help="Create review-rules.md template in project")
def review(branch: str | None, against: str | None, diff_only: bool, list_reports: bool, project_dir: str, model: str, init_rules: bool) -> None:
    """AI-assisted code review of a colleague branch."""
    from blink.loop.cmd_review import handle
    args = argparse.Namespace(
        branch=branch,
        against=against,
        diff_only=diff_only,
        list=list_reports,
        dir=project_dir,
        model=model or get_default_model("review"),
        init_rules=init_rules,
    )
    handle(args)
