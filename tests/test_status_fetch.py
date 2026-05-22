from __future__ import annotations

import subprocess
from pathlib import Path

from blink.models import RepoStatus
from blink.scanner import parse_status_v2, fetch_status, StatusFetcher


def _init_git_repo(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True, check=True)


def test_parse_clean():
    output = "# branch.head main\n# branch.ab +0 -0\n"
    status = parse_status_v2(output)
    assert status.branch == "main"
    assert status.dirty_count == 0
    assert status.ahead == 0
    assert status.behind == 0


def test_parse_dirty():
    output = "# branch.head feature\n# branch.ab +0 -0\n1 .M N... 100644 100644 100644 abc def file.py\n? untracked.txt\n"
    status = parse_status_v2(output)
    assert status.branch == "feature"
    assert status.dirty_count == 2


def test_parse_ahead_behind():
    output = "# branch.head main\n# branch.ab +3 -1\n"
    status = parse_status_v2(output)
    assert status.ahead == 3
    assert status.behind == 1


def test_parse_dirty_with_ahead():
    output = "# branch.head fix\n# branch.ab +1 -0\n1 .M N... 100644 100644 100644 abc def a.py\n2 R. N... 100644 100644 100644 abc def b.py\n"
    status = parse_status_v2(output)
    assert status.branch == "fix"
    assert status.dirty_count == 2
    assert status.ahead == 1
    assert status.behind == 0


def test_parse_detached_head():
    output = "# branch.head (detached)\n# branch.ab +0 -0\n"
    status = parse_status_v2(output)
    assert status.branch == "HEAD"


def test_parse_no_remote():
    output = "# branch.head main\n"
    status = parse_status_v2(output)
    assert status.branch == "main"
    assert status.ahead == 0
    assert status.behind == 0


def test_parse_empty_output():
    status = parse_status_v2("")
    assert status.branch == ""
    assert status.dirty_count == 0


def test_parse_unmerged():
    output = "# branch.head main\n# branch.ab +0 -0\nu AA N... 100644 100644 100644 abc def conflict.py\n"
    status = parse_status_v2(output)
    assert status.dirty_count == 1


def test_fetch_status_clean(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    _init_git_repo(repo)
    # Make initial commit so branch is clean
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, capture_output=True, check=True)
    status = fetch_status(repo)
    assert status.branch == "master" or status.branch == "main"
    assert status.dirty_count == 0


def test_fetch_status_dirty(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    _init_git_repo(repo)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, capture_output=True, check=True)
    Path(repo, "newfile.txt").write_text("hello")
    status = fetch_status(repo)
    assert status.dirty_count >= 1


def test_fetch_status_failure_raises() -> None:
    import pytest
    with pytest.raises(Exception):
        fetch_status("/nonexistent/path")


def test_status_fetcher_blocking(tmp_path: Path) -> None:
    repo = str(tmp_path / "repo")
    _init_git_repo(repo)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=repo, capture_output=True, check=True)

    results: list[tuple[int, RepoStatus]] = []
    errors: list[int] = []
    fetcher = StatusFetcher()
    fetcher.run_fetch(
        repos=[(1, repo)],
        blocking=True,
        on_status=lambda rid, s: results.append((rid, s)),
        on_error=lambda rid: errors.append(rid),
    )
    assert len(results) == 1
    assert results[0][0] == 1
    assert results[0][1].branch != ""
    assert results[0][1].fetched_at != ""
    assert len(errors) == 0


def test_status_fetcher_error_handling(tmp_path: Path) -> None:
    results: list[tuple[int, RepoStatus]] = []
    errors: list[int] = []
    fetcher = StatusFetcher()
    fetcher.run_fetch(
        repos=[(99, "/nonexistent/path")],
        blocking=True,
        on_status=lambda rid, s: results.append((rid, s)),
        on_error=lambda rid: errors.append(rid),
    )
    assert len(results) == 0
    assert errors == [99]
