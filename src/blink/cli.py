from __future__ import annotations

import os
import sys

import click

from blink.config import Config
from blink.scanner import Scanner, validate_git
from blink.store import Store
from blink.tui.app import BlinkApp


@click.command()
@click.option("--rescan", is_flag=True, default=False, help="Force a full rescan before launching TUI.")
def main(rescan: bool) -> None:
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
