from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from blink.config import Config
from blink.models import Remote, Repo
from blink.scanner import Scanner, ScanResult, fetch_description, fetch_remotes
from blink.store import Store
from blink.tui.actions import copy_path, detect_editors, open_in_editor


def _init_git_repo(path: str, name: str = "origin", url: str = "") -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    if url:
        subprocess.run(["git", "remote", "add", name, url], cwd=path, capture_output=True, check=True)
    desc_path = Path(path) / ".git" / "description"
    desc_path.write_text("Test repo description\n")


def test_e2e_scan_store_search(tmp_path: Path) -> None:
    repo1 = str(tmp_path / "alpha")
    repo2 = str(tmp_path / "beta")
    repo3 = str(tmp_path / "gamma")
    _init_git_repo(repo1, url="git@github.com:user/alpha.git")
    _init_git_repo(repo2, url="git@github.com:user/beta.git")
    _init_git_repo(repo3)

    store = Store(":memory:")
    store.init_db()

    scanner = Scanner(roots=[str(tmp_path)], excludes=[])
    results = scanner.run_scan(blocking=True)

    assert len(results) == 3

    for sr in results:
        rid = store.upsert_repo(sr.repo)
        for remote in sr.remotes:
            remote.repo_id = rid
            store.upsert_remote(remote)

    assert store.repo_count() == 3

    repos = store.get_all_repos()
    assert len(repos) == 3

    alpha = store.search_repos("alpha")
    assert len(alpha) == 1
    assert alpha[0].name == "alpha"
    assert len(alpha[0].remotes) == 1
    assert "user/alpha" in alpha[0].remotes[0].url

    beta_by_url = store.search_repos("user/beta")
    assert len(beta_by_url) == 1

    gamma = store.get_repo_by_path(repo3)
    assert gamma is not None
    assert gamma.name == "gamma"
    assert gamma.description == "Test repo description"

    store.delete_repo(repo2)
    assert store.repo_count() == 2

    store.close()


def test_e2e_stale_cleanup(tmp_path: Path) -> None:
    existing = str(tmp_path / "exists")
    removed = str(tmp_path / "removed")
    _init_git_repo(existing)
    _init_git_repo(removed)

    store = Store(":memory:")
    store.init_db()
    store.upsert_repo(Repo(name="exists", path=existing))
    store.upsert_repo(Repo(name="removed", path=removed))

    import shutil
    shutil.rmtree(removed)

    existing_repos = store.get_all_repos()
    valid = {r.path for r in existing_repos if os.path.isdir(r.path)}
    deleted = store.delete_stale_repos(valid)
    assert deleted == 1
    assert store.repo_count() == 1
    store.close()


def test_e2e_description_persisted(tmp_path: Path) -> None:
    repo = str(tmp_path / "myproject")
    _init_git_repo(repo)
    desc_path = Path(repo) / ".git" / "description"
    desc_path.write_text("My special project\n")

    desc = fetch_description(repo)
    assert desc == "My special project"

    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="myproject", path=repo, description=desc))
    stored = store.get_repo_by_path(repo)
    assert stored is not None
    assert stored.description == "My special project"
    store.close()


def test_e2e_copy_path(tmp_path: Path) -> None:
    test_path = str(tmp_path / "my-repo")
    Path(test_path).mkdir()
    assert copy_path(test_path) is True


def test_e2e_open_in_editor(tmp_path: Path) -> None:
    editors = detect_editors()
    repo = str(tmp_path / "test-open")
    Path(repo).mkdir()
    from unittest.mock import patch
    with patch("subprocess.Popen") as mock:
        open_in_editor(repo, "o", editors)
        mock.assert_called_once()


def test_performance_search_500_repos() -> None:
    store = Store(":memory:")
    store.init_db()
    for i in range(500):
        store.upsert_repo(Repo(
            name=f"repo-{i:04d}",
            path=f"/tmp/repos/repo-{i:04d}",
            description=f"Description for repo {i}",
        ))

    start = time.perf_counter()
    for _ in range(100):
        results = store.search_repos("repo-0042")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / 100) * 1000
    assert avg_ms < 50, f"Search too slow: {avg_ms:.1f}ms per query"

    assert len(results) == 1
    assert results[0].name == "repo-0042"
    store.close()


def test_config_creates_blink_dir(tmp_path: Path) -> None:
    cfg_path = tmp_path / "subdir" / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    assert cfg_path.exists()
    assert (tmp_path / "subdir" / ".blink").is_dir()
