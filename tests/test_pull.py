from __future__ import annotations

import subprocess
from pathlib import Path

from blink.models import Remote, Repo, RepoStatus
from blink.scanner import check_pull_prereqs, parse_pull_output


# ── parse_pull_output ──────────────────────────────────────────────────────


def test_parse_pull_already_up_to_date():
    ok, msg = parse_pull_output("Already up to date.\n", 0, "")
    assert ok is True
    assert "Already up to date" in msg


def test_parse_pull_fast_forward():
    stdout = (
        "Updating abc1234..def5678\n"
        "Fast-forward\n"
        " src/app.py | 3 ++-\n"
        " 2 files changed, 5 insertions(+), 2 deletions(-)\n"
    )
    ok, msg = parse_pull_output(stdout, 0, "")
    assert ok is True
    assert "Pull complete" in msg
    assert "2 files changed" in msg


def test_parse_pull_fast_forward_no_summary():
    stdout = "Updating abc1234..def5678\nFast-forward\n"
    ok, msg = parse_pull_output(stdout, 0, "")
    assert ok is True
    assert "Pull complete" in msg


def test_parse_pull_generic_success():
    ok, msg = parse_pull_output("Some other output\n", 0, "")
    assert ok is True
    assert "Pull complete" in msg


def test_parse_pull_empty_output_success():
    ok, msg = parse_pull_output("", 0, "")
    assert ok is True
    assert "Pull complete" in msg


def test_parse_pull_merge_conflict():
    stderr = "CONFLICT (content): Merge conflict in src/app.py\nAutomatic merge failed.\n"
    ok, msg = parse_pull_output("", 1, stderr)
    assert ok is False
    assert "CONFLICT" in msg


def test_parse_pull_network_error():
    stderr = "fatal: could not read from remote repository\n"
    ok, msg = parse_pull_output("", 1, stderr)
    assert ok is False
    assert "could not read" in msg


def test_parse_pull_failure_no_stderr():
    ok, msg = parse_pull_output("", 1, "")
    assert ok is False
    assert "Pull failed" in msg


# ── check_pull_prereqs ────────────────────────────────────────────────────


def test_check_pull_no_remotes():
    repo = Repo(name="x", path="/tmp/x", remotes=[])
    ok, msg = check_pull_prereqs(repo)
    assert ok is False
    assert msg == "No remote configured"


def test_check_pull_detached_head():
    repo = Repo(
        name="x", path="/tmp/x",
        remotes=[Remote(name="origin", url="git@github.com:user/x.git")],
        status=RepoStatus(branch="HEAD"),
    )
    ok, msg = check_pull_prereqs(repo)
    assert ok is False
    assert msg == "Detached HEAD"


def test_check_pull_status_none():
    repo = Repo(
        name="x", path="/tmp/x",
        remotes=[Remote(name="origin", url="git@github.com:user/x.git")],
        status=None,
    )
    ok, msg = check_pull_prereqs(repo)
    assert ok is True
    assert msg == ""


def test_check_pull_normal_branch():
    repo = Repo(
        name="x", path="/tmp/x",
        remotes=[Remote(name="origin", url="git@github.com:user/x.git")],
        status=RepoStatus(branch="main"),
    )
    ok, msg = check_pull_prereqs(repo)
    assert ok is True
    assert msg == ""


# ── integration: real git pull ────────────────────────────────────────────


def _init_git_repo(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True, check=True)


def test_real_git_pull_already_up_to_date(tmp_path: Path):
    bare = str(tmp_path / "bare.git")
    subprocess.run(["git", "init", "--bare", bare], capture_output=True, check=True)

    # Seed bare repo with an initial commit
    seed = str(tmp_path / "seed")
    subprocess.run(["git", "clone", bare, seed], capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=seed, capture_output=True, check=True)
    (Path(seed) / "file.txt").write_text("initial")
    subprocess.run(["git", "add", "."], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "push"], cwd=seed, capture_output=True, check=True)

    # Clone and pull — should be already up to date
    clone = str(tmp_path / "clone")
    subprocess.run(["git", "clone", bare, clone], capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=clone, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=clone, capture_output=True, check=True)

    result = subprocess.run(
        ["git", "pull"],
        cwd=clone, capture_output=True, text=True, timeout=10,
    )
    ok, msg = parse_pull_output(result.stdout, result.returncode, result.stderr)
    assert ok is True
    assert "Already up to date" in msg


def test_real_git_pull_fast_forward(tmp_path: Path):
    bare = str(tmp_path / "bare.git")
    subprocess.run(["git", "init", "--bare", bare], capture_output=True, check=True)

    # Seed the bare repo with an initial commit
    seed = str(tmp_path / "seed")
    subprocess.run(["git", "clone", bare, seed], capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=seed, capture_output=True, check=True)
    (Path(seed) / "file.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "push"], cwd=seed, capture_output=True, check=True)

    # Clone and make sure it has the initial commit
    clone = str(tmp_path / "clone")
    subprocess.run(["git", "clone", bare, clone], capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=clone, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=clone, capture_output=True, check=True)

    # Add another commit to bare via seed
    (Path(seed) / "file2.txt").write_text("world")
    subprocess.run(["git", "add", "."], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "second"], cwd=seed, capture_output=True, check=True)
    subprocess.run(["git", "push"], cwd=seed, capture_output=True, check=True)

    # Pull from clone
    result = subprocess.run(
        ["git", "pull"],
        cwd=clone, capture_output=True, text=True, timeout=10,
    )
    ok, msg = parse_pull_output(result.stdout, result.returncode, result.stderr)
    assert ok is True
    assert "Pull complete" in msg
