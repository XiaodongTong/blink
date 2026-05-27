"""Test runner for code review — detects and runs project tests on the merged branch."""

import json
import subprocess
from pathlib import Path

# (test_name, detection_method, command)
# detection_method: "file" checks file existence, "pkg_script" checks package.json scripts
TEST_DETECTORS = [
    # Python
    ("pytest", "file", ["pytest", "--tb=short", "-q", "--no-header"], ["pytest.ini", "pyproject.toml", "setup.cfg"]),
    ("python unittest", "file", ["python", "-m", "unittest", "discover", "-s", ".", "-q"], ["tests/", "test/"]),
    # Node
    ("npm test", "pkg_script", ["npm", "test", "--", "--silent"], ["package.json"]),
    ("yarn test", "pkg_script", ["yarn", "test", "--silent"], ["package.json"]),
    # Go
    ("go test", "file", ["go", "test", "./...", "-count=1", "-short"], ["go.mod"]),
    # Rust
    ("cargo test", "file", ["cargo", "test", "--quiet"], ["Cargo.toml"]),
    # Java
    ("mvn test", "file", ["mvn", "test", "-q"], ["pom.xml"]),
    ("gradle test", "file", ["gradle", "test", "-q"], ["build.gradle", "build.gradle.kts"]),
]


def _has_package_json_script(dir_path, script_name="test"):
    """Check if package.json has a test script."""
    pkg_path = Path(dir_path) / "package.json"
    if not pkg_path.exists():
        return False
    try:
        data = json.loads(pkg_path.read_text())
        scripts = data.get("scripts", {})
        return script_name in scripts
    except (json.JSONDecodeError, OSError):
        return False


def detect_test_command(dir_path):
    """Detect the test command for this project.

    Returns (name, cmd) or (None, None) if no test framework found.
    """
    dir_path = Path(dir_path)

    for name, method, cmd, markers in TEST_DETECTORS:
        if method == "file":
            # Check if any marker file/directory exists
            for marker in markers:
                if marker.endswith("/"):
                    if (dir_path / marker.rstrip("/")).is_dir():
                        return name, cmd
                else:
                    if (dir_path / marker).exists():
                        return name, cmd
        elif method == "pkg_script":
            if _has_package_json_script(dir_path):
                return name, cmd

    return None, None


def run_tests(dir_path, timeout=300):
    """Run project tests and return results.

    Returns:
        (test_name, passed, output) — test_name is None if no test framework found.
    """
    name, cmd = detect_test_command(dir_path)
    if not name:
        return None, True, "(no test framework detected)"

    try:
        proc = subprocess.run(
            cmd,
            cwd=dir_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        passed = proc.returncode == 0

        # Truncate to last 2000 chars to avoid bloating the prompt
        if len(output) > 2000:
            output = f"... (first {len(output) - 2000} chars truncated)\n" + output[-2000:]

        return name, passed, output.strip() or "(no test output)"

    except subprocess.TimeoutExpired:
        return name, False, f"(test timeout after {timeout}s)"
    except FileNotFoundError:
        return None, True, f"({name} not installed)"
    except Exception as e:
        return name, False, f"(test error: {e})"
