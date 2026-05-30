"""Tests for blink.loop.review.cmd — integration tests (handle pipeline, git ops)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blink.loop import git_ops
from blink.loop.review.cmd import cleanup_review_branch, handle, run_review
from blink.loop.review.report import ReviewResult, save_report


def _init_git_repo(path, initial_branch="main"):
    Path(path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", initial_branch], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True, check=True)


def _commit_file(path, filename, content, msg="init"):
    fpath = Path(path) / filename
    fpath.write_text(content)
    subprocess.run(["git", "add", filename], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=path, capture_output=True, check=True)


def _create_branch(path, branch, base="main"):
    subprocess.run(["git", "branch", branch, base], cwd=path, capture_output=True, check=True)


def _checkout(path, branch):
    subprocess.run(["git", "checkout", branch], cwd=path, capture_output=True, check=True)


# ── handle integration (mocked claude) ────────────────────────────────────

class TestHandleIntegration:
    def test_full_pipeline_with_mocked_claude(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello", "initial")
        _create_branch(repo, "feature/test")
        _checkout(repo, "feature/test")
        _commit_file(repo, "b.txt", "world", "add b")
        _checkout(repo, "main")

        mock_output = "VERDICT: APPROVE\n## Summary\nLGTM\n## Issues\nNone found.\n"
        with patch("blink.loop.review.cmd.run_claude_text", return_value=mock_output):
            args = MagicMock(
                list=False, init_rules=False, branch="feature/test",
                dir=repo, against=None, diff_only=True, model="sonnet",
                no_verify=True, no_lint=True, no_test=True, no_context=True,
                strict=False, keep_branch=False,
            )
            handle(args)

        reports = list((Path(repo) / "docs" / "blink" / "code-review").glob("*.md"))
        assert len(reports) == 1
        content = reports[0].read_text()
        assert "VERDICT: APPROVE" in content
        assert "feature/test" in content

    def test_error_on_missing_branch(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")

        args = MagicMock(
            list=False, init_rules=False, branch="nonexistent",
            dir=repo, against=None, diff_only=True, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)
        captured = capsys.readouterr()
        assert "does not exist" in captured.out or "does not exist" in captured.err

    def test_error_on_no_main_branch(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo, initial_branch="develop")
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x", base="develop")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "develop")

        args = MagicMock(
            list=False, init_rules=False, branch="feature/x",
            dir=repo, against=None, diff_only=True, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)
        captured = capsys.readouterr()
        assert "could not detect main branch" in captured.out or "could not detect main branch" in captured.err

    def test_claude_returns_none_no_report(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        with patch("blink.loop.review.cmd.run_claude_text", return_value=None):
            args = MagicMock(
                list=False, init_rules=False, branch="feature/x",
                dir=repo, against=None, diff_only=True, model="sonnet",
                no_verify=True, no_lint=True, no_test=True, no_context=True,
                strict=False, keep_branch=False,
            )
            handle(args)

        captured = capsys.readouterr()
        assert "no output" in captured.out or "no output" in captured.err
        review_dir = Path(repo) / "docs" / "blink" / "code-review"
        if review_dir.exists():
            assert len(list(review_dir.glob("*.md"))) == 0

    def test_empty_diff_returns_error(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/empty")
        _checkout(repo, "main")

        args = MagicMock(
            list=False, init_rules=False, branch="feature/empty",
            dir=repo, against=None, diff_only=True, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)

        captured = capsys.readouterr()
        assert "No changes" in captured.out or "No changes" in captured.err


# ── handle list & init-rules ─────────────────────────────────────────────

class TestHandleList:
    def test_list_no_reports(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")

        args = MagicMock(
            list=True, init_rules=False, branch=None,
            dir=repo, against=None, diff_only=False, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)
        assert "No reviews found" in capsys.readouterr().out

    def test_list_shows_reports(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")

        save_report(repo, "feature/x", "main", "APPROVE", "VERDICT: APPROVE\n## Summary\nOK")

        args = MagicMock(
            list=True, init_rules=False, branch=None,
            dir=repo, against=None, diff_only=False, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)
        out = capsys.readouterr().out
        assert "APPROVE" in out
        assert "feature-x-" in out


class TestHandleInitRules:
    def test_creates_template(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)

        args = MagicMock(
            list=False, init_rules=True, branch=None,
            dir=repo, against=None, diff_only=False, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)

        rules_path = Path(repo) / "docs" / "blink" / "review-rules.md"
        assert rules_path.exists()
        content = rules_path.read_text()
        assert "必查项" in content
        assert "历史教训" in content
        assert "代码风格" in content

    def test_errors_if_exists(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)

        rules_path = Path(repo) / "docs" / "blink" / "review-rules.md"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text("# Existing rules")

        args = MagicMock(
            list=False, init_rules=True, branch=None,
            dir=repo, against=None, diff_only=False, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)
        assert "already exists" in capsys.readouterr().out


# ── git_ops for review ───────────────────────────────────────────────────

class TestGitOpsReview:
    def test_get_current_branch(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        assert git_ops.get_current_branch(repo) == "main"

    def test_get_current_branch_detached(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
        subprocess.run(["git", "checkout", result.stdout.strip()], cwd=repo, capture_output=True, check=True)
        assert git_ops.get_current_branch(repo) is None

    def test_get_diff_stat(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        stat = git_ops.get_diff_stat(repo, "main", "feature/x")
        assert "b.txt" in stat

    def test_detect_main_branch(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo, initial_branch="main")
        _commit_file(repo, "a.txt", "hello")
        assert git_ops.detect_main_branch(repo) == "main"

    def test_detect_master_branch(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo, initial_branch="master")
        _commit_file(repo, "a.txt", "hello")
        assert git_ops.detect_main_branch(repo) == "master"

    def test_detect_no_main_branch(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo, initial_branch="develop")
        _commit_file(repo, "a.txt", "hello")
        assert git_ops.detect_main_branch(repo) is None

    def test_create_review_branch(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        review_name, saved_ref, stashed, error = git_ops.create_review_branch(repo, "feature/x", "main")
        assert review_name is not None
        assert review_name.startswith("review/")
        assert "feature-x" in review_name

        subprocess.run(["git", "checkout", "main"], cwd=repo, capture_output=True)
        subprocess.run(["git", "branch", "-D", review_name], cwd=repo, capture_output=True)

    def test_delete_branch(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "to-delete")
        assert git_ops.branch_exists(repo, "to-delete")
        git_ops.delete_branch(repo, "to-delete")
        assert not git_ops.branch_exists(repo, "to-delete")

    def test_create_review_branch_and_cleanup(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        review_name, original_branch, stashed, error = git_ops.create_review_branch(repo, "feature/x", "main")
        assert review_name is not None
        assert review_name.startswith("review/")

        # Default: cleanup deletes the review branch
        cleanup_review_branch(repo, original_branch, review_name, stashed, base="main")
        assert not git_ops.branch_exists(repo, review_name)
        assert git_ops.get_current_branch(repo) == "main"

    def test_create_review_branch_and_cleanup_keep(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        review_name, original_branch, stashed, error = git_ops.create_review_branch(repo, "feature/x", "main")
        assert review_name is not None

        # keep_branch=True preserves the review branch
        cleanup_review_branch(repo, original_branch, review_name, stashed, base="main", keep_branch=True)
        assert git_ops.branch_exists(repo, review_name)
        assert git_ops.get_current_branch(repo) == "main"

        subprocess.run(["git", "branch", "-D", review_name], cwd=repo, capture_output=True)

    def test_create_review_branch_with_master_base(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo, initial_branch="master")
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x", base="master")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "master")

        review_name, original_branch, stashed, error = git_ops.create_review_branch(repo, "feature/x", "master")
        assert review_name is not None

        cleanup_review_branch(repo, original_branch, review_name, stashed, base="master")
        assert not git_ops.branch_exists(repo, review_name)
        assert git_ops.get_current_branch(repo) == "master"

    def test_get_branch_list(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/a")
        _create_branch(repo, "feature/b")

        branches = git_ops.get_branch_list(repo, "feature/*")
        assert "feature/a" in branches
        assert "feature/b" in branches

    def test_create_review_branch_merge_conflict(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello", "initial")

        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "a.txt", "from-feature", "feature change")

        _checkout(repo, "main")
        _commit_file(repo, "a.txt", "from-main", "main change")

        review_name, _, stashed, error = git_ops.create_review_branch(repo, "feature/x", "main")
        assert review_name is None
        assert error is not None
        assert error[0] == "conflict"
        assert git_ops.get_current_branch(repo) == "main"

    def test_handle_merge_conflict_direct_request_changes(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello", "initial")

        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "a.txt", "from-feature", "feature change")
        _checkout(repo, "main")
        _commit_file(repo, "a.txt", "from-main", "main change")

        args = MagicMock(
            list=False, init_rules=False, branch="feature/x",
            dir=repo, against=None, diff_only=False, model="sonnet",
            no_verify=True, no_lint=True, no_test=True, no_context=True,
            strict=False, keep_branch=False,
        )
        handle(args)

        captured = capsys.readouterr()
        assert "merge conflict" in captured.out.lower()
        assert "DENY" in captured.out
        reports = list((Path(repo) / "docs" / "blink" / "code-review").glob("*.md"))
        assert len(reports) == 1
        content = reports[0].read_text()
        assert "需修改" in content
        assert "合并冲突" in content


# ── run_review core function ─────────────────────────────────────────────

class TestRunReview:
    def test_returns_review_result(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/test")
        _checkout(repo, "feature/test")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        mock_output = "VERDICT: APPROVE\n## Summary\nLGTM\n"
        stages = []
        with patch("blink.loop.review.cmd.run_claude_text", return_value=mock_output):
            result = run_review(
                repo, "feature/test", "main",
                diff_only=True,
                no_verify=True,
                no_lint=True,
                no_test=True,
                no_context=True,
                stage_fn=stages.append,
            )

        assert isinstance(result, ReviewResult)
        assert result.success
        assert result.verdict == "APPROVE"
        assert result.report_path
        assert "collecting" in stages

    def test_empty_diff_returns_failure(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/empty")
        _checkout(repo, "main")

        result = run_review(
            repo, "feature/empty", "main",
            diff_only=True,
            no_verify=True,
        )

        assert not result.success
        assert "No changes" in result.error

    def test_claude_failure_returns_error(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        with patch("blink.loop.review.cmd.run_claude_text", return_value=None):
            result = run_review(
                repo, "feature/x", "main",
                diff_only=True,
                no_verify=True,
            )

        assert not result.success
        assert result.error

    def test_branch_cleanup_after_non_diff_only(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "main")

        mock_output = "VERDICT: APPROVE\n## Summary\nOK\n"
        with patch("blink.loop.review.cmd.run_claude_text", return_value=mock_output):
            result = run_review(
                repo, "feature/x", "main",
                diff_only=False,
                no_verify=True,
                no_lint=True,
                no_test=True,
                no_context=True,
            )

        assert result.success
        # Review branch should be cleaned up
        assert git_ops.get_current_branch(repo) == "main"
