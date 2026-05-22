from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


def display_width(text: str) -> int:
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ('F', 'W') else 1
    return w


@dataclass
class Remote:
    id: Optional[int] = None
    repo_id: Optional[int] = None
    name: str = ""
    url: str = ""


@dataclass
class RepoStatus:
    branch: str = ""
    dirty_count: int = 0
    ahead: int = 0
    behind: int = 0
    fetched_at: str = ""


@dataclass
class Repo:
    id: Optional[int] = None
    name: str = ""
    alias: str = ""
    description: str = ""
    path: str = ""
    last_synced: str = ""
    created_at: str = ""
    pinned: int = 0
    view_count: int = 0
    remotes: List[Remote] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    status: Optional[RepoStatus] = None

    @property
    def display_name(self) -> str:
        return self.alias if self.alias else self.name

    def primary_remote_url(self) -> str:
        if self.remotes:
            return self.remotes[0].url
        return ""

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat()
