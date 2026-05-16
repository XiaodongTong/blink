from __future__ import annotations

import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

from blink.models import Remote, Repo

GIT_INTERNAL_DIRS = frozenset({
    "objects", "refs", "logs", "hooks", "info", "modules",
    "branches", "worktrees", "sequencer",
})


@dataclass
class ScanResult:
    repo: Repo
    remotes: List[Remote]


def validate_git() -> None:
    if shutil.which("git") is None:
        print("Error: 'git' not found on PATH. Please install git first.", file=sys.stderr)
        sys.exit(1)


def scan_paths(
    roots: List[str],
    excludes: List[str],
    progress: Optional[Callable[[int], None]] = None,
) -> List[str]:
    found: List[str] = []
    exclude_set = set(excludes)
    for root in roots:
        _walk(root, exclude_set, found, progress)
    return found


def _walk(
    root: str,
    exclude_set: Set[str],
    found: List[str],
    progress: Optional[Callable[[int], None]],
) -> None:
    try:
        entries = list(os.scandir(root))
    except (PermissionError, OSError):
        return
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        name = entry.name
        if name == ".git":
            found.append(root)
            if progress:
                progress(len(found))
            return
        if name in exclude_set or name.startswith("."):
            continue
        _walk(entry.path, exclude_set, found, progress)


def fetch_remotes(repo_path: str) -> List[Remote]:
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    remotes: List[Remote] = []
    seen: set[tuple[str, str]] = set()
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        remote_name = parts[0]
        url = parts[1].split()[0]
        key = (remote_name, url)
        if key not in seen:
            seen.add(key)
            remotes.append(Remote(name=remote_name, url=url))
    return remotes


def fetch_description(repo_path: str) -> str:
    desc_path = Path(repo_path) / ".git" / "description"
    try:
        text = desc_path.read_text().strip()
        if text and text != "Unnamed repository; edit this file 'description' to name the repository.":
            return text
    except (OSError, PermissionError):
        pass
    return ""


def _process_repo(repo_path: str) -> ScanResult:
    remotes = fetch_remotes(repo_path)
    description = fetch_description(repo_path)
    name = os.path.basename(repo_path)
    repo = Repo(
        name=name,
        path=repo_path,
        description=description,
        last_synced=Repo.now_iso(),
    )
    return ScanResult(repo=repo, remotes=remotes)


class Scanner:
    def __init__(
        self,
        roots: List[str],
        excludes: List[str],
        max_workers: Optional[int] = None,
    ) -> None:
        validate_git()
        self._roots = roots
        self._excludes = excludes
        cpu = os.cpu_count() or 4
        self._max_workers = max_workers or min(cpu * 2, 16)

    def run_scan(
        self,
        blocking: bool = True,
        on_result: Optional[Callable[[ScanResult], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> List[ScanResult]:
        if blocking:
            return self._blocking_scan(on_result, on_progress)
        import threading
        results: List[ScanResult] = []
        t = threading.Thread(
            target=self._blocking_scan,
            args=(on_result, on_progress),
            kwargs={"_results_list": results},
            daemon=True,
        )
        t.start()
        return results

    def _blocking_scan(
        self,
        on_result: Optional[Callable[[ScanResult], None]] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        _results_list: Optional[List[ScanResult]] = None,
    ) -> List[ScanResult]:
        paths = scan_paths(self._roots, self._excludes, on_progress)
        results: List[ScanResult] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {executor.submit(_process_repo, p): p for p in paths}
            for future in as_completed(futures):
                try:
                    sr = future.result()
                    results.append(sr)
                    if on_result:
                        on_result(sr)
                except Exception:
                    continue
        if _results_list is not None:
            _results_list.extend(results)
        return results
