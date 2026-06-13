"""Cybervisor runner backend."""

from __future__ import annotations

import subprocess
from pathlib import Path

from blink.loop import log_format
from blink.loop.runner import Runner as RunnerBase


class CybervisorRunner(RunnerBase):
    def run(self, prompt: str, cwd: str, log_file: str | Path | None = None,
            prompt_file: str | Path | None = None, **kwargs: object) -> int:
        cmd = ["cybervisor", "run"]

        with open(log_file, "a") if log_file else open("/dev/null", "a") as log:
            stdin_fh = open(prompt_file, "r") if prompt_file else None
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdin=stdin_fh if stdin_fh else subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                if not stdin_fh:
                    assert process.stdin is not None
                    process.stdin.write(prompt)
                    process.stdin.close()

                assert process.stdout is not None
                for line in process.stdout:
                    print(line, end="")
                    log_format.write_implement_output(log, line)

                process.wait()
            finally:
                if stdin_fh:
                    stdin_fh.close()

        return process.returncode
