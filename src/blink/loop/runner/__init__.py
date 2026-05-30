"""Runner base class for blink loop task execution backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class Runner(ABC):
    @abstractmethod
    def run(self, prompt: str, cwd: str, log_file: str | Path | None = None,
            **kwargs: object) -> int:
        """Run a task. Returns exit code (0=success)."""
        ...
