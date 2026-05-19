# guardrail

`PreToolUse` 훅에서 위험한 툴 호출을 실행 직전에 막는 플러그인입니다.

주요 보호 대상은 Bash 명령, 파일 읽기·쓰기, MCP 쓰기 도구, `git commit` 직전 staged diff입니다. Prompt injection 경고는 별도 플러그인인 [scan-injection](../scan-injection/README.md)이 담당합니다.

플러그인 이름은 `guardrail@lauvsong`이고, 마켓플레이스 등록 URL은 `https://github.com/lauvsong/marketplace`입니다.

## 출력 예시

차단 규칙에 걸리면 stderr에 차단 사유가 출력되고 해당 툴 호출은 실행되지 않습니다.

```text
PreToolUse:Bash hook error: BLOCKED: rm -rf is not allowed
```

로컬에서 훅을 직접 실행하면 stderr는 다음처럼 더 짧게 나옵니다.

```text
BLOCKED: rm -rf is not allowed
```

## 목차

- [출력 예시](#출력-예시)
- [역할](#역할)
- [차단 대상](#차단-대상)
- [요구사항](#요구사항)
- [설치](#설치)
- [정책 수정](#정책-수정)
- [자기보호 범위](#자기보호-범위)
- [MCP 쓰기 차단](#mcp-쓰기-차단)
- [로컬 환경 주의사항](#로컬-환경-주의사항)
- [동작 방식](#동작-방식)
- [파일 구조](#파일-구조)
- [설치 확인](#설치-확인)
- [참고](#참고)

## 역할

기본 권한 설정만으로도 막을 수 있는 일이 많습니다. `guardrail`은 로컬에서 반복해서 필요한 차단 규칙을 개인 정책 파일로 관리하려고 둔 보조 보호 장치입니다.

| 상황 | guardrail 처리 |
|------|----------------|
| 같은 Bash 동작이 옵션 순서, pipe, 변수, `sh -c`, `eval`, decode 명령으로 바뀌어 실행됩니다. | 실행 직전 명령 문자열을 다시 검사해 `git push --force`, `curl ... | sh`, `eval`, `base64 --decode`, `sh -c` 같은 known pattern을 차단합니다. |
| 특정 repo에서는 `git push`를 허용하되 force push는 어디서도 막고 싶습니다. | `allow.repos`와 `always_deny`로 repo별 예외와 절대 차단을 나눕니다. |
| 설정 파일은 읽어야 하지만 수정은 막고 싶습니다. | `protect.files`와 `allow.read_files`로 Read 예외와 Edit/Write 차단을 따로 둡니다. |
| MCP tool 이름이 길고 create/update/delete 계열을 매번 deny에 넣기 번거롭습니다. | `block.mcp_writes`에서 서버별 action 앞부분 기준으로 쓰기 계열을 묶어 막습니다. |
| 권한 프롬프트를 통과한 뒤에도 commit에 시크릿이 섞일 수 있습니다. | `git commit` 직전 staged diff의 추가 라인을 검사해 token/key/PEM/JWT 패턴이 있으면 커밋을 막습니다. |
| 보호 장치 자체가 에이전트 작업 중 약해질 수 있습니다. | 훅, 정책, 탐지 패턴, 플러그인 메타데이터, 일부 Claude 설정 파일을 기본 보호 대상으로 둡니다. |

이 플러그인은 기본 권한 기능을 끄거나 대체하지 않습니다. 기본 권한 설정은 그대로 두고, 실행 직전 한 번 더 검사합니다.

## 차단 대상

- 파괴적 Bash 명령: `rm -rf`, `dd`, `mkfs`, `terraform destroy`, `git push --force`, `sudo`, `eval`, `curl ... | sh` 등
- 보호 파일 Read/Edit/Write: `~/.ssh`, `~/.aws`, `.env`, `*.pem`, `~/.claude/settings.json` 등
- 외부 쓰기 명령: `git push`, `gh pr create`, `gh pr comment`, `gh pr merge`, `npm publish` 등
- 쓰기 모드 MCP 호출: Jira/Confluence create/update/delete, Notion delete 등
- `git commit` 직전 시크릿 스캔: staged diff의 추가 라인에서 AWS/GitHub/OpenAI/Anthropic 키, Stripe, Slack, PEM block, JWT 등을 검사

차단 규칙에 걸리면 훅이 stderr로 차단 사유를 출력하고 해당 툴 호출을 막습니다.

## 요구사항

- Claude Code 또는 Codex 플러그인 런타임
- `/bin/sh`를 실행할 수 있는 macOS/Linux 계열 shell 환경
- 훅을 실행하는 프로세스의 `PATH`에서 찾을 수 있는 Python 3.10+ (`python3`)

순정 Windows shell에서는 별도 `sh` 실행 환경이 필요합니다.

## 요구사항을 만족하지 못한 경우

- `/bin/sh`가 없거나 `${CLAUDE_PLUGIN_ROOT}`가 잘못 전달되면 shell wrapper가 Python 코드까지 도달하지 못합니다.
- Python 3.10+를 찾지 못하면 정책을 평가하지 않고 경고만 출력한 뒤 해당 툴 호출을 허용합니다.
- 정책 파일을 열지 못하거나 JSON/정규식 파싱에 실패하면 해당 툴 호출을 차단합니다. 잘못된 정책으로 보호하는 것보다 멈추는 쪽을 선택합니다.

## 설치

### Claude Code

```bash
/plugin marketplace add https://github.com/lauvsong/marketplace
/plugin install guardrail@lauvsong
```

### Codex

```bash
codex plugin marketplace add https://github.com/lauvsong/marketplace
codex plugin add guardrail@lauvsong
```

설치 후 새 세션을 시작하면 훅이 활성화됩니다.

개인 정책 파일은 설치 명령을 실행하는 순간이 아니라 첫 `guardrail` 훅 실행 시 자동 생성됩니다. 첫 `Bash`, `Read`, `Edit`, `Write`, `MultiEdit`, `mcp__*` 툴 호출이 생성 시점입니다.

### 업데이트

Claude Code:

```bash
claude plugin update guardrail@lauvsong
```

Codex:

```bash
codex plugin marketplace upgrade
```

플러그인 내부 파일과 `policies/default.json`은 업데이트될 수 있지만 이미 생성된 개인 `policy.json`은 덮어쓰거나 자동 병합하지 않습니다. 새 기본 정책을 반영하려면 내부 `default.json`과 개인 `policy.json`을 비교한 뒤 필요한 항목만 직접 반영합니다.

같은 버전에서 플러그인 캐시가 남아 있으면 업데이트 후에도 파일이 바뀌지 않을 수 있습니다. 그때는 플러그인을 지웠다가 다시 설치하고 새 세션에서 확인합니다.

## 정책 수정

규칙은 개인 정책 파일에서 수정합니다.

| 런타임 | 개인 정책 파일 |
|------|------|
| Claude Code | `~/.claude/plugins/guardrail/policy.json` |
| Codex | `~/.codex/plugins/guardrail/policy.json` |

개인 정책 파일은 첫 훅 실행 시 플러그인 내부의 `policies/default.json`을 복사해 생성합니다. 한 번 생성된 개인 정책 파일은 `plugin update`나 marketplace upgrade로 덮어쓰지 않습니다.

플러그인 내부의 `plugins/guardrail/policies/default.json`은 새 개인 정책 파일을 만들 때 쓰는 기본값입니다. 이 파일을 직접 수정하면 플러그인 업데이트나 재설치 때 바뀔 수 있으므로 사용자 커스텀은 개인 정책 파일에 둡니다.

`CLAUDE_GUARDRAIL_POLICY` 환경 변수를 지정하면 기본 개인 정책 파일 대신 해당 JSON 파일을 읽습니다. 이 방식은 테스트나 로컬 실험용으로 권장합니다.

보통은 아래 필드만 쓰면 됩니다.

```json
{
  "self_protection": {
    "enabled": true
  },
  "protect": {
    "files": ["**/.env", "**/.ssh/**", "**/*.pem"]
  },
  "block": {
    "commands": ["git push", "git push --force", "npm publish"],
    "mcp_writes": {
      "mcp-jira": ["jira_create_", "jira_update_", "jira_delete_"]
    }
  },
  "allow": {
    "read_files": ["~/.claude/settings.json"],
    "repos": {
      "my-team/my-repo": ["git push"]
    }
  },
  "always_deny": ["git push --force"],
  "advanced": {
    "command_regex": {
      "custom dangerous command": "\\bcustomcmd\\b"
    },
    "file_regex": {
      "vault token": "\\.vault-token\\b"
    }
  }
}
```

각 필드 설명:

| 필드 | 타입 | 설명 |
|------|------|------|
| `protect.files` | `string[]` | 보호할 파일/경로입니다. `**/.env`, `**/.ssh/**`, `~/.npmrc`처럼 적습니다. |
| `block.commands` | `string[]` 또는 `object` | 차단할 Bash 명령입니다. `"npm publish"`처럼 터미널에 치는 형태로 적습니다. |
| `block.mcp_writes` | `object` | MCP 서버별 차단할 action 앞부분 목록입니다. |
| `allow.read_files` | `string[]` | 보호 경로여도 `Read`만 허용할 파일/경로입니다. |
| `allow.repos` | `object` | repo별 허용 규칙입니다. key는 `owner/repo`, value는 허용할 rule name 목록입니다. |
| `always_deny` | `string[]` | repo 허용으로도 풀 수 없는 절대 차단 규칙 이름 목록입니다. |
| `advanced.command_regex` | `object` | 정규식이 꼭 필요한 Bash 차단 규칙입니다. |
| `advanced.file_regex` | `object` 또는 `string[]` | 정규식이 꼭 필요한 파일 보호 규칙입니다. |
| `self_protection.enabled` | `boolean` | `true`이면 자기보호 대상이 기본으로 보호됩니다. `false`이면 내장 자기보호만 끕니다. |

`block.commands`에 문자열 배열을 쓰면 명령 문자열 자체가 rule name입니다. repo별 허용이나 `always_deny`에서도 같은 이름을 씁니다.

예를 들어 아래 설정은 `my-team/my-repo`에서만 `git push`를 허용합니다. `git push --force`는 `always_deny`에 있으므로 허용되지 않습니다.

```json
{
  "block": {
    "commands": ["git push", "git push --force"]
  },
  "allow": {
    "repos": {
      "my-team/my-repo": ["git push"]
    }
  },
  "always_deny": ["git push --force"]
}
```

`block.commands`는 단순 문자열 포함이 아니라 내부 deny 정규식으로 컴파일됩니다. 예를 들어 `"git push --force"`는 `git push -f`, `git push origin main --force`까지 막습니다. `"eval"`, `"sh -c"`, `"curl * | sh"`처럼 command wrapper나 pipe 실행도 known pattern을 사용합니다.

## 자기보호 범위

자기보호는 에이전트가 guardrail 훅을 고치거나, 정책 파일을 바꾸거나, 탐지 패턴을 삭제하거나, Claude 설정에서 hook 연결을 약하게 만드는 실수를 막기 위한 기본 보호입니다.

기본값에서는 이 보호가 켜져 있습니다. 사용자가 `protect.files`에 적지 않아도 다음 경로는 보호 대상에 들어갑니다.

여기서 "자기 자신"은 현재 실행 중인 `guardrail` 플러그인의 설치 루트(`CLAUDE_PLUGIN_ROOT`)를 기준으로 합니다. Claude Code에서는 보통 `~/.claude/plugins/cache/.../guardrail/...` 아래이고, Codex에서는 `~/.codex/plugins/cache/.../guardrail/...` 아래입니다.

| 대상 | 예시 | 보호 이유 |
|------|------|-----------|
| 플러그인 내부 `hooks/` | `hooks/guardrail.py`, `hooks/run_guardrail.sh`, `hooks/hooks.json`, `hooks/scan_commit.py`, `hooks/scan_injection.py` | 실제 차단 로직과 hook 등록 명령이 들어 있습니다. |
| 플러그인 내부 `policies/` | `policies/default.json` | 새 개인 정책의 기본값입니다. |
| 플러그인 내부 `patterns/` | `patterns/secrets.json` | 시크릿 탐지 패턴입니다. |
| 플러그인 내부 `.claude-plugin/` | `.claude-plugin/plugin.json` | 플러그인 메타데이터와 hook 연결 정보입니다. |
| Claude 설정 파일 | `~/.claude/settings.json`, `~/.claude/settings.local.json` | Claude Code의 hook 연결을 약하게 만들거나 제거하지 못하게 합니다. |

`hooks/`, `policies/`, `patterns/`, `~/.claude/settings.json`은 읽기(`Read`)만 허용하고 수정은 차단합니다. `.claude-plugin/`과 `~/.claude/settings.local.json`은 읽기까지 포함해 보호 대상입니다. Bash 명령에 위 경로가 들어가도 차단됩니다.

현재 구현에서 내장 설정 파일 보호는 `~/.claude/settings.json`, `~/.claude/settings.local.json`만 대상으로 합니다. Codex의 `~/.codex/config.toml` 같은 전역 설정 파일은 자기보호 목록에 자동 포함되지 않으므로, 필요하면 개인 정책의 `protect.files`에 직접 추가해야 합니다.

직접 커스텀해야 한다면 개인 정책 파일에 아래 설정을 둡니다.

```json
{
  "self_protection": {
    "enabled": false
  }
}
```

이 설정은 guardrail의 자기보호만 해제합니다. 사용자가 `protect.files`, `block.commands`, `always_deny`, `block.mcp_writes`에 적은 일반 보호 규칙은 계속 적용됩니다.

주의할 점:

- 이 옵션을 끄면 에이전트가 guardrail 훅, 정책, 패턴, 플러그인 메타데이터를 수정할 수 있습니다.
- `~/.claude/settings*.json` 내장 보호도 함께 풀립니다.
- 개인 정책 파일은 유지되지만 내부 `default.json`은 플러그인 업데이트로 바뀔 수 있습니다.
- 이 옵션은 boolean `false`일 때만 꺼집니다. 문자열 `"false"`는 해제로 취급하지 않습니다.

## MCP 쓰기 차단

`block.mcp_writes`로 MCP 서버별 차단할 action을 지정합니다. 키는 MCP 서버 이름(tool name의 `mcp__<server>__` 부분), 값은 action 이름 앞부분 목록입니다. action 이름이 목록의 어느 항목으로 시작하면 차단됩니다.

```json
{
  "block": {
    "mcp_writes": {
      "my-jira": ["jira_create_", "jira_update_", "jira_delete_"],
      "my-notion": ["API-delete-", "API-patch-"]
    }
  }
}
```

예를 들어 서버 이름이 `my-jira`이면 `mcp__my-jira__jira_create_issue` 같은 tool이 차단됩니다. 읽기 전용 tool(`jira_get_`, `jira_search_` 등)은 앞부분 목록에 포함시키지 않으면 허용됩니다.

## 로컬 환경 주의사항

- 훅 명령은 `/bin/sh ${CLAUDE_PLUGIN_ROOT}/hooks/run_*.sh` 형태로 등록됩니다. `sh`가 없거나 `${CLAUDE_PLUGIN_ROOT}`가 잘못 들어오면 Python 코드까지 도달하지 못합니다.
- wrapper는 훅을 실행한 프로세스의 `PATH`에서 `python3`를 찾고 3.10 이상인지 확인합니다. 조건을 만족하지 못하면 경고만 출력하고 해당 툴 호출을 허용합니다.
- `CLAUDE_GUARDRAIL_POLICY`를 지정하면 기본 개인 설정 경로 대신 그 파일을 읽습니다. 테스트용 환경 변수가 shell 설정에 남아 있으면 예상과 다른 정책을 볼 수 있습니다.
- 현재 실행 중인 세션은 플러그인 업데이트 전의 훅을 계속 사용할 수 있습니다. 업데이트, 재설치, 설정 경로 이동 뒤에는 새 세션에서 확인합니다.
- 이전 세션이 guardrail 내부의 옛 `hooks/scan_injection.py` 경로를 계속 호출하면 `scan-injection hook moved` 경고가 보일 수 있습니다. guardrail은 이 경로를 호환 shim으로 남겨 두며, `scan-injection` 플러그인이 있으면 위임하고 없으면 경고만 출력한 뒤 해당 툴 호출을 허용합니다.

## 동작 방식

플러그인 런타임이 툴을 실행하기 직전 `PreToolUse` 훅을 호출합니다. 훅은 stdin으로 tool name과 input을 받아 판정합니다.

### guardrail.py

`Bash`, `Read`, `Edit`, `Write`, `MultiEdit`, `mcp__*` 툴의 `PreToolUse`에서 실행됩니다.

판정 순서:

1. 보호 파일 경로가 포함되어 있으면 차단
2. MCP 쓰기 action 앞부분이 매칭되면 차단
3. Bash 명령이 `block.commands` 또는 `deny` 규칙에 매칭되는지 검사
4. 매칭된 규칙이 `always_deny`면 무조건 차단
5. 현재 repo 또는 `gh --repo/-R` repo가 `allow.repos`에 있으면 허용
6. 그 외 command deny 매칭은 차단

### scan_commit.py

`Bash` 툴의 `PreToolUse`에서 실행됩니다. `git commit` 명령이 아니면 즉시 허용합니다.

`git diff --cached`로 staged diff의 추가 라인만 추출해 [`patterns/secrets.json`](patterns/secrets.json)의 정규식과 매칭합니다. AWS/GitHub/OpenAI/Anthropic 키, Stripe, Slack 토큰, PEM block, JWT 등이 탐지되면 커밋을 차단합니다.

## 파일 구조

```text
plugins/
  guardrail/
    .claude-plugin/
      plugin.json
    hooks/
      hooks.json
      run_guardrail.sh
      run_scan_commit.sh
      guardrail.py
      scan_commit.py
      scan_injection.py  # 이전 세션 호환 shim
    policies/
      default.json
    patterns/
      secrets.json
    tests/
      test_guardrail.py
      test_scan_commit.py
```

## 설치 확인

Claude Code에서는 플러그인 목록에 `guardrail@lauvsong`이 보이는지 확인합니다.

Codex에서는 다음 명령으로 설치 상태를 확인합니다.

```bash
codex plugin list
```

개발 중 로컬 테스트:

```bash
python3 -m pytest plugins/guardrail/tests
```

## 참고

- **`bypassPermissions: true` 사용 금지**: 권한 프롬프트를 건너뛰는 모드라 guardrail 검증을 믿기 어렵습니다. 관련 이슈: [#20946](https://github.com/anthropics/claude-code/issues/20946), [#26923](https://github.com/anthropics/claude-code/issues/26923).
- **`settings.json`의 tool deny만 믿지 않음**: deny 규칙이 세션마다 다르게 적용됐다는 보고가 있습니다. 관련 이슈: [#8961](https://github.com/anthropics/claude-code/issues/8961). 그래서 훅 기반으로 구현했습니다.
- 플러그인 제거는 막을 수 없습니다. `/plugin uninstall` 또는 Codex의 plugin remove 명령으로 제거할 수 있습니다.
- 플러그인을 제거해도 개인 정책 파일은 남습니다. 기본 경로는 `~/.claude/plugins/guardrail/policy.json`이고, Codex 기본 경로를 썼다면 `~/.codex/plugins/guardrail/policy.json`입니다.

## License

MIT
