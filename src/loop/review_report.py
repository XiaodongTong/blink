"""Review result dataclass, report persistence, and verdict parsing."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ReviewResult:
    success: bool
    verdict: str = ""
    report_path: str = ""
    error: str = ""
    info: str = ""


def ensure_review_dir(dir_path):
    review_dir = Path(dir_path) / "docs" / "blink" / "code-review"
    review_dir.mkdir(parents=True, exist_ok=True)
    return review_dir


def _branch_slug(branch):
    slug = branch.replace("/", "-")
    slug = re.sub(r"-+", "-", slug)
    return slug


def save_report(dir_path, branch, base, verdict, content, extra_sections=None):
    review_dir = ensure_review_dir(dir_path)
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    slug = _branch_slug(branch)
    base_name = f"{slug}-{date_str}-{time_str}"
    report_path = review_dir / f"{base_name}.md"
    # Collision avoidance: append counter if file exists
    if report_path.exists():
        for n in range(2, 100):
            report_path = review_dir / f"{base_name}-{n}.md"
            if not report_path.exists():
                break

    verdict_labels = {
        "APPROVE": "✓ 通过",
        "APPROVE_WITH_NOTES": "⚠ 有建议",
        "DENY": "✗ 需修改",
    }
    header = (
        f"# Code Review: {branch}\n"
        f"\n"
        f"- **分支**: `{branch}`\n"
        f"- **基准**: `{base}`\n"
        f"- **日期**: {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"- **结论**: {verdict_labels.get(verdict, verdict)}\n"
        f"\n"
        f"---\n"
        f"\n"
    )

    extra = ""
    if extra_sections:
        for title, body in extra_sections:
            extra += f"## {title}\n\n{body}\n\n---\n\n"

    report_path.write_text(header + extra + content)
    return str(report_path)


def parse_verdict(output, fallback="APPROVE_WITH_NOTES"):
    """Parse VERDICT from review output. Returns (verdict, output)."""
    if not output:
        return fallback, output or ""
    # Strict match: VERDICT at start of line
    matches = re.findall(r"^VERDICT:\s*(APPROVE_WITH_NOTES|DENY|APPROVE)\s*$", output, re.MULTILINE)
    if matches:
        return matches[-1], output
    # Less strict fallback
    matches = re.findall(r"VERDICT:\s*(APPROVE_WITH_NOTES|DENY|APPROVE)", output)
    if matches:
        return matches[-1], output
    return fallback, output
