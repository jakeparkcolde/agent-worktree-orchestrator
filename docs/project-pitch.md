# Project pitch

## English

**One goal. One worktree. A clear path to cleanup.**

Agent Worktree Orchestrator (AWO) is an experimental toolkit for managing Git worktrees across repositories when working with AI coding agents. It connects a project registry and Git checks with Orca task creation, helping maintainers keep independent tasks isolated and inspect cleanup candidates before removing them.

Use AWO when you want to:

- Start independent Codex or Claude tasks through Orca from a configured Git base.
- Inspect branches and worktrees across registered projects.
- Check a worktree's Git state before review, then preview cleanup after its commits are contained in the configured base.

**Current scope:** v0.1.0 provides shell scripts and operating guidance. It does not automatically run the configured test, lint, or typecheck commands, create pull requests, or merge them. Worktree reuse and overlapping-file coordination are orchestrator responsibilities. The `finish` command reports Git state and flags selected risk-related paths; it is not a complete risk assessment or an enforced approval gate.

**Safety principle:** If safety cannot be proven from Git state, preserve the work. Cleanup defaults to dry-run. Removal requires a clean, non-primary worktree with no commits unique to the configured base, HEAD contained in that base, and no unpushed commits when an upstream exists. Applied cleanup uses non-force Git removal and branch deletion. High-risk changes require human approval under the project's operating policy.

Start with `merge_policy: manual` on a repository you can restore from remote backups. See the [Quick Start](../README.md#quick-start), [safety model](safety-model.md), and [architecture](architecture.md).

## 한국어

**하나의 목표, 하나의 워크트리, 명확한 정리 절차.**

Agent Worktree Orchestrator(AWO)는 AI 코딩 에이전트와 작업할 때 여러 저장소의 Git 워크트리를 관리하는 실험적 도구 모음입니다. 프로젝트 설정과 Git 상태 점검을 Orca 작업 생성에 연결해 독립적인 작업을 분리하고, 삭제 전에 정리 후보를 확인할 수 있도록 돕습니다.

다음과 같은 작업에 활용할 수 있습니다.

- 설정한 Git 기준 참조에서 Orca를 통해 독립적인 Codex 또는 Claude 작업 시작
- 등록한 프로젝트별 브랜치와 워크트리 상태 확인
- 리뷰 전 워크트리의 Git 상태 점검, 작업 커밋이 기준 참조에 포함된 뒤 정리 후보 미리 보기

**현재 범위:** v0.1.0은 셸 스크립트와 운영 지침을 제공합니다. 설정된 테스트·린트·타입 검사 실행, PR 생성, 병합을 자동으로 수행하지 않습니다. 기존 워크트리 재사용과 파일 수정 범위 조율은 오케스트레이터가 담당합니다. `finish`는 Git 상태를 보고하고 일부 위험 관련 경로를 표시하지만, 완전한 위험 평가나 승인을 강제하는 장치는 아닙니다.

**안전 원칙:** Git 상태로 안전함을 확인할 수 없다면 작업을 보존합니다. 정리는 기본적으로 미리 보기입니다. 삭제 대상은 주 작업 폴더가 아니고, 미커밋 변경과 기준 참조 대비 고유 커밋이 없으며, HEAD가 기준 참조에 포함되어야 합니다. 업스트림이 있다면 푸시하지 않은 커밋도 없어야 합니다. 실제 정리에도 강제 옵션 없이 Git 워크트리 제거와 브랜치 삭제를 사용합니다. 고위험 변경은 프로젝트 운영 정책에 따라 사람의 승인이 필요합니다.

원격 백업으로 복구할 수 있는 저장소에서 `merge_policy: manual`로 시작하세요. [한국어 README](../README.ko.md), [안전 모델](safety-model.md), [아키텍처](architecture.md)를 참고하세요.
