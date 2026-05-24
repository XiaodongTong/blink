"""Single task execution for blink loop."""

import os
from datetime import datetime
from pathlib import Path

from blink.loop import config
from blink.loop import log_format
from blink.loop.git_ops import ensure_clean_git, create_task_branch
from blink.loop.review import get_head_commit, review_changes
from blink.loop.runner.cybervisor import CybervisorRunner
from blink.loop.runner.claude import ClaudeRunner
from blink.loop.state import save_state


def expand_dir(d):
    return os.path.expandvars(os.path.expanduser(d))


def resolve_prompt_file(prompt_file, dir_path):
    """Resolve prompt_file: ~ expansion, TLOOP_HOME-relative, then dir-relative."""
    pf = Path(prompt_file).expanduser()
    if pf.is_absolute():
        return pf
    candidate = config.TLOOP_HOME / prompt_file
    if candidate.exists():
        return candidate
    candidate = Path(dir_path) / prompt_file
    if candidate.exists():
        return candidate
    return Path(prompt_file)


def _runner_info(task):
    runner_name = task.get("use", "cybervisor")
    if runner_name == "claude":
        max_rounds = task.get("max_rounds", 5)
        return f"ClaudeRunner (max_rounds={max_rounds})", "claude -p --dangerously-skip-permissions --model opus"
    return "CybervisorRunner", "cybervisor run"


def run_task(task, index, state, review_enabled=False):
    name = task.get("name", f"Task {index + 1}")
    dir_path = expand_dir(task.get("dir", "."))
    prompt = task.get("prompt", "")
    prompt_file = task.get("prompt_file")
    branch_config = task.get("branch", True)
    commit_model = task.get("commit-model", "haiku")

    if not os.path.isdir(dir_path):
        print(f"{config.RED}  Directory not found: {dir_path}{config.RESET}")
        state.setdefault("tasks", {})[str(index)] = {
            "status": "failed",
            "error": f"Directory not found: {dir_path}",
            "updated_at": datetime.now().isoformat(),
        }
        save_state(state)
        return False

    resolved_pf = None
    if prompt_file:
        resolved_pf = resolve_prompt_file(prompt_file, dir_path)
        if resolved_pf.exists():
            prompt = resolved_pf.read_text()
        else:
            print(f"{config.RED}  Prompt file not found: {prompt_file}{config.RESET}")
            return False

    if not prompt.strip():
        print(f"{config.RED}  No prompt defined for task: {name}{config.RESET}")
        return False

    print(f"\n{config.BOLD}{'=' * 60}{config.RESET}")
    print(f"{config.BOLD}  Task [{index + 1}]: {name}{config.RESET}")
    print(f"  Directory: {config.CYAN}{dir_path}{config.RESET}")
    print(f"{config.BOLD}{'=' * 60}{config.RESET}\n")

    config.LOGS_DIR.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = config.LOGS_DIR / f"{timestamp}-{safe_name}.log"

    runner_label, command_label = _runner_info(task)

    started_dt = datetime.now()
    started = started_dt.isoformat()

    with open(log_file, "w") as log:
        log_format.write_header(log, name, dir_path, runner_label, command_label)

    if not ensure_clean_git(dir_path, name, log_file, model=commit_model):
        state.setdefault("tasks", {})[str(index)] = {
            "status": "failed",
            "error": "Failed to clean working tree via auto-commit",
            "updated_at": datetime.now().isoformat(),
        }
        save_state(state)
        return False

    branch_name = create_task_branch(dir_path, branch_config)
    if branch_name is None:
        state.setdefault("tasks", {})[str(index)] = {
            "status": "failed",
            "error": "Failed to create task branch",
            "updated_at": datetime.now().isoformat(),
        }
        save_state(state)
        return False
    if branch_name:
        with open(log_file, "a") as log:
            log_format.write_branch(log, branch_name)

    base_commit = get_head_commit(dir_path) if review_enabled else None

    state.setdefault("tasks", {})[str(index)] = {
        "status": "running",
        "started_at": started,
    }
    save_state(state)

    try:
        runner_name = task.get("use", "cybervisor")
        if runner_name == "claude":
            runner = ClaudeRunner()
            max_rounds = task.get("max_rounds", 5)
            returncode = runner.run(prompt, dir_path, log_file=log_file, max_rounds=max_rounds, prompt_file=resolved_pf)
        else:
            runner = CybervisorRunner()
            returncode = runner.run(prompt, dir_path, log_file=log_file, prompt_file=resolved_pf)

        if returncode == 0:
            status = "done"
            state["tasks"][str(index)] = {
                "status": status,
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
            }
            save_state(state)
            print(f"\n{config.GREEN}✅ Task [{index + 1}] done{config.RESET}")

            if base_commit:
                print(f"\n{config.CYAN}[review] Running post-task code review...{config.RESET}")
                review_ok = review_changes(dir_path, base_commit, log_file)
                if review_ok:
                    print(f"{config.GREEN}[review] Complete{config.RESET}")
                else:
                    print(f"{config.YELLOW}[review] Finished with warnings{config.RESET}")
        else:
            status = "failed"
            state["tasks"][str(index)] = {
                "status": status,
                "started_at": started,
                "finished_at": datetime.now().isoformat(),
                "returncode": returncode,
            }
            save_state(state)
            print(
                f"\n{config.RED}❌ Task [{index + 1}] failed (exit code: {returncode}){config.RESET}"
            )
            print(f"   Log: {log_file}")

        with open(log_file, "a") as log:
            log_format.write_footer(log, started_dt, status)

        if returncode != 0:
            return False

    except Exception as e:
        state["tasks"][str(index)] = {
            "status": "failed",
            "started_at": started,
            "error": str(e),
        }
        save_state(state)
        with open(log_file, "a") as log:
            log_format.write_footer(log, started_dt, "failed")
        print(f"\n{config.RED}❌ Task [{index + 1}] error: {e}{config.RESET}")
        return False

    return True
