"""Claude Code runner backend with round-loop execution."""

import subprocess
import time
from pathlib import Path

from blink.loop import log_format
from blink.loop.runner import Runner
from blink.config import get_default_model

COMPLETION_SUFFIX = (

    "\n\nWhen you have fully completed all the requested work, "
    "output the following on its own line to signal completion:\n"
    "<promise>COMPLETE</promise>\n"
    "Do NOT output this unless you have finished everything. "
    "If there is still work to do, end your response normally — "
    "another iteration will pick up where you left off."
)


class ClaudeRunner(Runner):
    def run(self, prompt, cwd, log_file=None, max_rounds=5, prompt_file=None, model=None):
        """
        Run Claude Code in a loop with configurable round limit.

        Args:
            prompt: The prompt to send to Claude Code
            cwd: Working directory for the task
            log_file: Optional path to log file
            max_rounds: Maximum number of loop iterations (default 5)
            prompt_file: Optional path to prompt file (used as stdin like CybervisorRunner)
            model: Claude model to use (default: from config)

        Returns:
            0 on success (completion signal detected), non-zero on failure
        """
        resolved_model = model or get_default_model("task")
        enriched_prompt = prompt + COMPLETION_SUFFIX

        constitution_path = Path(cwd) / "docs" / "blink" / "constitution.md"
        constitution_content = ""
        if constitution_path.exists():
            constitution_content = (
                "<constitution>\n"
                + constitution_path.read_text()
                + "\n</constitution>\n\n"
            )

        log = open(log_file, "a") if log_file else open("/dev/null", "a")
        try:
            if constitution_content:
                log_format.write_implement_message(log, "Constitution loaded from docs/blink/constitution.md")

            for round_num in range(1, max_rounds + 1):
                log_format.write_round(log, round_num, max_rounds)

                print(f"\n{'=' * 60}")
                print(f" Round {round_num}/{max_rounds} ")
                print(f"{'=' * 60}")

                if prompt_file:
                    with open(prompt_file, "r") as f:
                        final_input = constitution_content + f.read() + COMPLETION_SUFFIX
                else:
                    final_input = constitution_content + enriched_prompt

                log_format.write_implement_input(log, final_input)

                print(f"\n{'─' * 60}")
                print(" Input to Claude:")
                print(f"{'─' * 60}")
                print(final_input)
                print(f"{'─' * 60}\n")

                process = subprocess.Popen(
                    ["claude", "-p", "--dangerously-skip-permissions", "--model", resolved_model],
                    cwd=cwd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                process.stdin.write(final_input)
                process.stdin.close()

                output_parts = []
                for line in process.stdout:
                    print(line, end="")
                    log_format.write_implement_output(log, line)
                    output_parts.append(line)

                process.wait()

                accumulated = "".join(output_parts)
                if "<promise>COMPLETE</promise>" in accumulated:
                    log_format.write_implement_message(log, "Completion signal detected")
                    return 0

                if round_num < max_rounds:
                    log_format.write_implement_message(log, f"Round {round_num} complete, sleeping 2s before next round")
                    time.sleep(2)

            log_format.write_implement_message(log, f"All {max_rounds} rounds exhausted without completion signal")
            return 1
        finally:
            log.close()
