"""Structured log formatting for blink task logs."""

from datetime import datetime

DOUBLE = "═" * 60


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _ts_full():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_header(log, task_name, directory, runner_info, command):
    log.write(f"Task:       {task_name}\n")
    log.write(f"Directory:  {directory}\n")
    log.write(f"Runner:     {runner_info}\n")
    log.write(f"Command:    {command}\n")
    log.write(f"Started:    {_ts_full()}\n\n")
    log.flush()


def write_auto_commit(log, text):
    log.write(f"[{_ts()}]-[auto commit] {text}\n")
    log.flush()


def write_branch(log, branch_name):
    log.write(f"[{_ts()}]-[branch] 创建分支: {branch_name}\n\n")
    log.flush()


def write_round(log, round_num, max_rounds):
    if round_num > 1:
        log.write(f"\nRound {round_num}/{max_rounds}\n\n")
        log.flush()


def _write_section(log, phase, tag, content):
    ts = _ts()
    prefix = f"[{ts}]-[{phase}]-[{tag}] "
    padding = " " * len(prefix)
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if i == 0:
            log.write(f"{prefix}{line}\n")
        else:
            log.write(f"{padding}{line}\n")
    if not lines:
        log.write(prefix.rstrip() + "\n")
    log.write("\n")
    log.flush()


def write_implement_input(log, content):
    _write_section(log, "implement", "input", content)


def write_implement_output(log, line):
    log.write(f"[{_ts()}]-[implement]-[output] {line.rstrip(chr(10))}\n")
    log.flush()


def write_implement_message(log, message):
    log.write(f"[{_ts()}]-[implement] {message}\n")
    log.flush()


def write_task_review_input(log, content):
    _write_section(log, "task-review", "input", content)


def write_task_review_output(log, line):
    log.write(f"[{_ts()}]-[task-review]-[output] {line.rstrip(chr(10))}\n")
    log.flush()


def write_task_review_message(log, message):
    log.write(f"[{_ts()}]-[task-review] {message}\n")
    log.flush()


def write_footer(log, started_at, status):
    finished = datetime.now()
    duration = finished - started_at
    secs = int(duration.total_seconds())
    dur = f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
    icon = "✅" if status == "done" else "❌"
    log.write(f"\n{DOUBLE}\n")
    log.write(f"[{_ts()}]-[finished] {_ts_full()} | Duration: {dur} | {icon} {status}\n")
    log.write(f"{DOUBLE}\n")
    log.flush()
