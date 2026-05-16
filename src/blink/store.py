from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from blink.models import Remote, Repo

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    alias TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL UNIQUE,
    last_synced TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS remotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE,
    UNIQUE(repo_id, name)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS repo_tags (
    repo_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (repo_id, tag_id),
    FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
"""


class Store:
    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init_db(self) -> None:
        conn = self._connect()
        conn.executescript(_DDL)
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            conn.commit()

    def upsert_repo(self, repo: Repo) -> int:
        conn = self._connect()
        existing = conn.execute("SELECT id FROM repos WHERE path = ?", (repo.path,)).fetchone()
        if existing:
            repo_id = existing["id"]
            conn.execute(
                "UPDATE repos SET name=?, description=?, last_synced=? WHERE id=?",
                (repo.name, repo.description, repo.last_synced, repo_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO repos (name, alias, description, path, last_synced) VALUES (?, ?, ?, ?, ?)",
                (repo.name, repo.alias, repo.description, repo.path, repo.last_synced),
            )
            repo_id = cur.lastrowid
        conn.commit()
        return repo_id

    def upsert_remote(self, remote: Remote) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO remotes (repo_id, name, url) VALUES (?, ?, ?) "
            "ON CONFLICT(repo_id, name) DO UPDATE SET url=excluded.url",
            (remote.repo_id, remote.name, remote.url),
        )
        conn.commit()

    def get_all_repos(self) -> List[Repo]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, name, alias, description, path, last_synced, created_at FROM repos ORDER BY name"
        ).fetchall()
        repos = []
        for r in rows:
            repo = Repo(
                id=r["id"], name=r["name"], alias=r["alias"],
                description=r["description"], path=r["path"],
                last_synced=r["last_synced"], created_at=r["created_at"],
            )
            repo.remotes = self._get_remotes_for(conn, repo.id)
            repo.tags = self.get_tags_for_repo(repo.id)
            repos.append(repo)
        return repos

    def search_repos(self, query: str) -> List[Repo]:
        if not query.strip():
            return self.get_all_repos()
        conn = self._connect()
        pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT DISTINCT r.id, r.name, r.alias, r.description, r.path, r.last_synced, r.created_at "
            "FROM repos r LEFT JOIN remotes rm ON r.id = rm.repo_id "
            "LEFT JOIN repo_tags rt ON r.id = rt.repo_id "
            "LEFT JOIN tags t ON rt.tag_id = t.id "
            "WHERE r.name LIKE ? OR r.alias LIKE ? OR r.description LIKE ? "
            "OR r.path LIKE ? OR rm.url LIKE ? OR t.name LIKE ? "
            "ORDER BY r.name",
            (pattern, pattern, pattern, pattern, pattern, pattern),
        ).fetchall()
        repos = []
        for r in rows:
            repo = Repo(
                id=r["id"], name=r["name"], alias=r["alias"],
                description=r["description"], path=r["path"],
                last_synced=r["last_synced"], created_at=r["created_at"],
            )
            repo.remotes = self._get_remotes_for(conn, repo.id)
            repo.tags = self.get_tags_for_repo(repo.id)
            repos.append(repo)
        return repos

    def delete_repo(self, path: str) -> bool:
        conn = self._connect()
        cur = conn.execute("DELETE FROM repos WHERE path = ?", (path,))
        conn.commit()
        return cur.rowcount > 0

    def get_repo_by_path(self, path: str) -> Optional[Repo]:
        conn = self._connect()
        r = conn.execute(
            "SELECT id, name, alias, description, path, last_synced, created_at FROM repos WHERE path = ?",
            (path,),
        ).fetchone()
        if r is None:
            return None
        repo = Repo(
            id=r["id"], name=r["name"], alias=r["alias"],
            description=r["description"], path=r["path"],
            last_synced=r["last_synced"], created_at=r["created_at"],
        )
        repo.remotes = self._get_remotes_for(conn, repo.id)
        repo.tags = self.get_tags_for_repo(repo.id)
        return repo

    def repo_count(self) -> int:
        conn = self._connect()
        row = conn.execute("SELECT COUNT(*) as cnt FROM repos").fetchone()
        return row["cnt"]

    def set_alias(self, repo_id: int, alias: str) -> None:
        conn = self._connect()
        conn.execute("UPDATE repos SET alias=? WHERE id=?", (alias, repo_id))
        conn.commit()

    def get_tags_for_repo(self, repo_id: int) -> List[str]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT t.name FROM tags t "
            "JOIN repo_tags rt ON t.id = rt.tag_id "
            "WHERE rt.repo_id = ? ORDER BY t.name",
            (repo_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def add_tag(self, repo_id: int, tag_name: str) -> None:
        conn = self._connect()
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
        tag_id = row["id"]
        conn.execute("INSERT OR IGNORE INTO repo_tags (repo_id, tag_id) VALUES (?, ?)", (repo_id, tag_id))
        conn.commit()

    def remove_tag(self, repo_id: int, tag_name: str) -> None:
        conn = self._connect()
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
        if row:
            conn.execute("DELETE FROM repo_tags WHERE repo_id=? AND tag_id=?", (repo_id, row["id"]))
            conn.commit()

    def get_all_tags(self) -> List[str]:
        conn = self._connect()
        rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def delete_stale_repos(self, paths_to_keep: set[str]) -> int:
        conn = self._connect()
        placeholders = ",".join("?" for _ in paths_to_keep)
        if paths_to_keep:
            cur = conn.execute(
                f"DELETE FROM repos WHERE path NOT IN ({placeholders})",
                list(paths_to_keep),
            )
        else:
            cur = conn.execute("DELETE FROM repos")
        conn.commit()
        return cur.rowcount

    def _get_remotes_for(self, conn: sqlite3.Connection, repo_id: int) -> List[Remote]:
        rows = conn.execute(
            "SELECT id, repo_id, name, url FROM remotes WHERE repo_id = ?", (repo_id,)
        ).fetchall()
        return [Remote(id=r["id"], repo_id=r["repo_id"], name=r["name"], url=r["url"]) for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
