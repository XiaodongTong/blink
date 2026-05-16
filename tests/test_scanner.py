from __future__ import annotations

import os
import subprocess
from pathlib import Path

from blink.models import Remote, Repo
from blink.scanner import (
    ScanResult,
    Scanner,
    fetch_description,
    fetch_remotes,
    scan_paths,
)


def _init_git_repo(path: str, name: str = "origin", url: str = "") -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    if url:
        subprocess.run(["git", "remote", "add", name, url], cwd=path, capture_output=True, check=True)
    desc_path = Path(path) / ".git" / "description"
    desc_path.write_text("Test repo description\n")


def test_scan_paths_finds_git_repos(tmp_path: Path) -> None:
    repo1 = str(tmp_path / "project-a")
    repo2 = str(tmp_path / "project-b")
    _init_git_repo(repo1)
    _init_git_repo(repo2)
    found = scan_paths([str(tmp_path)], [])
    assert len(found) == 2
    assert repo1 in found
    assert repo2 in found


def test_scan_paths_skips_excludes(tmp_path: Path) -> None:
    repo = str(tmp_path / "node_modules" / "project")
    _init_git_repo(repo)
    found = scan_paths([str(tmp_path)], ["node_modules"])
    assert len(found) == 0


def test_scan_paths_skips_dotdirs(tmp_path: Path) -> None:
    repo = str(tmp_path / ".hidden" / "project")
    _init_git_repo(repo)
    found = scan_paths([str(tmp_path)], [])
    assert len(found) == 0


def test_scan_paths_handles_permission_error(tmp_path: Path) -> None:
    bad = str(tmp_path / "noperm")
    Path(bad).mkdir()
    os.chmod(bad, 0o000)
    try:
        found = scan_paths([str(tmp_path)], [])
        assert isinstance(found, list)
    finally:
        os.chmod(bad, 0o755)


def test_fetch_remotes(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    _init_git_repo(repo, url="git@github.com:user/repo.git")
    remotes = fetch_remotes(repo)
    assert len(remotes) == 1
    assert remotes[0].name == "origin"
    assert "user/repo" in remotes[0].url


def test_fetch_remotes_empty(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    _init_git_repo(repo)
    remotes = fetch_remotes(repo)
    assert len(remotes) == 0


def test_fetch_description(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    _init_git_repo(repo)
    desc = fetch_description(repo)
    assert desc == "Test repo description"


def test_fetch_description_default_unnamed(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    Path(repo).mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    desc = fetch_description(repo)
    assert desc == ""


def test_fetch_description_missing(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    Path(repo).mkdir(parents=True)
    Path(repo, ".git").mkdir()
    desc = fetch_description(repo)
    assert desc == ""


def test_scanner_blocking(tmp_path: Path) -> None:
    _init_git_repo(str(tmp_path / "proj1"))
    _init_git_repo(str(tmp_path / "proj2"), url="git@github.com:org/proj2.git")
    scanner = Scanner(roots=[str(tmp_path)], excludes=[])
    results = scanner.run_scan(blocking=True)
    assert len(results) == 2
    names = {r.repo.name for r in results}
    assert names == {"proj1", "proj2"}
    r2 = next(r for r in results if r.repo.name == "proj2")
    assert len(r2.remotes) == 1


def test_scanner_progress_callback(tmp_path: Path) -> None:
    _init_git_repo(str(tmp_path / "a"))
    _init_git_repo(str(tmp_path / "b"))
    counts: list[int] = []
    scanner = Scanner(roots=[str(tmp_path)], excludes=[])
    scanner.run_scan(blocking=True, on_progress=lambda c: counts.append(c))
    assert len(counts) >= 1
    assert counts[-1] == 2


def test_process_repo_sets_last_synced(tmp_path: Path) -> None:
    _init_git_repo(str(tmp_path / "repo"))
    scanner = Scanner(roots=[str(tmp_path)], excludes=[])
    results = scanner.run_scan(blocking=True)
    assert len(results) == 1
    assert results[0].repo.last_synced != ""
