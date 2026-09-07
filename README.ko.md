\
# Agent Worktree Orchestrator

> Git worktree + Orca + Codex/Claude를 여러 프로젝트에서 운영하기 위한 실험적 AI 개발 Control Plane

AWO는 AI 코딩을 많이 할수록 생기는 **Git 운영 문제**를 줄이기 위한 오픈소스 템플릿입니다.

핵심 문제는 코딩 자체보다 다음과 같은 운영에서 생깁니다.

- Worktree가 계속 쌓임
- 각 branch가 `main`에서 너무 멀어짐
- 여러 AI가 같은 파일을 동시에 수정함
- merge한 worktree가 남아 있음
- push되지 않은 commit을 잘못 지울 위험
- 사람이 branch/rebase/cleanup 관리에 시간을 씀

AWO는 이를 다음 구조로 바꿉니다.

```text
사람
  │
  │ Goal
  ▼
Agents Control Plane
  │
  ├─ projects.yaml
  ├─ AGENTS.md
  ├─ Git 안전 정책
  └─ Git Orchestrator Skill
  │
  ▼
Orca
  │
  ├─ 독립 Worktree
  ├─ Codex / Claude
  ├─ 테스트 / 리뷰
  └─ PR
  │
  ▼
Merge → 안전한 Cleanup
```

## 핵심 원칙

- 한 Worktree = 한 Goal
- 독립 작업은 repo의 base ref에서 시작
- 독립 작업은 Orca `--no-parent`
- 같은 작업은 기존 Worktree 우선 재사용
- Worktree는 1~3개 정도로 짧게 유지
- dirty / unique commit / unpushed commit이 있으면 자동 삭제 금지
- DB, 인증, 결제, production infra 등은 사람 승인
- `AGENTS.md`는 workspace 규칙, 실제 업무는 Goal/prompt

## 설치

```bash
cp projects.example.yaml projects.yaml
# 실제 프로젝트 경로로 수정
chmod +x bin/awo scripts/*.sh
./bin/awo doctor
```

## 상태 확인

```bash
./bin/awo status myapp
```

## 작업 시작

```bash
./bin/awo start myapp login-fix codex \
  "로그인 간헐 오류를 수정하고 회귀 테스트를 추가"
```

## Merge 전 검사

Worktree 안에서:

```bash
/path/to/awo/bin/awo finish
```

## Cleanup 미리보기

```bash
./bin/awo cleanup myapp
```

## 안전한 대상만 실제 정리

```bash
./bin/awo cleanup myapp --apply
```

처음에는 반드시:

```yaml
merge_policy: "manual"
```

로 시작하는 것을 권장합니다.

자세한 설명:

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/safety-model.md`](docs/safety-model.md)
- [`docs/orca-integration.md`](docs/orca-integration.md)
- [`docs/usage.md`](docs/usage.md)

## 라이선스

MIT
