"""Static analysis integration for code review — runs real linters and feeds output as context."""

import re
import shutil
import subprocess
from pathlib import Path

LANG_EXTENSIONS = {
    "python": {".py"},
    "node": {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"},
    "go": {".go"},
    "rust": {".rs"},
    "java": {".java"},
}

# Per-language linter commands: list of (name, [cmd...], filter_files_flag)
# First available tool wins.
LINTER_COMMANDS = {
    "python": [
        ("ruff", ["ruff", "check", "--no-fix", "--quiet"], True),
        ("flake8", ["flake8", "--max-line-length=120"], True),
        ("mypy", ["mypy", "--no-error-summary", "--ignore-missing-imports"], True),
    ],
    "node": [
        ("eslint", ["eslint", "--no-fix", "--format=compact"], True),
        ("tsc", ["tsc", "--noEmit", "--pretty", "false"], False),
    ],
    "go": [
        ("go vet", ["go", "vet", "./..."], False),
        ("golangci-lint", ["golangci-lint", "run", "--out-format=line-number"], True),
    ],
    "rust": [
        ("cargo clippy", ["cargo", "clippy", "--quiet", "--message-format=short"], False),
    ],
    "java": [
        ("checkstyle", ["checkstyle", "-c", "/google_checks.xml"], True),
    ],
}


def detect_project_languages(dir_path, diff_files):
    """Detect project languages from diff file extensions."""
    languages = set()
    for f in diff_files:
        ext = Path(f).suffix.lower()
        for lang, exts in LANG_EXTENSIONS.items():
            if ext in exts:
                languages.add(lang)
                break
    return languages


def _extract_diff_files(diff_text):
    """Extract changed file paths from a unified diff."""
    files = []
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+?)$", diff_text, re.MULTILINE):
        files.append(match.group(2))
    return files


def _find_linter(lang):
    """Find the first available linter for a language."""
    commands = LINTER_COMMANDS.get(lang, [])
    for name, cmd, filter_files in commands:
        binary = cmd[0]
        if shutil.which(binary):
            return name, cmd, filter_files
    return None, None, None


def _filter_output_by_files(output, diff_files):
    """Filter linter output to only include lines referencing diff files."""
    if not output or not diff_files:
        return output
    normalized = set()
    for f in diff_files:
        normalized.add(f)
        normalized.add(f"./{f}")
        normalized.add(str(Path(f)))
    lines = output.splitlines()
    filtered = []
    for line in lines:
        for f in normalized:
            if f in line:
                filtered.append(line)
                break
    return "\n".join(filtered) if filtered else ""


def run_static_analysis(dir_path, diff_text, timeout=60):
    """Run static analysis tools on the project, filtered to diff files.

    Returns a string with lint results, or a message indicating no results.
    """
    diff_files = _extract_diff_files(diff_text)
    if not diff_files:
        return "(no files changed)"

    languages = detect_project_languages(dir_path, diff_files)
    if not languages:
        return "(no supported languages detected in changed files)"

    results = []

    for lang in sorted(languages):
        name, cmd, filter_files = _find_linter(lang)
        if not name or not cmd:
            available = ", ".join(c[0] for c in LINTER_COMMANDS.get(lang, []))
            results.append(f"[{lang}] (no linter available — install: {available})")
            continue

        try:
            proc = subprocess.run(
                cmd,
                cwd=dir_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            output = output.strip()

            if not output:
                results.append(f"[{lang}/{name}] no issues found")
                continue

            if filter_files:
                output = _filter_output_by_files(output, diff_files)
                if not output:
                    results.append(f"[{lang}/{name}] no issues in changed files")
                    continue

            if len(output) > 8000:
                output = output[:8000] + f"\n... (truncated, {len(output)} chars total)"

            results.append(f"[{lang}/{name}]\n{output}")

        except subprocess.TimeoutExpired:
            results.append(f"[{lang}/{name}] (linter timeout after {timeout}s)")
        except Exception as e:
            results.append(f"[{lang}/{name}] (error: {e})")

    return "\n\n".join(results) if results else "(no lint results)"
