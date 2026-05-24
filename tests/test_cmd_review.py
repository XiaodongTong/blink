"""Tests for blink.loop.cmd_review — AI-assisted code review pipeline."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blink.loop import git_ops
from blink.loop.cmd_review import (
    REVIEW_PROMPT,
    _branch_slug,
    build_review_prompt,
    cleanup_review_branch,
    collect_context,
    ensure_review_dir,
    handle,
    parse_verdict,
    save_report,
)


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


# ── ensure_review_dir ─────────────────────────────────────────────────────

class TestEnsureReviewDir:
    def test_creates_nested_directory(self, tmp_path):
        review_dir = ensure_review_dir(str(tmp_path))
        assert review_dir.exists()
        assert review_dir == tmp_path / "docs" / "blink" / "code-review"

    def test_idempotent(self, tmp_path):
        ensure_review_dir(str(tmp_path))
        ensure_review_dir(str(tmp_path))
        assert (tmp_path / "docs" / "blink" / "code-review").exists()


# ── collect_context ───────────────────────────────────────────────────────

class TestCollectContext:
    def test_collects_diff_log_stat(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello", "initial")
        _create_branch(repo, "feature/test")
        _checkout(repo, "feature/test")
        _commit_file(repo, "b.txt", "world", "add b")

        ctx = collect_context(repo, "feature/test", "main")
        assert "b.txt" in ctx["diff"]
        assert "add b" in ctx["log"]
        assert "b.txt" in ctx["stat"]

    def test_no_rules_when_file_absent(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")

        ctx = collect_context(repo, "feature/x", "main")
        assert ctx["rules"] == ""

    def test_loads_rules_file(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")

        rules_path = Path(repo) / "docs" / "blink" / "review-rules.md"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text("# Rules\n- Check security")

        ctx = collect_context(repo, "feature/x", "main")
        assert "Check security" in ctx["rules"]

    def test_truncates_large_diff(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "big")
        _checkout(repo, "big")
        # Create a file larger than 100KB
        big_content = "x" * (110 * 1024)
        _commit_file(repo, "big.txt", big_content, "big file")

        ctx = collect_context(repo, "big", "main")
        assert ctx["truncated"] is True
        assert len(ctx["diff"]) <= 100 * 1024


# ── build_review_prompt ───────────────────────────────────────────────────

class TestBuildReviewPrompt:
    def test_includes_rules_block(self):
        ctx = {"diff": "diff content", "log": "abc123 commit", "stat": "1 file", "rules": "No hardcoded secrets", "truncated": False}
        prompt = build_review_prompt(ctx)
        assert "No hardcoded secrets" in prompt
        assert "abc123 commit" in prompt
        assert "1 file" in prompt
        assert "diff content" in prompt

    def test_rules_placeholder_when_empty(self):
        ctx = {"diff": "d", "log": "l", "stat": "s", "rules": "", "truncated": False}
        prompt = build_review_prompt(ctx)
        assert "No project-specific review rules defined" in prompt

    def test_truncation_notice(self):
        ctx = {"diff": "d", "log": "l", "stat": "s", "rules": "", "truncated": True}
        prompt = build_review_prompt(ctx)
        assert "DIFF TRUNCATED" in prompt


# ── parse_verdict ─────────────────────────────────────────────────────────

class TestParseVerdict:
    def test_approve(self):
        v, _ = parse_verdict("VERDICT: APPROVE\n## Summary\nLGTM")
        assert v == "APPROVE"

    def test_approve_with_notes(self):
        v, _ = parse_verdict("VERDICT: APPROVE_WITH_NOTES\n## Summary\nLooks good")
        assert v == "APPROVE_WITH_NOTES"

    def test_request_changes(self):
        v, _ = parse_verdict("VERDICT: REQUEST_CHANGES\n## Summary\nProblems found")
        assert v == "REQUEST_CHANGES"

    def test_uses_last_verdict(self):
        v, _ = parse_verdict("VERDICT: APPROVE\n...\nVERDICT: REQUEST_CHANGES")
        assert v == "REQUEST_CHANGES"

    def test_none_defaults_to_approve_with_notes(self):
        v, out = parse_verdict(None)
        assert v == "APPROVE_WITH_NOTES"

    def test_no_verdict_defaults_to_approve_with_notes(self):
        v, _ = parse_verdict("Just some text without a verdict line")
        assert v == "APPROVE_WITH_NOTES"


# ── save_report ───────────────────────────────────────────────────────────

class TestSaveReport:
    def test_creates_file_with_metadata_header(self, tmp_path):
        path = save_report(str(tmp_path), "feature/auth", "main", "APPROVE", "LGTM")
        report = Path(path)
        assert report.exists()
        content = report.read_text()
        assert "feature/auth" in content
        assert "**Base**: `main`" in content
        assert "**Verdict**: APPROVE" in content
        assert "LGTM" in content

    def test_filename_uses_slug(self, tmp_path):
        path = save_report(str(tmp_path), "feature/auth", "main", "APPROVE", "ok")
        assert "feature-auth-" in Path(path).name

    def test_slug_collapses_dashes(self, tmp_path):
        path = save_report(str(tmp_path), "feature//auth", "main", "APPROVE", "ok")
        filename = Path(path).name
        assert "feature-auth-" in filename
        assert "---" not in filename

    def test_saves_to_correct_directory(self, tmp_path):
        path = save_report(str(tmp_path), "bugfix/x", "main", "APPROVE", "ok")
        assert "docs/blink/code-review" in path


# ── _branch_slug ──────────────────────────────────────────────────────────

class TestBranchSlug:
    def test_slash_to_dash(self):
        assert _branch_slug("feature/auth") == "feature-auth"

    def test_collapse_dashes(self):
        assert _branch_slug("feature///auth") == "feature-auth"

    def test_no_slash(self):
        assert _branch_slug("main") == "main"


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
        with patch("blink.loop.cmd_review.run_claude_text", return_value=mock_output):
            args = MagicMock(
                list=False, init_rules=False, branch="feature/test",
                dir=repo, against=None, diff_only=True, model="sonnet",
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

        with patch("blink.loop.cmd_review.run_claude_text", return_value=None):
            args = MagicMock(
                list=False, init_rules=False, branch="feature/x",
                dir=repo, against=None, diff_only=True, model="sonnet",
            )
            handle(args)

        captured = capsys.readouterr()
        assert "no output" in captured.out or "no output" in captured.err
        review_dir = Path(repo) / "docs" / "blink" / "code-review"
        if review_dir.exists():
            assert len(list(review_dir.glob("*.md"))) == 0


# ── git_ops additions ─────────────────────────────────────────────────────

class TestHandleList:
    def test_list_no_reports(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello")

        args = MagicMock(
            list=True, init_rules=False, branch=None,
            dir=repo, against=None, diff_only=False, model="sonnet",
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
        )
        handle(args)
        assert "already exists" in capsys.readouterr().out


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
        # Get HEAD hash and checkout detached
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

        review_name, saved_ref, stashed = git_ops.create_review_branch(repo, "feature/x", "main")
        assert review_name is not None
        assert review_name.startswith("review/")
        assert "feature-x" in review_name

        # Cleanup
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

        review_name, original_branch, stashed = git_ops.create_review_branch(repo, "feature/x", "main")
        assert review_name is not None
        assert review_name.startswith("review/")

        cleanup_review_branch(repo, original_branch, review_name, stashed, base="main")
        assert not git_ops.branch_exists(repo, review_name)
        assert git_ops.get_current_branch(repo) == "main"

    def test_create_review_branch_with_master_base(self, tmp_path):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo, initial_branch="master")
        _commit_file(repo, "a.txt", "hello")
        _create_branch(repo, "feature/x", base="master")
        _checkout(repo, "feature/x")
        _commit_file(repo, "b.txt", "world")
        _checkout(repo, "master")

        review_name, original_branch, stashed = git_ops.create_review_branch(repo, "feature/x", "master")
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

        # Create conflicting changes on feature branch
        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "a.txt", "from-feature", "feature change")

        # Create conflicting changes on main
        _checkout(repo, "main")
        _commit_file(repo, "a.txt", "from-main", "main change")

        review_name, _, stashed = git_ops.create_review_branch(repo, "feature/x", "main")
        assert review_name is None
        assert git_ops.get_current_branch(repo) == "main"

    def test_handle_merge_conflict_falls_back_to_diff_only(self, tmp_path, capsys):
        repo = str(tmp_path / "repo")
        _init_git_repo(repo)
        _commit_file(repo, "a.txt", "hello", "initial")

        _create_branch(repo, "feature/x")
        _checkout(repo, "feature/x")
        _commit_file(repo, "a.txt", "from-feature", "feature change")
        _checkout(repo, "main")
        _commit_file(repo, "a.txt", "from-main", "main change")

        mock_output = "VERDICT: APPROVE\n## Summary\nOK\n## Issues\nNone found.\n"
        with patch("blink.loop.cmd_review.run_claude_text", return_value=mock_output):
            args = MagicMock(
                list=False, init_rules=False, branch="feature/x",
                dir=repo, against=None, diff_only=False, model="sonnet",
            )
            handle(args)

        captured = capsys.readouterr()
        assert "merge conflict" in captured.out.lower()
        reports = list((Path(repo) / "docs" / "blink" / "code-review").glob("*.md"))
        assert len(reports) == 1
