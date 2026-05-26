"""Reusable Claude CLI runner with retry and verification."""

import subprocess

from blink import logger
from blink.loop import log_format

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

CYAN = "\033[96m"

DEFAULT_MAX_RETRIES = 3

EXECUTION_SUFFIX = (
    "\n\nIMPORTANT: Execute the steps above immediately. "
    "Do NOT ask for confirmation, do NOT just describe what you would do. "
    "Perform every step now using your available tools."
)


def run_claude(prompt, cwd, max_retries=DEFAULT_MAX_RETRIES, verify_fn=None, log_file=None, verbose=False, model="haiku", quiet=False):
    """Run `claude -p` with --dangerously-skip-permissions and optional retry loop.

    Args:
        prompt: The prompt text to send to Claude.
        cwd: Working directory for the subprocess.
        max_retries: Max attempts before giving up.
        verify_fn: Optional callable(cwd) -> bool that checks if the work was actually done.
        log_file: Optional path to append logs.
        verbose: If True, print the prompt sent to Claude and the raw output received.
        model: Model to use ("haiku", "sonnet", "opus"). Passed to `claude --model`.
        quiet: If True, suppress all print() output (for TUI usage).

    Returns:
        True if Claude succeeded (and passed verification if provided), False otherwise.
    """
    enriched_prompt = prompt + EXECUTION_SUFFIX

    logger.log("claude", f"run_claude: model={model}, attempt=1/{max_retries}, cwd={cwd}")

    if verbose and not quiet:
        print(f"{CYAN}--- claude input ---{RESET}")
        print(prompt)
        print(f"{CYAN}--- end ---{RESET}")

    cmd = ["claude", "--dangerously-skip-permissions", "--model", model, "--print", enriched_prompt]

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            logger.log("claude", f"重试: attempt={attempt}/{max_retries}, model={model}")
            hint = (
                f"This is attempt {attempt}/{max_retries}. "
                "The previous attempt did not complete the task. "
                "You MUST execute the steps now, not describe them."
            )
            attempt_prompt = prompt + "\n\n" + hint + EXECUTION_SUFFIX
            attempt_cmd = ["claude", "--dangerously-skip-permissions", "--print", attempt_prompt]
        else:
            attempt_cmd = cmd

        if not quiet:
            print(f"  Running claude --model {model} (attempt {attempt}/{max_retries})...")
        try:
            result = subprocess.run(
                attempt_cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            if not quiet:
                print(f"{YELLOW}  Claude timed out after 300s (attempt {attempt}/{max_retries}){RESET}")
            if attempt >= max_retries:
                if not quiet:
                    print(f"{RED}  Max retries reached. Giving up.{RESET}")
                return False
            continue

        if log_file:
            with open(log_file, "a") as log:
                if attempt > 1:
                    log_format.write_round(log, attempt, max_retries)
                log_format.write_auto_commit(log, f"model={model} exit={result.returncode}")
                if result.stdout:
                    for line in result.stdout.splitlines():
                        log_format.write_auto_commit(log, line)
                if result.stderr:
                    for line in result.stderr.splitlines():
                        log_format.write_auto_commit(log, line)
                log.flush()

        if result.returncode != 0:
            if not quiet:
                print(f"{YELLOW}  Claude exited with code {result.returncode} (attempt {attempt}/{max_retries}){RESET}")
            logger.log("claude", f"退出码异常: exit={result.returncode}, attempt={attempt}/{max_retries}")
            if attempt < max_retries:
                continue
            return False

        if verbose and not quiet:
            print(f"{CYAN}--- claude output ---{RESET}")
            print(result.stdout if result.stdout else "(no output)")
            if result.stderr:
                print(f"{YELLOW}[stderr]{RESET} {result.stderr}")
            print(f"{CYAN}--- end ---{RESET}")

        if verify_fn is None:
            logger.log("claude", f"完成: exit=0, stdout={len(result.stdout) if result.stdout else 0} chars")
            return True

        if verify_fn(cwd):
            return True

        if not quiet:
            print(f"{YELLOW}  Claude completed but verification failed (attempt {attempt}/{max_retries}){RESET}")
        if attempt >= max_retries:
            if not quiet:
                print(f"{RED}  Max retries reached. Giving up.{RESET}")
            return False

    return False


def run_claude_text(prompt, cwd, max_retries=DEFAULT_MAX_RETRIES, log_file=None, verbose=False, model="sonnet", quiet=False):
    """Run `claude -p` and return stdout text. No EXECUTION_SUFFIX — for analysis tasks.

    Unlike run_claude(), this function:
    - Does NOT append EXECUTION_SUFFIX (TaskReview is analysis, not execution)
    - Returns the stdout string on success, None on failure
    - Has no verify_fn (output IS the result)
    - Defaults to sonnet model (analysis needs deeper reasoning)
    """
    logger.log("claude", f"run_claude_text: model={model}, prompt={len(prompt):,} chars, cwd={cwd}")

    if verbose and not quiet:
        print(f"{CYAN}--- claude input (text mode) ---{RESET}")
        print(prompt)
        print(f"{CYAN}--- end ---{RESET}")

    cmd = ["claude", "--dangerously-skip-permissions", "--model", model, "--print", prompt]

    for attempt in range(1, max_retries + 1):
        if not quiet:
            print(f"  Running claude --model {model} (attempt {attempt}/{max_retries})...")
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            if not quiet:
                print(f"{YELLOW}  Claude timed out after 300s (attempt {attempt}/{max_retries}){RESET}")
            if attempt >= max_retries:
                if not quiet:
                    print(f"{RED}  Max retries reached. Giving up.{RESET}")
                return None
            continue

        if log_file:
            with open(log_file, "a") as log:
                log.write(f"[claude_runner_text] model={model} attempt {attempt}/{max_retries} exit={result.returncode}\n")
                if result.stdout:
                    log.write(result.stdout + "\n")
                if result.stderr:
                    log.write(result.stderr + "\n")
                log.flush()

        if result.returncode != 0:
            if not quiet:
                print(f"{YELLOW}  Claude exited with code {result.returncode} (attempt {attempt}/{max_retries}){RESET}")
            logger.log("claude", f"退出码异常(text): exit={result.returncode}, attempt={attempt}/{max_retries}")
            if attempt < max_retries:
                continue
            return None

        if verbose and not quiet:
            print(f"{CYAN}--- claude output ---{RESET}")
            print(result.stdout if result.stdout else "(no output)")
            if result.stderr:
                print(f"{YELLOW}[stderr]{RESET} {result.stderr}")
            print(f"{CYAN}--- end ---{RESET}")

        if result.stdout and result.stdout.strip():
            logger.log("claude", f"完成(text): exit=0, stdout={len(result.stdout)} chars")
            return result.stdout.strip()

        if not quiet:
            print(f"{YELLOW}  Claude returned empty output (attempt {attempt}/{max_retries}){RESET}")
        if attempt >= max_retries:
            return None

    return None
