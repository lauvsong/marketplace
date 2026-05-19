#!/usr/bin/env python3
"""
PreToolUse hook: git commit 직전 staged diff 의 추가 라인을 시크릿 패턴과 매칭.

Bash 명령 중 `git commit` 만 인터셉트하고 나머지는 통과한다.
패턴은 patterns/secrets.json 에 정의한다.

Exit 0 = allow, Exit 2 = block.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
PATTERN_FILE = PLUGIN_ROOT / "patterns" / "secrets.json"

GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b(?!-)", re.IGNORECASE)


def _load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[guardrail/scan_commit] WARN: parse failed {path}: {e}", file=sys.stderr)
        return {}


def _build_patterns() -> dict:
    return dict(_load_json(PATTERN_FILE).get("patterns", {}) or {})


def _staged_diff() -> str:
    """staged diff 의 추가된 라인만 반환. git 호출 실패 시 빈 문자열."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--no-color", "-U0"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return ""
    except Exception:
        return ""

    added_lines = []
    for line in result.stdout.splitlines():
        # file header (+++ b/foo.py) 제외, 실제 추가 (+) 만
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
    return "\n".join(added_lines)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = data.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(cmd):
        sys.exit(0)

    patterns = _build_patterns()
    if not patterns:
        sys.exit(0)

    diff = _staged_diff()
    if not diff:
        sys.exit(0)

    hits = []
    for name, pattern in patterns.items():
        try:
            if re.search(pattern, diff):
                hits.append(name)
        except re.error as e:
            print(f"[guardrail/scan_commit] WARN: bad regex {name!r}: {e}", file=sys.stderr)

    if hits:
        print(
            "BLOCKED: staged diff contains likely secret(s): " + ", ".join(hits) +
            ". Remove them and re-stage before committing.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
