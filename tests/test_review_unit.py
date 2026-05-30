"""Tests for blink.loop.review.cmd — unit tests for core functions."""
from __future__ import annotations

from pathlib import Path

from blink.loop.review.cmd import run_review
from blink.loop.review.context import build_review_prompt, collect_context
from blink.loop.review.report import (
    ReviewResult,
    _branch_slug,
    ensure_review_dir,
    parse_verdict,
    save_report,
)


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
        import subprocess
        repo = str(tmp_path / "repo")
        Path(repo).mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
        Path(repo, "a.txt").write_text("hello")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "feature/test"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "feature/test"], cwd=repo, capture_output=True, check=True)
        Path(repo, "b.txt").write_text("world")
        subprocess.run(["git", "add", "b.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=repo, capture_output=True, check=True)

        ctx = collect_context(repo, "feature/test", "main")
        assert "b.txt" in ctx["diff"]
        assert "add b" in ctx["log"]
        assert "b.txt" in ctx["stat"]

    def test_no_rules_when_file_absent(self, tmp_path):
        import subprocess
        repo = str(tmp_path / "repo")
        Path(repo).mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
        Path(repo, "a.txt").write_text("hello")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "feature/x"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "feature/x"], cwd=repo, capture_output=True, check=True)
        Path(repo, "b.txt").write_text("world")
        subprocess.run(["git", "add", "b.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=repo, capture_output=True, check=True)

        ctx = collect_context(repo, "feature/x", "main")
        assert ctx["rules"] == ""

    def test_loads_rules_file(self, tmp_path):
        import subprocess
        repo = str(tmp_path / "repo")
        Path(repo).mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
        Path(repo, "a.txt").write_text("hello")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "feature/x"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "feature/x"], cwd=repo, capture_output=True, check=True)
        Path(repo, "b.txt").write_text("world")
        subprocess.run(["git", "add", "b.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=repo, capture_output=True, check=True)

        rules_path = Path(repo) / "docs" / "blink" / "review-rules.md"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text("# Rules\n- Check security")

        ctx = collect_context(repo, "feature/x", "main")
        assert "Check security" in ctx["rules"]

    def test_truncates_large_diff(self, tmp_path):
        import subprocess
        repo = str(tmp_path / "repo")
        Path(repo).mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
        Path(repo, "a.txt").write_text("hello")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "big"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "big"], cwd=repo, capture_output=True, check=True)
        big_content = "x" * (110 * 1024)
        Path(repo, "big.txt").write_text(big_content)
        subprocess.run(["git", "add", "big.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "big file"], cwd=repo, capture_output=True, check=True)

        ctx = collect_context(repo, "big", "main")
        assert ctx["truncated"] is True
        assert len(ctx["diff"]) <= 100 * 1024

    def test_default_context_fields(self, tmp_path):
        import subprocess
        repo = str(tmp_path / "repo")
        Path(repo).mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
        Path(repo, "a.txt").write_text("hello")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "feature/x"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "feature/x"], cwd=repo, capture_output=True, check=True)
        Path(repo, "b.txt").write_text("world")
        subprocess.run(["git", "add", "b.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add b"], cwd=repo, capture_output=True, check=True)

        ctx = collect_context(repo, "feature/x", "main")
        assert ctx["code_context"] == "(no additional context)"
        assert ctx["lint_result"] == "(lint not run)"
        assert ctx["test_result"] == "(tests not run)"


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

    def test_static_instructions_before_variables(self):
        ctx = {"diff": "diff content", "log": "log content", "stat": "stat", "rules": "MY_RULES", "truncated": False}
        prompt = build_review_prompt(ctx)
        static_idx = prompt.index("审查范围")
        rules_idx = prompt.index("MY_RULES")
        assert static_idx < rules_idx, "Static instructions should come before variable content"


# ── parse_verdict ─────────────────────────────────────────────────────────

class TestParseVerdict:
    def test_approve(self):
        v, _ = parse_verdict("VERDICT: APPROVE\n## Summary\nLGTM")
        assert v == "APPROVE"

    def test_approve_with_notes(self):
        v, _ = parse_verdict("VERDICT: APPROVE_WITH_NOTES\n## Summary\nLooks good")
        assert v == "APPROVE_WITH_NOTES"

    def test_request_changes(self):
        v, _ = parse_verdict("VERDICT: DENY\n## Summary\nProblems found")
        assert v == "DENY"

    def test_uses_last_verdict(self):
        v, _ = parse_verdict("VERDICT: APPROVE\n...\nVERDICT: DENY")
        assert v == "DENY"

    def test_none_defaults_to_approve_with_notes(self):
        v, out = parse_verdict(None)
        assert v == "APPROVE_WITH_NOTES"

    def test_no_verdict_defaults_to_approve_with_notes(self):
        v, _ = parse_verdict("Just some text without a verdict line")
        assert v == "APPROVE_WITH_NOTES"

    def test_strict_regex_priority(self):
        v, _ = parse_verdict("VERDICT: APPROVE\n")
        assert v == "APPROVE"

    def test_mid_sentence_verdict(self):
        v, _ = parse_verdict("The VERDICT: APPROVE is clear\n")
        assert v == "APPROVE"


# ── save_report ───────────────────────────────────────────────────────────

class TestSaveReport:
    def test_creates_file_with_metadata_header(self, tmp_path):
        path = save_report(str(tmp_path), "feature/auth", "main", "APPROVE", "LGTM")
        report = Path(path)
        assert report.exists()
        content = report.read_text()
        assert "feature/auth" in content
        assert "**基准**: `main`" in content
        assert "**结论**: ✓ 通过" in content
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

    def test_filename_includes_time(self, tmp_path):
        path = save_report(str(tmp_path), "feature/x", "main", "APPROVE", "ok")
        filename = Path(path).name
        # Format: feature-x-YYYYMMDD-HHMM.md
        import re
        assert re.match(r"feature-x-\d{8}-\d{6}\.md", filename)

    def test_no_overwrite_on_same_day(self, tmp_path):
        path1 = save_report(str(tmp_path), "feature/x", "main", "APPROVE", "first")
        path2 = save_report(str(tmp_path), "feature/x", "main", "DENY", "second")
        assert path1 != path2


# ── _branch_slug ──────────────────────────────────────────────────────────

class TestBranchSlug:
    def test_slash_to_dash(self):
        assert _branch_slug("feature/auth") == "feature-auth"

    def test_collapse_dashes(self):
        assert _branch_slug("feature///auth") == "feature-auth"

    def test_no_slash(self):
        assert _branch_slug("main") == "main"


# ── ReviewResult ──────────────────────────────────────────────────────────

class TestReviewResult:
    def test_success_result(self):
        r = ReviewResult(True, verdict="APPROVE", report_path="/tmp/report.md")
        assert r.success
        assert r.verdict == "APPROVE"

    def test_failure_result(self):
        r = ReviewResult(False, error="something went wrong")
        assert not r.success
        assert r.error == "something went wrong"
