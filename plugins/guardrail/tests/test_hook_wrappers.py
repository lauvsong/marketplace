"""
Hook command wrappers.

Claude Code invokes hooks from hooks.json, so the registered command should
surface a clear message when python3 is unavailable instead of failing with a
plain command-not-found error.
"""
import json
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"


def _commands() -> list[str]:
    data = json.loads(HOOKS_JSON.read_text())
    commands = []
    for entries in data["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                commands.append(hook["command"])
    return commands


def test_hooks_json_contains_only_codex_supported_top_level_keys():
    data = json.loads(HOOKS_JSON.read_text())
    assert set(data) == {"hooks"}


def _run_without_python(script_name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", str(PLUGIN_ROOT / "hooks" / script_name)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        text=True,
        capture_output=True,
        env={
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PATH": "/nonexistent",
        },
        timeout=5,
    )


def _run_with_old_python(tmp_path: Path, script_name: str) -> subprocess.CompletedProcess:
    python3 = tmp_path / "python3"
    python3.write_text("#!/bin/sh\nexit 1\n")
    python3.chmod(0o755)
    return subprocess.run(
        ["/bin/sh", str(PLUGIN_ROOT / "hooks" / script_name)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        text=True,
        capture_output=True,
        env={
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
            "PATH": str(tmp_path),
        },
        timeout=5,
    )


def test_hooks_json_uses_shell_wrappers_instead_of_direct_python3():
    commands = _commands()
    assert commands
    assert all(command.startswith("/bin/sh ${CLAUDE_PLUGIN_ROOT}/hooks/") for command in commands)
    assert all("python3" not in command for command in commands)


def test_guardrail_wrapper_allows_with_clear_warning_when_python3_is_missing():
    result = _run_without_python("run_guardrail.sh")
    assert result.returncode == 0
    assert "WARNING" in result.stderr
    assert "guardrail requires Python 3" in result.stderr
    assert "allowing tool use without guardrail evaluation" in result.stderr


def test_scan_commit_wrapper_allows_with_clear_warning_when_python3_is_missing():
    result = _run_without_python("run_scan_commit.sh")
    assert result.returncode == 0
    assert "WARNING" in result.stderr
    assert "scan_commit requires Python 3" in result.stderr
    assert "allowing tool use without staged-secret scanning" in result.stderr


def test_guardrail_wrapper_allows_with_clear_warning_when_python3_is_too_old(tmp_path):
    result = _run_with_old_python(tmp_path, "run_guardrail.sh")
    assert result.returncode == 0
    assert "WARNING" in result.stderr
    assert "guardrail requires Python 3.10 or newer" in result.stderr
    assert "allowing tool use without guardrail evaluation" in result.stderr


def test_scan_commit_wrapper_allows_with_clear_warning_when_python3_is_too_old(tmp_path):
    result = _run_with_old_python(tmp_path, "run_scan_commit.sh")
    assert result.returncode == 0
    assert "WARNING" in result.stderr
    assert "scan_commit requires Python 3.10 or newer" in result.stderr
    assert "allowing tool use without staged-secret scanning" in result.stderr
