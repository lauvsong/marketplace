#!/usr/bin/env python3
"""
PreToolUse hook for Claude Code.

The Python stays small: load one JSON policy, classify the tool call, and
allow or block. Policy changes live in policies/default.json.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(
    os.environ.get("CLAUDE_CUSTOMS_ROOT")
    or os.environ.get("CLAUDE_PLUGIN_ROOT")
    or Path(__file__).resolve().parent.parent
)
_user_policy_env = os.environ.get("CLAUDE_GUARDRAIL_POLICY")
_legacy_user_policy = Path.home() / ".guardrail.json"


def _runtime_home() -> Path:
    home = Path.home()
    root_parts = set(PLUGIN_ROOT.parts)
    if ".codex" in root_parts:
        return home / ".codex"
    if ".claude" in root_parts:
        return home / ".claude"
    if (home / ".claude").exists():
        return home / ".claude"
    if (home / ".codex").exists():
        return home / ".codex"
    return home / ".claude"


def _user_policy_path() -> Path:
    return _runtime_home() / "plugins" / "guardrail" / "policy.json"


def _migrate_legacy_policy(path: Path) -> Path:
    if path.exists() or not _legacy_user_policy.exists():
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_legacy_user_policy), str(path))
    except Exception as e:
        print(
            f"WARN: failed to move legacy guardrail policy {_legacy_user_policy} to {path}: {e}",
            file=sys.stderr,
        )
        return _legacy_user_policy
    return path

if _user_policy_env:
    POLICY_PATH = Path(_user_policy_env)
else:
    _default_policy = PLUGIN_ROOT / "policies" / "default.json"
    _user_policy = _migrate_legacy_policy(_user_policy_path())
    if not _user_policy.exists():
        try:
            _user_policy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_default_policy, _user_policy)
        except Exception:
            pass
    POLICY_PATH = _user_policy if _user_policy.exists() else _default_policy


def _escape_path(path: Path) -> str:
    return re.escape(str(path))


SELF_PROTECTED_FILES = [
    r"\.claude/settings\.json",
    r"\.claude/settings\.local\.json",
    _escape_path(PLUGIN_ROOT / "hooks"),
    _escape_path(PLUGIN_ROOT / "policies"),
    _escape_path(PLUGIN_ROOT / "patterns"),
    _escape_path(PLUGIN_ROOT / ".claude-plugin"),
]

SELF_READ_ALLOWED_FILES = [
    r"\.claude/settings\.json",
    _escape_path(PLUGIN_ROOT / "hooks"),
    _escape_path(PLUGIN_ROOT / "policies"),
    _escape_path(PLUGIN_ROOT / "patterns"),
]

KNOWN_COMMAND_PATTERNS = {
    "rm -rf": r"\brm\s+-[a-z]*r[a-z]*f\b",
    "rm -fr": r"\brm\s+-[a-z]*f[a-z]*r\b",
    "rm -r": r"\brm\s+(-r\b|--recursive\b)",
    "mkfs": r"\bmkfs\b",
    "dd": r"\bdd\s+.*of=",
    "truncate": r"\btruncate\b",
    "chmod 777": r"\bchmod\s+777\b",
    "chown": r"\bchown\b",
    "git push": r"\bgit\s+push\b",
    "git push --force": r"\bgit\s+push\b.*?(--force\b|-f\b)",
    "git reset --hard": r"\bgit\s+reset\s+--hard\b",
    "git clean": r"\bgit\s+clean\b",
    "kubectl delete": r"\bkubectl\s+delete\b",
    "kubectl drain": r"\bkubectl\s+drain\b",
    "kubectl scale 0": r"\bkubectl\s+scale\b.*--replicas[= ]*0\b",
    "kubectl exec": r"\bkubectl\s+exec\b",
    "kubectl apply": r"\bkubectl\s+apply\b",
    "helm uninstall": r"\bhelm\s+(uninstall|delete)\b",
    "docker sys prune": r"\bdocker\s+system\s+prune\b",
    "brew uninstall": r"\bbrew\s+uninstall\b",
    "curl|wget pipe": r"\b(curl|wget)\b.*\|\s*(ba)?sh\b",
    "npm publish": r"\bnpm\s+publish\b",
    "gradle publish": r"\bgradle\w*\s+publish\b",
    "printenv": r"\bprintenv\b",
    "env dump": r"^\s*env\s*$",
    "echo secret var": r"\becho\b.*\$\{?\w*(TOKEN|SECRET|PASSWORD|KEY|CREDENTIAL)\w*\b",
    "show-token": r"\bgh\s+auth\s+.*--show-token\b",
    "eval": r"\beval\s",
    "sh -c": r"\b(ba|z)?sh\s+-c\b",
    "dot source": r"^\s*\.\s+\S",
    "base64 decode": r"\bbase64\s+(-d\b|--decode\b)",
    "printf hex": r"\bprintf\s+.*\\x[0-9a-fA-F]",
    "xxd reverse": r"\bxxd\s+.*-r\b",
    "gh pr merge": r"\bgh\s+pr\s+merge\b",
    "gh pr close": r"\bgh\s+pr\s+close\b",
    "gh issue close": r"\bgh\s+issue\s+close\b",
    "gh issue comment": r"\bgh\s+issue\s+comment\b",
    "gh repo delete": r"\bgh\s+repo\s+delete\b",
    "gh release delete": r"\bgh\s+release\s+delete\b",
    "gh api delete": r"\bgh\s+api\b.*-X\s+DELETE\b",
    "npm install": r"\bnpm\s+install\b",
    "npm i": r"\bnpm\s+i\b",
    "yarn add": r"\byarn\s+add\b",
    "pnpm add": r"\bpnpm\s+add\b",
    "pip install": r"\bpip3?\s+install\b",
    "brew install": r"\bbrew\s+install\b",
    "cargo install": r"\bcargo\s+install\b",
    "terraform destroy": r"\bterraform\s+destroy\b",
    "terraform apply": r"\bterraform\s+apply\b",
    "docker exec": r"\bdocker\s+exec\b",
    "docker rm": r"\bdocker\s+rm\b",
    "docker rmi": r"\bdocker\s+rmi\b",
    "sudo": r"\bsudo\s",
    "killall": r"\bkillall\s",
    "diskutil erase": r"\bdiskutil\s+(eraseDisk|partitionDisk)\b",
    "crontab remove": r"\bcrontab\s+-r\b",
    "launchctl unload": r"\blaunchctl\s+unload\b",
    "osascript": r"\bosascript\b",
    "defaults write": r"\bdefaults\s+write\b",
    "security": r"\bsecurity\s",
    "mongo shell": r"\bmongo\s",
    "mongosh": r"\bmongosh\b",
    "psql": r"\bpsql\s",
    "mysql": r"\bmysql\s",
    "ssh": r"\bssh\s",
    "scp": r"\bscp\s",
    "rsync": r"\brsync\s",
    "curl * | sh": r"\b(curl|wget)\b.*\|\s*(ba)?sh\b",
    "curl | sh": r"\b(curl|wget)\b.*\|\s*(ba)?sh\b",
    "sh < redirect": r"^\s*(ba)?sh\s+<",
}


def _load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        print(f"BLOCKED: guardrail policy file not found: {path}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"BLOCKED: failed to parse guardrail policy {path}: {e}", file=sys.stderr)
        sys.exit(2)


def _validate_regex(label: str, pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as e:
        print(f"BLOCKED: invalid guardrail policy regex ({label}): {e}", file=sys.stderr)
        sys.exit(2)


def _list_items(value) -> list:
    return value if isinstance(value, list) else []


def _dict_items(value) -> dict:
    return value if isinstance(value, dict) else {}


def _append_unique(values: list, additions: list[str]) -> None:
    for item in additions:
        if item not in values:
            values.append(item)


def _merge_prefixes(target: dict, source: dict) -> None:
    for server, prefixes in source.items():
        current = list(target.get(server, []) or [])
        _append_unique(current, [str(prefix) for prefix in _list_items(prefixes)])
        target[server] = current


def _compile_path_pattern(pattern: str) -> str:
    if pattern.startswith("~/"):
        return r"(?:~|/Users/[^/\s'\"]+)" + re.escape(pattern[1:])

    regex = []
    for char in pattern:
        if char == "*":
            regex.append(".*")
        elif char == "?":
            regex.append(".")
        else:
            regex.append(re.escape(char))
    return "".join(regex)


def _compile_command_pattern(command: str) -> str:
    normalized = " ".join(_split_command(command)) or re.sub(r"\s+", " ", command.strip())
    known = KNOWN_COMMAND_PATTERNS.get(normalized.lower())
    if known:
        return known

    regex = []
    for char in command:
        if char == "*":
            regex.append(".*?")
        elif char.isspace():
            regex.append(r"\s+")
        else:
            regex.append(re.escape(char))
    return r"\b" + "".join(regex) + r"\b"


def _command_entries(value) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        return [(str(name), str(command)) for name, command in value.items()]
    if isinstance(value, list):
        return [(str(command), str(command)) for command in value]
    return []


def _regex_values(value) -> list[str]:
    if isinstance(value, dict):
        return [str(pattern) for pattern in value.values()]
    if isinstance(value, list):
        return [str(pattern) for pattern in value]
    return []


def _merge_friendly_policy(policy: dict) -> None:
    protect = _dict_items(policy.get("protect"))
    protected = policy["protected_files"]
    _append_unique(protected, [_compile_path_pattern(str(pattern)) for pattern in _list_items(protect.get("files"))])

    block = _dict_items(policy.get("block"))
    deny = policy["deny"]
    for name, command in _command_entries(block.get("commands")):
        deny.setdefault(name, _compile_command_pattern(command))
    _merge_prefixes(policy["mcp_write_actions"], _dict_items(block.get("mcp_writes")))

    allow = _dict_items(policy.get("allow"))
    _append_unique(
        policy["read_allowed_files"],
        [_compile_path_pattern(str(pattern)) for pattern in _list_items(allow.get("read_files"))],
    )
    allow_repos = _dict_items(allow.get("repos"))
    scoped_repos = _dict_items(policy["scoped_allow"].get("repos"))
    for repo, rules in allow_repos.items():
        current = list(scoped_repos.get(repo, []) or [])
        _append_unique(current, [str(rule) for rule in _list_items(rules)])
        scoped_repos[repo] = current
    policy["scoped_allow"]["repos"] = scoped_repos

    advanced = _dict_items(policy.get("advanced"))
    for name, pattern in _dict_items(advanced.get("command_regex")).items():
        deny[str(name)] = str(pattern)
    _append_unique(protected, _regex_values(advanced.get("file_regex")))


def _self_protection_enabled(policy: dict) -> bool:
    value = policy.get("self_protection", {})
    if value is False:
        return False
    return _dict_items(value).get("enabled", True) is not False


def _load_policy() -> dict:
    policy = _load_json(POLICY_PATH)

    protected = list(policy.get("protected_files", []) or [])
    policy["protected_files"] = protected
    policy["read_allowed_files"] = list(policy.get("read_allowed_files", []) or [])
    policy["deny"] = dict(policy.get("deny", {}) or {})
    policy["mcp_write_actions"] = dict(policy.get("mcp_write_actions", {}) or {})
    policy["scoped_allow"] = dict(policy.get("scoped_allow", {}) or {})

    _merge_friendly_policy(policy)

    if _self_protection_enabled(policy):
        for pattern in SELF_PROTECTED_FILES:
            if pattern not in protected:
                protected.append(pattern)

        read_allowed = policy["read_allowed_files"]
        for pattern in SELF_READ_ALLOWED_FILES:
            if pattern not in read_allowed:
                read_allowed.append(pattern)

    for i, pattern in enumerate(policy["protected_files"]):
        _validate_regex(f"protected_files[{i}]", pattern)
    for i, pattern in enumerate(policy["read_allowed_files"]):
        _validate_regex(f"read_allowed_files[{i}]", pattern)
    for name, pattern in policy["deny"].items():
        _validate_regex(f"deny.{name}", pattern)

    policy["always_deny"] = set(policy.get("always_deny", []) or [])
    return policy


def _read_input() -> tuple[str, dict]:
    try:
        data = json.load(sys.stdin)
        return data.get("tool_name", ""), data.get("tool_input", {})
    except Exception:
        sys.exit(0)


def _search(pattern: str, text: str, *, flags: int = re.IGNORECASE) -> bool:
    try:
        return re.search(pattern, text, flags) is not None
    except re.error as e:
        print(f"[guardrail] WARN: bad regex {pattern!r}: {e}", file=sys.stderr)
        return False


def _match_any(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        if _search(pattern, text):
            return pattern
    return None


def _split_command(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return []


def _repo_from_remote_url(url: str) -> str | None:
    normalized = url.strip().removesuffix(".git")
    match = re.search(r"[:/]([^/:]+)/([^/]+)$", normalized)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _git_remote_repo(remote: str = "origin") -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return _repo_from_remote_url(result.stdout)


def _git_push_remote(cmd: str) -> str:
    args = _split_command(cmd)
    if not args:
        match = re.search(r"\bgit\s+push\s+(?!-)(\S+)", cmd)
        return match.group(1) if match else "origin"

    try:
        git_index = args.index("git")
        push_index = args.index("push", git_index + 1)
    except ValueError:
        return "origin"

    for arg in args[push_index + 1:]:
        if arg.startswith("-"):
            continue
        return arg
    return "origin"


def _gh_repo_arg(cmd: str) -> str | None:
    args = _split_command(cmd)
    for i, arg in enumerate(args):
        if arg in ("--repo", "-R") and i + 1 < len(args):
            return args[i + 1].removesuffix(".git")
        if arg.startswith("--repo="):
            return arg.split("=", 1)[1].removesuffix(".git")
    return None


def _repo_for_command(rule_name: str, cmd: str) -> str | None:
    if rule_name.startswith("git push"):
        return _git_remote_repo(_git_push_remote(cmd))
    if rule_name.startswith("gh "):
        repo = _gh_repo_arg(cmd)
        return _repo_from_remote_url(repo) or repo if repo else _git_remote_repo()
    return _git_remote_repo()


def _is_scoped_allowed(policy: dict, rule_name: str, cmd: str) -> bool:
    repos = (policy.get("scoped_allow", {}) or {}).get("repos", {}) or {}
    repo = _repo_for_command(rule_name, cmd)
    if not repo:
        return False
    allowed_rules = repos.get(repo, []) or []
    return "*" in allowed_rules or rule_name in allowed_rules


def _check_mcp(tool: str, policy: dict) -> None:
    parts = tool.split("__", 2)
    if len(parts) == 3:
        server, action = parts[1], parts[2]
        prefixes = tuple(policy["mcp_write_actions"].get(server, []) or [])
        if prefixes and action.startswith(prefixes):
            print(f"BLOCKED: write operation on {server} MCP ({action})", file=sys.stderr)
            sys.exit(2)
    sys.exit(0)


def _check_file_access(tool: str, tool_input: dict, policy: dict) -> None:
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    matched = _match_any(policy["protected_files"], file_path)
    if matched is None:
        sys.exit(0)
    if tool == "Read" and _match_any(policy["read_allowed_files"], file_path):
        sys.exit(0)

    print(f"BLOCKED: {tool} access to protected file ({matched})", file=sys.stderr)
    sys.exit(2)


def _check_bash(tool_input: dict, policy: dict) -> None:
    cmd = tool_input.get("command", "")
    if not cmd:
        sys.exit(0)

    matched = _match_any(policy["protected_files"], cmd)
    if matched is not None:
        print(f"BLOCKED: access to protected file ({matched})", file=sys.stderr)
        sys.exit(2)

    for name in policy["always_deny"]:
        pattern = policy["deny"].get(name)
        if pattern and _search(pattern, cmd, flags=re.IGNORECASE | re.MULTILINE):
            print(f"BLOCKED: {name} is not allowed", file=sys.stderr)
            sys.exit(2)

    for name, pattern in policy["deny"].items():
        if not _search(pattern, cmd, flags=re.IGNORECASE | re.MULTILINE):
            continue
        if _is_scoped_allowed(policy, name, cmd):
            sys.exit(0)
        print(f"BLOCKED: {name} is not allowed", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


def main() -> None:
    tool, tool_input = _read_input()
    if not (tool == "Bash" or tool.startswith("mcp__") or tool in ("Read", "Edit", "Write", "MultiEdit")):
        sys.exit(0)

    policy = _load_policy()

    if tool.startswith("mcp__"):
        _check_mcp(tool, policy)

    if tool in ("Read", "Edit", "Write", "MultiEdit"):
        _check_file_access(tool, tool_input, policy)

    if tool == "Bash":
        _check_bash(tool_input, policy)

    sys.exit(0)


if __name__ == "__main__":
    main()
