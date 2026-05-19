"""
scan_commit.py 테스트.

가짜 git repo (tmp_path) 를 만들고 파일을 stage 한 뒤 훅을 실행한다.
실제 `git diff --cached` 동작을 그대로 사용 — mocking 없이 통합 테스트.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK = PLUGIN_ROOT / "hooks" / "scan_commit.py"


def run_hook(payload: dict, *, cwd: Path, config_path: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    env["CLAUDE_GUARDRAIL_CONFIG"] = str(config_path) if config_path else "/nonexistent"
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(cwd),
        timeout=10,
    )


def bash(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def write_config(tmp_path: Path, cfg: dict) -> Path:
    p = tmp_path / "guardrail.config.json"
    p.write_text(json.dumps(cfg))
    return p


@pytest.fixture
def git_repo(tmp_path):
    """초기 커밋이 있는 빈 git repo 를 만들고 작업 디렉토리로 반환."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "README.md").write_text("# init\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


# ─── 통과 케이스 ─────────────────────────────────────────────
def test_non_bash_passes(git_repo):
    r = run_hook({"tool_name": "Read", "tool_input": {}}, cwd=git_repo)
    assert r.returncode == 0


def test_non_commit_bash_passes(git_repo):
    r = run_hook(bash("ls -la"), cwd=git_repo)
    assert r.returncode == 0


def test_clean_commit_passes(git_repo):
    (git_repo / "feature.py").write_text("def add(a, b):\n    return a + b\n")
    subprocess.run(["git", "add", "feature.py"], cwd=git_repo, check=True)
    r = run_hook(bash("git commit -m 'add feature'"), cwd=git_repo)
    assert r.returncode == 0, f"clean code should pass (stderr={r.stderr!r})"


def test_git_commit_tree_passes(git_repo):
    """'git commit-tree' 같이 비슷한 명령은 인터셉트 안 함."""
    r = run_hook(bash("git commit-tree HEAD"), cwd=git_repo)
    assert r.returncode == 0


# ─── 차단 케이스 ─────────────────────────────────────────────
SECRET_SAMPLES = [
    ("AWS access key",     "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'"),
    ("GitHub PAT classic", "TOKEN = 'ghp_" + "a" * 36 + "'"),
    ("GitHub PAT fine",    "TOKEN = 'github_pat_" + "A" * 82 + "'"),
    ("Slack token",        "TOKEN = 'xoxb-12345-67890-abcdefghij'"),
    ("Stripe live",        "STRIPE = 'sk_live_" + "A" * 24 + "'"),
    ("PEM block",          "key = '-----BEGIN RSA PRIVATE KEY-----'"),
    ("Anthropic key",      "K = 'sk-ant-api03-" + "A" * 95 + "'"),
    ("Google API",         "K = 'AIza" + "a" * 35 + "'"),
    ("Generic api_key",    "api_key = 'abcdefghijklmnop1234'"),
    ("JWT",                "TOKEN = 'eyJabcdefghij.eyJabcdefghij.signaturehere'"),
]


@pytest.mark.parametrize("label,line", SECRET_SAMPLES)
def test_secret_in_staged_diff_blocks_commit(git_repo, label, line):
    (git_repo / "leak.py").write_text(line + "\n")
    subprocess.run(["git", "add", "leak.py"], cwd=git_repo, check=True)
    r = run_hook(bash("git commit -m wip"), cwd=git_repo)
    assert r.returncode == 2, f"[{label}] should block (stderr={r.stderr!r})"
    assert "BLOCKED" in r.stderr


def test_secret_only_in_existing_lines_does_not_block(git_repo):
    """이미 커밋되어 있던 시크릿(=staged 가 아닌)에는 반응하지 않아야 한다."""
    (git_repo / "legacy.py").write_text("OLD = 'AKIAIOSFODNN7EXAMPLE'\n")
    subprocess.run(["git", "add", "legacy.py"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "legacy"], cwd=git_repo, check=True)
    # 같은 파일에 무관한 추가만
    (git_repo / "legacy.py").write_text("OLD = 'AKIAIOSFODNN7EXAMPLE'\nnew_line = 1\n")
    subprocess.run(["git", "add", "legacy.py"], cwd=git_repo, check=True)
    r = run_hook(bash("git commit -m bump"), cwd=git_repo)
    assert r.returncode == 0, f"existing secret line should not block new commit (stderr={r.stderr!r})"


# ─── Legacy user config is ignored ──────────────────────────
def test_legacy_config_cannot_disable_scan(git_repo, tmp_path):
    config = write_config(tmp_path, {"scan_commit": False})
    (git_repo / "leak.py").write_text("AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n")
    subprocess.run(["git", "add", "leak.py"], cwd=git_repo, check=True)
    r = run_hook(bash("git commit -m wip"), cwd=git_repo, config_path=config)
    assert r.returncode == 2
    assert "AWS access key" in r.stderr


# ─── Edge: git 컨텍스트 없는 디렉토리 ────────────────────────
def test_outside_git_repo_passes(tmp_path):
    """git 이 아닌 디렉토리에서 git commit 명령 → diff 실패 → 통과 (가드레일 본체가 따로 막음)."""
    r = run_hook(bash("git commit -m x"), cwd=tmp_path)
    assert r.returncode == 0
