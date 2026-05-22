from __future__ import annotations

import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

from blink.models import Remote, Repo, RepoStatus

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


def parse_status_v2(output: str) -> RepoStatus:
    branch = ""
    ahead = 0
    behind = 0
    dirty_count = 0
    for line in output.splitlines():
        if line.startswith("# branch.head "):
            val = line[len("# branch.head "):]
            if val == "(detached)":
                branch = "HEAD"
            else:
                branch = val
        elif line.startswith("# branch.ab "):
            rest = line[len("# branch.ab "):]
            parts = rest.split()
            for p in parts:
                if p.startswith("+"):
                    ahead = int(p[1:])
                elif p.startswith("-"):
                    behind = int(p[1:])
        elif line and line[0] in ("1", "2", "u", "?"):
            dirty_count += 1
    return RepoStatus(branch=branch, dirty_count=dirty_count, ahead=ahead, behind=behind)


def fetch_status(repo_path: str) -> RepoStatus:
    result = subprocess.run(
        ["git", "--no-optional-locks", "status", "--porcelain=v2", "--branch"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git status failed for {repo_path}: {result.stderr}")
    return parse_status_v2(result.stdout)


@dataclass
class StatusFetchItem:
    repo_id: int
    repo_path: str


class StatusFetcher:
    def __init__(self, max_workers: Optional[int] = None) -> None:
        validate_git()
        cpu = os.cpu_count() or 4
        self._max_workers = max_workers or min(cpu * 2, 16)

    def run_fetch(
        self,
        repos: List[Tuple[int, str]],
        blocking: bool = True,
        on_status: Optional[Callable[[int, RepoStatus], None]] = None,
        on_error: Optional[Callable[[int], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        if blocking:
            self._blocking_fetch(repos, on_status, on_error, on_done)
        else:
            import threading
            t = threading.Thread(
                target=self._blocking_fetch,
                args=(repos, on_status, on_error, on_done),
                daemon=True,
            )
            t.start()

    def _blocking_fetch(
        self,
        repos: List[Tuple[int, str]],
        on_status: Optional[Callable[[int, RepoStatus], None]] = None,
        on_error: Optional[Callable[[int], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {}
            for repo_id, repo_path in repos:
                futures[executor.submit(fetch_status, repo_path)] = repo_id
            for future in as_completed(futures):
                repo_id = futures[future]
                try:
                    status = future.result()
                    status.fetched_at = Repo.now_iso()
                    if on_status:
                        on_status(repo_id, status)
                except Exception:
                    if on_error:
                        on_error(repo_id)
        if on_done:
            on_done()
