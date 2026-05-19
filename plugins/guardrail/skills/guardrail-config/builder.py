#!/usr/bin/env python3
"""Deprecated guardrail-config builder compatibility entrypoint."""
import sys


def main() -> int:
    print(
        "guardrail-config builder is deprecated; edit ~/.claude/plugins/guardrail/policy.json directly.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
