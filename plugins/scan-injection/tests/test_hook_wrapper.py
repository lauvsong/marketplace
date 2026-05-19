"""
Hook command wrapper for scan-injection.
"""
import json
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"


def test_hooks_json_contains_only_codex_supported_top_level_keys():
    data = json.loads(HOOKS_JSON.read_text())
    assert set(data) == {"hooks"}


def test_hooks_json_uses_shell_wrapper_instead_of_direct_python3():
    data = json.loads(HOOKS_JSON.read_text())
    command = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert command == "/bin/sh ${CLAUDE_PLUGIN_ROOT}/hooks/run_scan_injection.sh"


def test_wrapper_emits_context_warning_when_python3_is_missing():
    result = subprocess.run(
        ["/bin/sh", str(PLUGIN_ROOT / "hooks" / "run_scan_injection.sh")],
        input=json.dumps({"tool_name": "Read", "tool_response": "normal output"}),
        text=True,
        capture_output=True,
        env={
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PATH": "/nonexistent",
        },
        timeout=5,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "[scan-injection] WARNING" in context
    assert "Python 3 is required" in context


def test_wrapper_emits_context_warning_when_python3_is_too_old(tmp_path):
    python3 = tmp_path / "python3"
    python3.write_text("#!/bin/sh\nexit 1\n")
    python3.chmod(0o755)

    result = subprocess.run(
        ["/bin/sh", str(PLUGIN_ROOT / "hooks" / "run_scan_injection.sh")],
        input=json.dumps({"tool_name": "Read", "tool_response": "normal output"}),
        text=True,
        capture_output=True,
        env={
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PATH": str(tmp_path),
        },
        timeout=5,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "[scan-injection] WARNING" in context
    assert "Python 3.10 or newer is required" in context
