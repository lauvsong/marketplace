"""Tests for the deprecated guardrail-config builder."""
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BUILDER = PLUGIN_ROOT / "skills" / "guardrail-config" / "builder.py"


def test_builder_is_disabled(tmp_path):
    config = tmp_path / "guardrail.config.json"
    config.write_text('{"preset": "standard"}')
    before = config.read_text()

    r = subprocess.run(
        [sys.executable, str(BUILDER), "preset", "strict"],
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert r.returncode == 2
    assert "deprecated" in r.stderr
    assert config.read_text() == before
