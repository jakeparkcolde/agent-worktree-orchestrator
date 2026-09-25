# Jev 라우팅 작업 결과 / 인계 — 2026-09-25

## 목적과 최신 지시

터미널 접수에서 Jev로 프로젝트·기존 목표·요청 유형 후보를 추천하여 AWO와 총괄 AI의
판단을 보조한다. 기본 규칙과 실행 권한은 보존한다. 사용자 지시에 따라 배정된
`jev-routing`에서 직접 구현·검증·문서·로컬 커밋만 수행하며 추가 작업자/워크트리는 만들지 않는다.
병합·push·다른 worktree 수정·기존 사용자 설정/키 변경은 금지다.
키는 환경변수 우선, 다음 전용 파일을 안전하게 읽는다. 실제 키 파일을 읽거나 API를
호출하는 일은 root만 수행한다. 워커의 키 테스트는 임시 파일과 `Path.home()` mock을 쓴다.
실제 HOME 환경변수를 바꾸지 않는다. UTF-8 한국어 주석/빈 줄을 지원하되 단일 할당만 허용한다.

## 작업 위치와 상태

- 작업 경로: `/Users/koldeumaegmini/orca/workspaces/agent-worktree-orchestrator/jev-routing`
- 브랜치: `jakeparkcolde/jev-routing`
- 기준: `origin/main`, 시작 SHA `853f9da86fd7b217e31dcbbff81725f2446f0762`
- 버전 파일: `0.2.0` 유지. 기능은 CHANGELOG Unreleased에 기록.
- 레지스트리: `AWO_PROJECTS_FILE=/Users/koldeumaegmini/agent-worktree-orchestrator/projects.yaml`
- 시작/최종 검사에서 작업 공간 3개. primary와 `disk-space-watch`는 수정하지 않았다.
- 기존 `jev-routing`을 `awo request --worktree ... --apply`로 현재 목표에 연결했다.
  Git 공용 디렉터리의 `awo/tasks.json` 연결만 기록했고 projects.yaml은 바꾸지 않았다.
- 현재 작업의 로컬 커밋은 이 문서를 포함하는 `feat: add opt-in Jev routing advice` 커밋이다.
  최종 SHA는 완료 메시지와 `git log -1`로 확인한다. push/PR/merge/cleanup은 수행하지 않는다.

## 구현

- `scripts/awo_advice.py`: 외부 전송 allowlist, 검증된 목표의 opaque ID/로컬 경로 매핑,
  bounded Choice API, 고정 모델 `jev-1.13.0`, 5초 socket timeout, 무재시도/무redirect,
  폐쇄형 응답 검증, 상태/오류 코드와 안전한 키 로딩.
- `scripts/awo_request.py`: opt-in `--advise none|jev`와 별도 `advisory` 출력 추가.
  기존 decision 객체와 인수는 모델로 변경하지 않는다. 기본 호출, 명확한 규칙,
  apply 경계에서는 키를 읽거나 외부 호출하지 않는다. 한도 차단의 추천도 차단을 풀지 않는다.
- 프로젝트 후보는 key/aliases/선택적 description, 목표 후보는 검증된 ID/제목만 전송한다.
  로컬 경로·브랜치·diff·파일명/내용·전체 대화는 전송하지 않는다.
- 환경변수 > `~/.config/awo/jev.env`. 현재 사용자 소유·일반 파일·정확히 0600·마지막
  경로 요소 symlink 거부. UTF-8 주석과 빈 줄, 정확히 하나의 `TYPESAFE_API_KEY=` 허용.
  쉘 평가·자동 설정 변경·키값/파일본문/원격 오류 본문 출력 없음.
- 모델의 프로젝트/기존 목표/요청 유형 추천만 제공한다. 자유 목표 생성 없음.
  `none/ambiguous/multiple` 후보와 에러를 구별한다. 요청 유형의 모호함은 `unclear`로 통일.
  복수/불명확/업무 아님 또는 애매한 후보는 `shadow_advisory/request_needs_review`로
  후보를 보존하며, 전체 요청이 기존 목표에 맞는지 지시한다. 자동 실행 경로는 없다.
- `tests/test_advice.py`, `tests/test_jev_key.py`: 규칙/전송/실행 경계·에러·키 로더 회귀테스트.
- `tests/evaluate_jev.py`, `tests/fixtures/jev-korean-cases.json`: 명시적 replay/live를 분리한
  공개 합성 한국어 12건 평가. replay는 실제 모델 평가를 가장하지 않는다.
- 사용 절차와 롤백: `docs/jev-advice.md`. 진입 문서/README/도움말/설정 예제 업데이트.

## 검증과 발견한 실패

최종 검사 결과:

- `make test`: **137개 Python 테스트 통과**, CLI/설정 파서/Bash 문법 검사 통과.
  최종 로그: `/tmp/awo-jev-verified-tests.log`.
- `make lint`: shellcheck 통과. `git diff --check`: 통과.
- `python3 tests/evaluate_jev.py --replay --limit 12`: 12건 스키마 replay 통과.
  `/tmp/awo-jev-replay-final.json`은 fixture_replay이며 live 검증이 아니다.
- 마지막 `git fetch origin` 뒤 기준 대비 ahead/behind는 커밋 전 0/0이었다.
  기능 커밋 후 1개 로컬 커밋이 앞선다. 구성된 test/lint 명령을 모두 실행했다.
- 테스트/평가 프로세스 종료. 새 서버·감시·백그라운드 작업은 없다.
- 실패 상태나 구현 blocker는 남지 않았다. 최종 diff/병합 판단은 root의 후속 작업이다.

- 초기 전체 `make test`: 132개 Python 테스트와 CLI/설정 파서/Bash 문법 검사 통과.
- `IncompleteRead`를 `response.read()`에서 발생시켜 정상 JSON과 기존 action 보존을 검증했다.
  모든 `HTTPException`은 안전한 `network_error`로 변환한다.
- 실제 키 없이 UTF-8 주석 템플릿을 재현하여 `key_file_format` 실패를 먼저 확인했다.
  로더 수정 후 키 로더 6건 통과. 중복·다른 변수·쉘 구문·소유자/권한/symlink 검사는 유지.
- 워커는 실제 사용자 키를 읽지 않았고 live API 호출도 실행하지 않았다.

## root가 제공한 최초 live 탐색 결과

root가 별도 실행한 공개 한국어 연결 예제 1건 성공(0.803초, research)을 보고했다.
이어 제공한 `/tmp/awo-jev-live-20260925.json`을 읽어
`docs/evaluations/2026-09-25-jev-initial.json`에 그대로 보존했다. 이 파일에는 공개
합성 fixture의 결과만 있고 키/실제 프로젝트 경로는 없다.

12건의 관측 시간은 7.505초, 기대 라벨 일치는 프로젝트 12/12, 기존 목표 11/12,
요청 유형 11/12였다. `ambiguous`의 유형 중복과 `mixed-intent`의 부분 목표 일치가
불일치 원인이었다. 이것은 12개 탐색 샘플이며 모델 정확도·성능 비교·자동 라우팅
검증을 의미하지 않는다. 원본의 `is_accuracy_measurement`는 라벨 대조 모드 표시다.

그 후 유형 선택지 중복 제거, 전체 요청 적합 instruction, 검토 필요 상태와 회귀테스트를
추가했다. **기대 라벨은 변경하지 않았다.** 초기 원본은 이전 스키마이며 현재 구현의
live 재검증 자료로 간주하지 않는다.

root의 최종 CLI 연결 확인: 사용자 키 파일 수정 없이 기본 요청은
`needs_worktree + disabled/not_requested/source=none`(5.379초), 추천 요청은
동일한 `needs_worktree + suggested/candidate_recommendation/source=live`,
`model=jev-1.13.0`, `execution_authority=false`(6.739초)였다. root가 보고한 단일 관측이며
성능 벤치마크가 아니다. 워커의 실행으로 표현하지 않는다.

수정 후 root의 공개 합성 12건 결과 `/tmp/awo-jev-live-retest-20260925.json`은
`docs/evaluations/2026-09-25-jev-retest.json`에 별도 원본으로 보존했다.
관측 7.802초, 스키마 12/12, 프로젝트/기존 목표/요청 유형 각 12/12 기대 라벨 일치.
최초 결과를 보고 보완한 뒤 **같은 탐색 샘플**로 재검증한 것이므로 holdout 정확도,
일반 한국어 성능이나 자동 실행 가능성을 주장하지 않는다. 별도 wiki 구현은 범위에 없다.

## 한계 / 남은 확인

- confidence는 정확도나 승인 확률이 아니다. 자동 라우팅·자동 실행은 없다.
- 비밀/절대경로 패턴 검사는 보조 수단이다. 요청문·메타데이터에 비밀/고객 본문을
  넣지 않는 계약을 유지하며 민감한 원문은 총괄이 비식별 요약 후 opt-in해야 한다.
- API 직전/직후 후보를 검증해도 적용까지 상태가 바뀔 수 있다. 총괄은 기존 목표와
  경로/변경을 다시 검토하고 명시적 `--project/--goal/--worktree`로 수동 적용한다.
- timeout은 socket 기준이며 DNS/OS 지연을 포함한 엄격한 wall-clock deadline은 아니다.
- 실제 프로젝트 설명과 사용자의 키 파일은 수정하지 않았다. 최종 병합은 root 검토 대상이다.

## 복사해서 이어갈 프롬프트

```text
Jev 라우팅 최종 검토를 이어가세요.
작업 공간 /Users/koldeumaegmini/orca/workspaces/agent-worktree-orchestrator/jev-routing,
브랜치 jakeparkcolde/jev-routing입니다. AGENTS.md와
 docs/work-results/2026-09-25-jev-routing.md, docs/jev-advice.md를 읽으세요.
AWO_PROJECTS_FILE은 /Users/koldeumaegmini/agent-worktree-orchestrator/projects.yaml입니다.
추가 작업자/워크트리 생성, main/다른 worktree 수정, push/merge/키 수정은 하지 마세요.
로컬 커밋과 최종 diff를 검토하고, 초기 live 탐색 자료와 변경 후 검증을 구분하세요.
키를 출력하지 마세요. 실제키 접근/live 호출은 root의 명시적인 사용자 승인 범위에서만
진행하고 공개 합성 예제를 사용하세요. 추천은 항상 advisory이며 action을 변경하지 않습니다.
후보 재검증 후 수동 --project/--goal/--worktree 선택 절차와 apply 경계를 확인하세요.
```
