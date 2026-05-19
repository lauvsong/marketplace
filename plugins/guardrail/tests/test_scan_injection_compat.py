"""
Compatibility hook for sessions that still reference guardrail's old
scan_injection.py path after scan-injection moved to a separate plugin.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "scan_injection.py"


def run_compat_hook(plugin_root: Path, home: Path, payload: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        timeout=5,
    )


def test_missing_scan_injection_plugin_allows_without_breaking_session(tmp_path):
    guardrail_root = tmp_path / "plugins" / "guardrail"
    guardrail_root.mkdir(parents=True)

    result = run_compat_hook(
        guardrail_root,
        tmp_path,
        {"tool_name": "Bash", "tool_response": "plain command output"},
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert "scan-injection hook moved" in result.stderr


def test_delegates_to_sibling_scan_injection_plugin(tmp_path):
    guardrail_root = tmp_path / "plugins" / "guardrail"
    target_hook = tmp_path / "plugins" / "scan-injection" / "hooks" / "scan_injection.py"
    target_hook.parent.mkdir(parents=True)
    target_hook.write_text(
        "\n".join([
            "import json",
            "import sys",
            "payload = json.load(sys.stdin)",
            "print(json.dumps({'delegated_tool': payload['tool_name']}))",
        ]),
        encoding="utf-8",
    )

    result = run_compat_hook(
        guardrail_root,
        tmp_path,
        {"tool_name": "Bash", "tool_response": "plain command output"},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"delegated_tool": "Bash"}
    assert result.stderr == ""
