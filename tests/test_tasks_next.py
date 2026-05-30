"""Tests for tasks-next.yaml buffering: has_running_tasks, _add_task target_file, migration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

import pytest

from blink.loop import config
from blink.loop.state import load_state, save_state, has_running_tasks, show_status


class TestHasRunningTasks:
    """has_running_tasks() reads state.json and checks for running status."""

    def test_no_state_file_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")
        assert has_running_tasks() is False

    def test_empty_tasks_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")
        save_state({"tasks": {}, "version": 1})
        assert has_running_tasks() is False

    def test_pending_only_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")
        save_state({"tasks": {"0": {"status": "pending"}}, "version": 1})
        assert has_running_tasks() is False

    def test_done_only_returns_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")
        save_state({"tasks": {"0": {"status": "done"}}, "version": 1})
        assert has_running_tasks() is False

    def test_running_returns_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")
        save_state({"tasks": {"0": {"status": "running"}}, "version": 1})
        assert has_running_tasks() is True

    def test_mixed_with_running_returns_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")
        save_state({
            "tasks": {
                "0": {"status": "done"},
                "1": {"status": "running"},
                "2": {"status": "pending"},
            },
            "version": 1,
        })
        assert has_running_tasks() is True


class TestAddTaskTargetFile:
    """_add_task() with target_file param routes writes correctly."""

    def test_default_writes_to_tasks_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "TLOOP_HOME", tmp_path)
        monkeypatch.setattr(config, "TASKS_FILE", tmp_path / "tasks.yaml")
        monkeypatch.setattr(config, "NEXT_TASKS_FILE", tmp_path / "tasks-next.yaml")
        from blink.loop.cmd_edit import _add_task

        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(config.SAMPLE_TASKS_YAML)

        msg = _add_task("/tmp/my-project")
        assert "Task 1" in msg

        data = yaml.safe_load(tasks_file.read_text())
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["dir"] == "/tmp/my-project"
        assert not (tmp_path / "tasks-next.yaml").exists()

    def test_target_file_writes_to_next(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "TLOOP_HOME", tmp_path)
        monkeypatch.setattr(config, "TASKS_FILE", tmp_path / "tasks.yaml")
        monkeypatch.setattr(config, "NEXT_TASKS_FILE", tmp_path / "tasks-next.yaml")
        from blink.loop.cmd_edit import _add_task

        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(config.SAMPLE_TASKS_YAML)
        next_file = tmp_path / "tasks-next.yaml"

        msg = _add_task("/tmp/my-project", target_file=next_file)
        assert "Task 1" in msg

        # tasks.yaml should be unchanged
        data = yaml.safe_load(tasks_file.read_text())
        assert len(data["tasks"]) == 0

        # tasks-next.yaml should have the new task
        data_next = yaml.safe_load(next_file.read_text())
        assert len(data_next["tasks"]) == 1
        assert data_next["tasks"][0]["dir"] == "/tmp/my-project"

    def test_target_file_appends_to_existing_next(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "TLOOP_HOME", tmp_path)
        monkeypatch.setattr(config, "TASKS_FILE", tmp_path / "tasks.yaml")
        monkeypatch.setattr(config, "NEXT_TASKS_FILE", tmp_path / "tasks-next.yaml")
        from blink.loop.cmd_edit import _add_task

        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(config.SAMPLE_TASKS_YAML)
        next_file = tmp_path / "tasks-next.yaml"
        next_file.write_text(config.SAMPLE_TASKS_YAML)

        _add_task("/tmp/proj-a", target_file=next_file)
        _add_task("/tmp/proj-b", target_file=next_file)

        data_next = yaml.safe_load(next_file.read_text())
        assert len(data_next["tasks"]) == 2

    def test_target_file_none_defaults_to_tasks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "TLOOP_HOME", tmp_path)
        monkeypatch.setattr(config, "TASKS_FILE", tmp_path / "tasks.yaml")
        monkeypatch.setattr(config, "NEXT_TASKS_FILE", tmp_path / "tasks-next.yaml")
        from blink.loop.cmd_edit import _add_task

        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(config.SAMPLE_TASKS_YAML)

        _add_task("/tmp/my-project", target_file=None)

        data = yaml.safe_load(tasks_file.read_text())
        assert len(data["tasks"]) == 1
        assert not (tmp_path / "tasks-next.yaml").exists()


class TestNextTasksFileConstant:
    """NEXT_TASKS_FILE must be under TLOOP_HOME."""

    def test_next_tasks_file_path(self):
        assert config.NEXT_TASKS_FILE == config.TLOOP_HOME / "tasks-next.yaml"

    def test_next_tasks_file_is_path(self):
        assert isinstance(config.NEXT_TASKS_FILE, Path)


class TestShowStatusWithQueue:
    """show_status() prints queue info when tasks-next.yaml exists."""

    def test_shows_queue_count(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(config, "NEXT_TASKS_FILE", tmp_path / "tasks-next.yaml")
        next_file = tmp_path / "tasks-next.yaml"
        next_file.write_text("tasks:\n  - name: Queued\n    dir: /tmp/x\n")

        tasks = [{"name": "Current", "dir": "/tmp/y"}]
        state = {"tasks": {"0": {"status": "pending"}}, "version": 1}
        show_status(tasks, state)

        out = capsys.readouterr().out
        assert "1 task(s) queued in tasks-next.yaml" in out

    def test_no_queue_message_when_no_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(config, "NEXT_TASKS_FILE", tmp_path / "tasks-next.yaml")

        tasks = [{"name": "Current", "dir": "/tmp/y"}]
        state = {"tasks": {}, "version": 1}
        show_status(tasks, state)

        out = capsys.readouterr().out
        assert "queued" not in out

    def test_no_queue_message_when_empty(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(config, "NEXT_TASKS_FILE", tmp_path / "tasks-next.yaml")
        next_file = tmp_path / "tasks-next.yaml"
        next_file.write_text("tasks: []\n")

        tasks = [{"name": "Current", "dir": "/tmp/y"}]
        state = {"tasks": {}, "version": 1}
        show_status(tasks, state)

        out = capsys.readouterr().out
        assert "queued" not in out
