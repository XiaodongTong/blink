"""Tests for blink.loop integration: CLI subcommands, import paths, data directory."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLoopImports:
    """All loop modules must import cleanly."""

    def test_config_imports(self):
        from blink.loop import config
        assert config.TLOOP_HOME == Path.home() / ".blink" / "loop"

    def test_state_imports(self):
        from blink.loop import state
        assert hasattr(state, "load_state")

    def test_task_imports(self):
        from blink.loop import task
        assert hasattr(task, "run_task")

    def test_git_ops_imports(self):
        from blink.loop import git_ops
        assert hasattr(git_ops, "ensure_clean_git")
        assert hasattr(git_ops, "is_git_repo")
        assert hasattr(git_ops, "is_git_clean")

    def test_claude_runner_imports(self):
        from blink.loop import claude_runner
        assert hasattr(claude_runner, "run_claude")

    def test_review_imports(self):
        from blink.loop import review
        assert hasattr(review, "review_changes")

    def test_cmd_handlers_import(self):
        from blink.loop.cmd_run import handle as run_handle
        from blink.loop.cmd_edit import handle as edit_handle
        from blink.loop.cmd_commit import handle as commit_handle
        from blink.loop.cmd_log import handle as log_handle
        from blink.loop.cmd_review import handle as review_handle
        assert callable(run_handle)
        assert callable(edit_handle)
        assert callable(commit_handle)
        assert callable(log_handle)
        assert callable(review_handle)

    def test_runner_base_class(self):
        from blink.loop.runner import Runner
        from blink.loop.runner.claude import ClaudeRunner
        from blink.loop.runner.cybervisor import CybervisorRunner
        assert issubclass(ClaudeRunner, Runner)
        assert issubclass(CybervisorRunner, Runner)

    def test_add_task_function_exists(self):
        from blink.loop.cmd_edit import _add_task
        assert callable(_add_task)


class TestConfigPaths:
    """Config must point to ~/.blink/loop/ not ~/.tloop/."""

    def test_home_is_blink_loop(self):
        from blink.loop.config import TLOOP_HOME
        assert str(TLOOP_HOME).endswith(".blink/loop")
        assert ".tloop" not in str(TLOOP_HOME)

    def test_tasks_file_under_blink_loop(self):
        from blink.loop.config import TASKS_FILE
        assert ".blink" in str(TASKS_FILE)
        assert ".tloop" not in str(TASKS_FILE)

    def test_header_references_blink(self):
        from blink.loop.config import TASKS_YAML_HEADER
        assert "blink edit" in TASKS_YAML_HEADER
        assert "tloop edit" not in TASKS_YAML_HEADER

    def test_sample_yaml_references_blink(self):
        from blink.loop.config import SAMPLE_TASKS_YAML
        assert "blink" in SAMPLE_TASKS_YAML


class TestCLIHelp:
    """CLI smoke tests via --help."""

    def test_main_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "blink", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "commit" in result.stdout
        assert "edit" in result.stdout
        assert "run" in result.stdout
        assert "log" in result.stdout
        assert "review" in result.stdout

    def test_run_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "blink", "run", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--status" in result.stdout
        assert "--only" in result.stdout

    def test_commit_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "blink", "commit", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--path" in result.stdout
        assert "--model" in result.stdout

    def test_edit_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "blink", "edit", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--add" in result.stdout

    def test_log_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "blink", "log", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0


class TestNoStaleTloopRefs:
    """Source code must not contain stale tloop subprocess references."""

    def test_no_which_tloop(self):
        result = subprocess.run(
            ["grep", "-r", 'shutil.which("tloop")', "src/blink/"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0  # grep returns non-zero when no match

    def test_no_popen_tloop(self):
        result = subprocess.run(
            ["grep", "-r", "Popen.*tloop", "src/blink/"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


class TestCommitAction:
    """Test the TUI commit action uses direct function calls."""

    def test_commit_calls_git_ops(self):
        """_run_commit should call git_ops functions, not subprocess tloop."""
        from blink.tui.app import BlinkApp
        import inspect
        source = inspect.getsource(BlinkApp._run_commit)
        assert "shutil.which" not in source
        assert "subprocess.Popen" not in source
        assert "ensure_clean_git" in source or "git_ops" in source

    def test_add_task_calls_internal(self):
        """_run_add_task should call _add_task directly, not subprocess."""
        from blink.tui.app import BlinkApp
        import inspect
        source = inspect.getsource(BlinkApp._run_add_task)
        assert "shutil.which" not in source
        assert "subprocess.Popen" not in source
        assert "_add_task" in source
