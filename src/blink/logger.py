"""Blink 日志模块 — 按天分割，写入 ~/.blink/logs/。

格式: [HH:MM:SS]-[模块]-日志内容
文件名: blink-YYYY-MM-DD.log
"""

import threading
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".blink" / "logs"


def _ensure_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _log_file_path() -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"blink-{date_str}.log"


_lock = threading.Lock()


def log(module: str, message: str) -> None:
    """写入一条日志。线程安全，按天自动分割。

    Args:
        module: 模块名，如 "review", "commit", "scanner"
        message: 日志内容
    """
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}]-[{module}] {message}\n"
    with _lock:
        _ensure_dir()
        with open(_log_file_path(), "a", encoding="utf-8") as f:
            f.write(line)


def log_lines(module: str, content: str) -> None:
    """写入多行日志，每行都带时间戳和模块前缀。

    适合记录 AI 的输入输出等长文本。
    """
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{ts}]-[{module}] "
    with _lock:
        _ensure_dir()
        with open(_log_file_path(), "a", encoding="utf-8") as f:
            for line in content.splitlines():
                f.write(f"{prefix}{line}\n")
