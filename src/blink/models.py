from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Remote:
    id: Optional[int] = None
    repo_id: Optional[int] = None
    name: str = ""
    url: str = ""


@dataclass
class Repo:
    id: Optional[int] = None
    name: str = ""
    alias: str = ""
    description: str = ""
    path: str = ""
    last_synced: str = ""
    created_at: str = ""
    remotes: List[Remote] = field(default_factory=list)

    def primary_remote_url(self) -> str:
        if self.remotes:
            return self.remotes[0].url
        return ""

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat()
