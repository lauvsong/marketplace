#!/bin/sh
set -eu

PLUGIN_ROOT=${CLAUDE_PLUGIN_ROOT:-}
if [ -z "$PLUGIN_ROOT" ]; then
  case "$0" in
    */*) SCRIPT_DIR=${0%/*} ;;
    *) SCRIPT_DIR=. ;;
  esac
  PLUGIN_ROOT=$SCRIPT_DIR/..
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'WARNING: guardrail requires Python 3, so the safety policy cannot be evaluated; allowing tool use without guardrail evaluation. Install Python 3 and restart Claude Code.' >&2
  exit 0
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  printf '%s\n' 'WARNING: guardrail requires Python 3.10 or newer, so the safety policy cannot be evaluated; allowing tool use without guardrail evaluation. Upgrade Python and restart Claude Code.' >&2
  exit 0
fi

exec python3 "$PLUGIN_ROOT/hooks/guardrail.py"
