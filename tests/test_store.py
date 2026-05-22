from __future__ import annotations

import sqlite3

from blink.models import Remote, Repo, RepoStatus
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
    assert "tags" in names
    assert "repo_tags" in names
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
    assert row["version"] == 3
    store.close()


def test_set_alias() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.set_alias(rid, "my-alias")
    repo = store.get_repo_by_path("/x")
    assert repo is not None
    assert repo.alias == "my-alias"
    store.close()


def test_set_description() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.set_description(rid, "my description")
    repo = store.get_repo_by_path("/x")
    assert repo is not None
    assert repo.description == "my description"
    store.close()


def test_set_description_null_old_db() -> None:
    # The description column has a NOT NULL DEFAULT '' constraint,
    # so we test that set_description works on repos created with empty string.
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x", description=""))
    store.set_description(rid, "new desc")
    repo = store.get_repo_by_path("/x")
    assert repo is not None
    assert repo.description == "new desc"
    store.close()


def test_upsert_preserves_alias_on_rescan() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="x", path="/x"))
    store.set_alias(store.get_repo_by_path("/x").id, "my-alias")
    # Simulate rescan: scanner creates a new Repo with empty alias
    store.upsert_repo(Repo(name="x", path="/x", last_synced="2025-06-01T00:00:00"))
    repo = store.get_repo_by_path("/x")
    assert repo is not None
    assert repo.alias == "my-alias"
    store.close()


def test_add_and_get_tags() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.add_tag(rid, "python")
    store.add_tag(rid, "api")
    tags = store.get_tags_for_repo(rid)
    assert set(tags) == {"python", "api"}
    store.close()


def test_add_duplicate_tag_idempotent() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.add_tag(rid, "python")
    store.add_tag(rid, "python")
    tags = store.get_tags_for_repo(rid)
    assert tags == ["python"]
    store.close()


def test_remove_tag() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.add_tag(rid, "python")
    store.add_tag(rid, "api")
    store.remove_tag(rid, "python")
    tags = store.get_tags_for_repo(rid)
    assert tags == ["api"]
    store.close()


def test_get_all_tags() -> None:
    store = _make_store()
    r1 = store.upsert_repo(Repo(name="a", path="/a"))
    r2 = store.upsert_repo(Repo(name="b", path="/b"))
    store.add_tag(r1, "zebra")
    store.add_tag(r1, "alpha")
    store.add_tag(r2, "beta")
    tags = store.get_all_tags()
    assert tags == ["alpha", "beta", "zebra"]
    store.close()


def test_search_repos_by_tag() -> None:
    store = _make_store()
    r1 = store.upsert_repo(Repo(name="repo-a", path="/a"))
    r2 = store.upsert_repo(Repo(name="repo-b", path="/b"))
    store.add_tag(r1, "python")
    store.add_tag(r2, "python")
    store.add_tag(r2, "api")
    results = store.search_repos("python")
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"repo-a", "repo-b"}
    store.close()


def test_search_repos_by_tag_partial() -> None:
    store = _make_store()
    r1 = store.upsert_repo(Repo(name="repo-a", path="/a"))
    store.add_tag(r1, "python-api")
    results = store.search_repos("api")
    assert len(results) == 1
    assert results[0].name == "repo-a"
    store.close()


def test_load_repos_populates_tags() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.add_tag(rid, "python")
    store.add_tag(rid, "api")
    repos = store.get_all_repos()
    assert repos[0].tags == ["api", "python"]
    store.close()


# ── pinned & view_count ──────────────────────────────────────────────────


def test_toggle_pin() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    assert store.get_repo_by_path("/x").pinned == 0
    new_val = store.toggle_pin(rid)
    assert new_val == 1
    assert store.get_repo_by_path("/x").pinned == 1
    new_val = store.toggle_pin(rid)
    assert new_val == 0
    assert store.get_repo_by_path("/x").pinned == 0
    store.close()


def test_increment_view_count() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    assert store.get_repo_by_path("/x").view_count == 0
    store.increment_view_count(rid)
    store.increment_view_count(rid)
    assert store.get_repo_by_path("/x").view_count == 2
    store.close()


def test_sort_by_pinned_then_view_count_then_name() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="beta", path="/b"))
    r_alpha = store.upsert_repo(Repo(name="alpha", path="/a"))
    r_gamma = store.upsert_repo(Repo(name="gamma", path="/c"))
    # alpha: pinned, view_count=2
    store.toggle_pin(r_alpha)
    store.increment_view_count(r_alpha)
    store.increment_view_count(r_alpha)
    # gamma: not pinned, view_count=5
    for _ in range(5):
        store.increment_view_count(r_gamma)
    repos = store.get_all_repos()
    assert [r.name for r in repos] == ["alpha", "gamma", "beta"]
    store.close()


def test_search_repos_preserves_sort_order() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="alpha-repo", path="/a"))
    r_beta = store.upsert_repo(Repo(name="beta-repo", path="/b"))
    store.toggle_pin(r_beta)
    repos = store.search_repos("repo")
    assert repos[0].name == "beta-repo"
    assert repos[1].name == "alpha-repo"
    store.close()


def test_upsert_preserves_pinned_and_view_count() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="x", path="/x"))
    rid = store.get_repo_by_path("/x").id
    store.toggle_pin(rid)
    store.increment_view_count(rid)
    # Simulate rescan
    store.upsert_repo(Repo(name="x", path="/x", last_synced="2025-06-01T00:00:00"))
    repo = store.get_repo_by_path("/x")
    assert repo.pinned == 1
    assert repo.view_count == 1
    store.close()


def test_migration_adds_columns() -> None:
    store = Store(":memory:")
    conn = store._connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (1);
        CREATE TABLE IF NOT EXISTS repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            alias TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL UNIQUE,
            last_synced TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.execute("INSERT INTO repos (name, path) VALUES ('old', '/old')")
    conn.commit()
    store.init_db()
    repo = store.get_repo_by_path("/old")
    assert repo is not None
    assert repo.pinned == 0
    assert repo.view_count == 0
    store.close()


# ── repo_status ──────────────────────────────────────────────────────────


def test_upsert_and_get_status() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    status = RepoStatus(branch="main", dirty_count=2, ahead=1, behind=3, fetched_at="2026-01-01T00:00:00")
    store.upsert_status(rid, status)
    got = store.get_status_for_repo(rid)
    assert got is not None
    assert got.branch == "main"
    assert got.dirty_count == 2
    assert got.ahead == 1
    assert got.behind == 3
    assert got.fetched_at == "2026-01-01T00:00:00"
    store.close()


def test_upsert_status_updates_existing() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.upsert_status(rid, RepoStatus(branch="main", dirty_count=1))
    store.upsert_status(rid, RepoStatus(branch="feature", dirty_count=3))
    got = store.get_status_for_repo(rid)
    assert got is not None
    assert got.branch == "feature"
    assert got.dirty_count == 3
    store.close()


def test_get_status_nonexistent_repo() -> None:
    store = _make_store()
    assert store.get_status_for_repo(999) is None
    store.close()


def test_get_all_repos_joins_status() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.upsert_status(rid, RepoStatus(branch="main", dirty_count=0, ahead=2))
    repos = store.get_all_repos()
    assert len(repos) == 1
    assert repos[0].status is not None
    assert repos[0].status.branch == "main"
    assert repos[0].status.ahead == 2
    store.close()


def test_get_all_repos_no_status() -> None:
    store = _make_store()
    store.upsert_repo(Repo(name="x", path="/x"))
    repos = store.get_all_repos()
    assert len(repos) == 1
    assert repos[0].status is None
    store.close()


def test_search_repos_joins_status() -> None:
    store = _make_store()
    rid = store.upsert_repo(Repo(name="alpha", path="/a"))
    store.upsert_status(rid, RepoStatus(branch="dev", dirty_count=5))
    results = store.search_repos("alpha")
    assert len(results) == 1
    assert results[0].status is not None
    assert results[0].status.branch == "dev"
    assert results[0].status.dirty_count == 5
    store.close()


def test_migration_v2_to_v3() -> None:
    store = Store(":memory:")
    conn = store._connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version (version) VALUES (2);
        CREATE TABLE IF NOT EXISTS repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            alias TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL UNIQUE,
            last_synced TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            pinned INTEGER NOT NULL DEFAULT 0,
            view_count INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.execute("INSERT INTO repos (name, path) VALUES ('existing', '/existing')")
    conn.commit()
    store.init_db()
    # repo_status table should now exist
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in tables}
    assert "repo_status" in names
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    assert row["version"] == 3
    store.close()
