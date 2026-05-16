from __future__ import annotations

import sqlite3

from blink.models import Remote, Repo
from blink.store import Store


def _make_store() -> Store:
    store = Store(":memory:")
    store.init_db()
    return store


def test_init_db_creates_tables() -> None:
    store = _make_store()
    conn = store._connect()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in tables}
    assert "repos" in names
    assert "remotes" in names
    store.close()


def test_upsert_and_get_repo() -> None:
    store = _make_store()
    repo = Repo(name="my-repo", path="/tmp/my-repo", last_synced="2025-01-01T00:00:00")
    rid = store.upsert_repo(repo)
    assert rid > 0
    repos = store.get_all_repos()
    assert len(repos) == 1
    assert repos[0].name == "my-repo"
    assert repos[0].path == "/tmp/my-repo"
    store.close()


def test_upsert_repo_updates_existing() -> None:
    store = _make_store()
    repo = Repo(name="my-repo", path="/tmp/my-repo", last_synced="2025-01-01")
    rid1 = store.upsert_repo(repo)
    repo.name = "renamed"
    rid2 = store.upsert_repo(repo)
    assert rid1 == rid2
    repos = store.get_all_repos()
    assert len(repos) == 1
    assert repos[0].name == "renamed"
    store.close()


def test_upsert_remote() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="r", path="/tmp/r"))
    store.upsert_remote(Remote(repo_id=rid, name="origin", url="git@github.com:user/r.git"))
    repos = store.get_all_repos()
    assert len(repos[0].remotes) == 1
    assert repos[0].remotes[0].url == "git@github.com:user/r.git"
    store.close()


def test_search_repos_by_name() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="alpha", path="/a"))
    store.upsert_repo(Repo(name="beta", path="/b"))
    store.upsert_repo(Repo(name="alphabet", path="/c"))
    results = store.search_repos("alpha")
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"alpha", "alphabet"}
    store.close()


def test_search_repos_by_remote_url() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="proj", path="/p"))
    store.upsert_remote(Remote(repo_id=rid, name="origin", url="git@github.com:org/proj.git"))
    results = store.search_repos("org/proj")
    assert len(results) == 1
    assert results[0].name == "proj"
    store.close()


def test_search_empty_returns_all() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="a", path="/a"))
    store.upsert_repo(Repo(name="b", path="/b"))
    assert len(store.search_repos("")) == 2
    assert len(store.search_repos("  ")) == 2
    store.close()


def test_delete_repo() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="x", path="/x"))
    assert store.repo_count() == 1
    assert store.delete_repo("/x") is True
    assert store.repo_count() == 0
    assert store.delete_repo("/nonexistent") is False
    store.close()


def test_delete_repo_cascades_remotes() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.upsert_remote(Remote(repo_id=rid, name="origin", url="git@github.com:user/x.git"))
    store.delete_repo("/x")
    assert store.repo_count() == 0
    store.close()


def test_get_repo_by_path() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="x", path="/x"))
    repo = store.get_repo_by_path("/x")
    assert repo is not None
    assert repo.name == "x"
    assert store.get_repo_by_path("/missing") is None
    store.close()


def test_delete_stale_repos() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="a", path="/a"))
    store.upsert_repo(Repo(name="b", path="/b"))
    store.upsert_repo(Repo(name="c", path="/c"))
    deleted = store.delete_stale_repos({"/a", "/c"})
    assert deleted == 1
    repos = store.get_all_repos()
    assert len(repos) == 2
    assert {r.path for r in repos} == {"/a", "/c"}
    store.close()


def test_schema_version_set() -> None:
    store = _make_store()
    conn = store._connect()
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == 1
    store.close()
