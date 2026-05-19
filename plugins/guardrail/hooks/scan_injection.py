#!/usr/bin/env python3
"""
Compatibility shim for stale sessions.

Older sessions may still call guardrail/hooks/scan_injection.py even though the
scanner now lives in the scan-injection plugin. Keep this path fail-open so a
cache refresh does not break tool execution.
"""
import os
import runpy
import sys
from pathlib import Path

PLUGIN_ROOT = Path(
    os.environ.get("CLAUDE_CUSTOMS_ROOT")
    or os.environ.get("CLAUDE_PLUGIN_ROOT")
    or Path(__file__).resolve().parent.parent
)
CURRENT_HOOK = Path(__file__).resolve()


def _hook_path(plugin_root: Path) -> Path:
    return plugin_root / "hooks" / "scan_injection.py"


def _unique(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _candidate_plugin_roots() -> list[Path]:
    candidates = [
        # Local marketplace checkout: plugins/guardrail -> plugins/scan-injection.
        PLUGIN_ROOT.parent / "scan-injection",
        # Installed cache: cache/lauvsong/guardrail/local -> cache/lauvsong/scan-injection/local.
        PLUGIN_ROOT.parent.parent / "scan-injection" / PLUGIN_ROOT.name,
    ]

    scan_cache = PLUGIN_ROOT.parent.parent / "scan-injection"
    if scan_cache.is_dir():
        candidates.extend(sorted(path for path in scan_cache.iterdir() if path.is_dir()))

    return _unique(candidates)


def _find_target_hook() -> tuple[Path, Path] | None:
    for plugin_root in _candidate_plugin_roots():
        hook = _hook_path(plugin_root)
        if hook.exists() and hook.resolve() != CURRENT_HOOK:
            return plugin_root, hook
    return None


def _warn(message: str) -> None:
    print(f"[guardrail] WARNING: {message}", file=sys.stderr)


def _delegate(plugin_root: Path, hook: Path) -> None:
    previous_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    previous_argv = sys.argv[:]
    os.environ["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    sys.argv = [str(hook)]
    try:
        runpy.run_path(str(hook), run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if code == 0:
            sys.exit(0)
        _warn(f"delegated scan-injection hook exited with {code}; allowing tool use")
        sys.exit(0)
    except Exception as e:
        _warn(f"delegated scan-injection hook failed: {e}; allowing tool use")
        sys.exit(0)
    finally:
        if previous_root is None:
            os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        else:
            os.environ["CLAUDE_PLUGIN_ROOT"] = previous_root
        sys.argv = previous_argv


def main() -> None:
    target = _find_target_hook()
    if target is None:
        _warn(
            "scan-injection hook moved to scan-injection@lauvsong; "
            "install that plugin or start a new session to clear stale hook references"
        )
        sys.exit(0)

    plugin_root, hook = target
    _delegate(plugin_root, hook)


if __name__ == "__main__":
    main()
