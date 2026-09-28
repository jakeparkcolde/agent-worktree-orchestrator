# AWO 작업 수명주기 구현 결과 / 2026-09-29

## 목표와 승인 범위

2026-09-28 사용자 명시 승인: 작업판 → 할일/보관/재개/인계 → 중복 방지 → 실행 자원 →
정리 안내. 추가 승인: related independent task, stable ID start, 접두어 없는 명시 의도,
선택적 park --close. 작업폴더 한도 4는 coordinator가 등록 완료했다고 전달했다.
이 워커는 work-lifecycle에서만 구현하며 다른 agent/worktree 생성 금지.
production 상태/파일/프로세스 변경, Jev 실제 전송/키/trial 변경, push/merge 금지.
시험은 temporary Git + Orca doubles. 실제 기존 창을 닫거나 전송하지 않았다.

## 구현

- `scripts/awo_lifecycle.py`: 읽기 전용 board, task add/import/bind/show/start/park/resume/done/
  reconcile, resource list/check/suggest/register/release. 기본 board는 lightweight,
  --cleanup만 기존 audit.inspect 재사용. 오류 격리, Git timeout, 단일 세션 목록,
  미등록 작업/실제 WIP/복수 agent 표시, 한국어 텍스트.
- `scripts/awo_state.py`: 공용 project flock, timezone 이벤트, 생성 직전 durable intent,
  생성 성공 뒤 task 저장이 중단된 경우도 registration_pending으로 fail-closed.
- `scripts/awo_start.py`, `scripts/awo_request.py`: 공용 잠금, 기존 tasks.json 목록 호환,
  stable ID/이력 보존, full/short ref 정규화. 정상 사전 거부에는 pending 없음.
- `scripts/awo_audit.py`: 명령별 timeout과 fsync 저장. 보수적인 정리 판정 자체 유지.
- `bin/awo`: CLI 연결, 조회 시 bytecode 쓰기 방지.
- `tests/test_lifecycle.py`, `tests/test_lifecycle_regressions.py`: 실제 임시 Git과 Orca 대역.
- `docs/work-lifecycle.md`, `docs/request-entry.md`, `examples/awo-hub/AGENTS.md`, AWO 자체
  AGENTS/skill/README: 사용법, 거점과 worker 구분, 자연어 의도 계약. 외부 지침 미설치.

보관은 dirty/ignored를 포함한 폴더를 보존하고 고유한 JSON 인계 파일을 append-only로
저장한다. 새 프로세스 재개는 Git identity와 세션 exact handle을 검증한다. 기존 단일
작업자는 switch만 하며 새 턴 전송은 없다. 세션이 없을 때만 start로 새 세션을 만들고
목표/인계/next/validation을 직접 전달한다. related_to는 같은 프로젝트 ID 관계일 뿐,
configured base에서 독립 생성하며 기존 변경/대화를 복사하지 않는다.

명시 --close만 공식 tui-idle + rendered screen + 두 번의 identity/화면 검사와 인계/기록
저장 성공 후 정확한 단일 창을 닫는다. 자신의 창, busy/unknown/복수/draft/partial screen은
차단한다. draft 없는 Orca는 누락을 안전으로 보지 않고 --input-checked를 별도 요구한다.

## 검증 이력 (최종 결과는 아래 참조)

- 수정 전 실패 재현: 중단 후 재실행 차단 누락, full ref branch 불일치, 생성 전 중복 이름
  거부에도 pending이 남는 결함. 각각 실패 확인 후 수정했다.
- worker 직접: start + lifecycle 회귀 51 tests 통과 (10.892초, 이후 테스트 추가됨).
- worker 직접: 보관/기존 세션 연결/다수 및 unknown 차단/기본 작업판/사전검사 5 tests 통과.
- worker 직접: related 독립 base/dirty 보존, 한도 도달 무오염, close idle/busy 4 tests 통과.
- worker 직접: draft/partial screen/self 차단 및 idle close 2 tests 통과.
- worker 직접: 두 프로세스 resume 중복 방지, board 파일 bytes/mtime 불변,
  draft 없는 버전의 명시 input 확인 3 tests 통과.
- Python AST 구문 검사 및 git diff --check 통과.
- coordinator 전달: 초기 production read-only board 15 projects/40 worktrees, session known,
  errors 없음, 12.098초. 이는 lightweight 분리 전 관측이며 현재 성능 수치로 주장하지 않는다.
- coordinator 전달: 초기 lifecycle 테스트 46개 중 4개 실패, socket 오류 0. 전달된 fixture/
  기대값 문제를 수정했다. 실제 포트 bind 검증은 coordinator 환경에서 통과했다.
- 전체 make test/make lint는 coordinator가 직접 실행 중/결과 전달 예정. 아직 최종 통과로
  기록하지 않는다. worker 샌드박스는 socket bind를 거부해 권한 요청을 했으나 coordinator가
  취소했고 이후 권한 확대 없이 계속했다. 포트 시험은 삭제/skip하지 않았다.

## 한계와 보수적인 거부

- 외부 직접 Orca/agent 실행은 AWO 잠금 밖이다. 목록/재검증 이후 외부 입력의 TOCTOU를
  완전히 제거할 수 없다. 작업 시작/완료는 세션 연결만으로 주장하지 않는다.
- 창이 없다는 사실은 모든 background 프로세스 종료 증거가 아니다. processes-checked는
  사용자 확인이며 프로세스 kill/DB 변경/env 변경은 없다.
- related 링크는 같은 프로젝트만 지원. 자동 의미 병합이나 대화 복사 없음.
- 생성 결과가 없어 검증할 경로도 없으면 reconcile은 보수적으로 막는다. 무조건 force-clear
  없음. dispatch/tasks 손상은 수동 점검 필요. 메타데이터는 tamper-proof audit/백업이 아니다.
- 자원은 같은 설정을 쓰는 명시 등록끼리만 충돌 검사. 포트 제안은 예약이 아니며 실행 직전
  재검사 필요. DB namespace 별칭/다른 config/미등록 자원 전체 격리는 보장하지 않는다.
- 기본 board 정리 결과 UNKNOWN은 안전 판정 아님. --cleanup은 느릴 수 있으며 per-command
  timeout은 전체 시간 예산이 아니다. offline 프로젝트는 누적 대기 가능.
- 안전 종료는 전체 대화 저장을 보장하지 않는다. 필요한 결정은 인계에 먼저 저장해야 한다.
  Orca 1.4.211 draft 부재는 사용자 실화면 확인 없이는 close 불가.

## Git/프로세스/다음 단계

기준 HEAD d4d8c6d, branch jakeparkcolde/work-lifecycle. 다른 3개 worktree는 수정하지 않았다.
서버/상주 작업은 시작하지 않았다. 실행한 시험 subprocess는 종료됐다. 커밋은 아직 없음.
최종 상태: 구현 및 전체 검증 완료. worker의 Git 쓰기는 sandbox에 차단됐으며 재시도하지 않는다.
coordinator가 지정한 17개 파일의 커밋을 수행할 예정이다. push/merge/cleanup 없음.

## 최종 범위 확정과 후속 요구

사용자 마지막 요청은 운영 문서로 반영: 작업창≠worktree, 프로젝트·목표 이름 권장,
cd만으로 기존 세션 허용 경로가 확장되지 않을 수 있음, 정확한 WT 세션 시작 및
권한 오류 원문 진단 절차. 폴더 이동/chmod/신뢰 설정 변경은 하지 않았다.
추가 UI/창 배치/표시명 일괄 변경/전용 권한 진단 명령은 미구현이며 후속 범위다.
전체 검증은 coordinator가 현재 확정된 코드/시험으로 수행 중이다.

## 커밋 단계의 실제 차단 (2026-09-29)

worker가 명시 파일명으로 git add를 실행했지만 다음 오류로 실패했다. 스테이징/커밋 없음.

```text
fatal: Unable to create '/Users/koldeumaegmini/agent-worktree-orchestrator/.git/worktrees/work-lifecycle/index.lock': Operation not permitted
```

사용자 지시에 따라 권한 확대를 요청하지 않았다. coordinator 환경에서 다음 파일만
스테이징하고 커밋할 수 있다. 다른 worktree나 production runtime은 대상이 아니다.

```bash
git add AGENTS.md README.md README.ko.md bin/awo \
  scripts/awo_audit.py scripts/awo_request.py scripts/awo_start.py \
  scripts/awo_state.py scripts/awo_lifecycle.py \
  tests/test_lifecycle.py tests/test_lifecycle_regressions.py \
  docs/request-entry.md docs/work-lifecycle.md examples/awo-hub/AGENTS.md \
  skills/git-orchestrator/SKILL.md \
  docs/work-results/2026-09-29-work-lifecycle.md \
  docs/work-results/2026-09-29-work-lifecycle-continuation.md
git commit -m "feat: add safe task lifecycle, related work and explicit session parking"
```

위 커밋 명령은 아직 실행하지 않았다. coordinator의 최종 시험/커밋 결과가 오면 반영한다.

## 최종 검증 진행 업데이트

coordinator 전달: make lint 통과. make test는 실행 중이며 실패 표시 2개가 관측되어
traceback을 기다리고 있다. 아직 전체 시험 통과가 아니다.
커밋 실패는 WT 폴더 외 공유 Git 경로의 sandbox 접근 진단 사례로 운영 문서에 반영했다.
chmod 원인으로 단정하거나 모든 프로젝트 권한을 확대하지 않는다.

## 최종 결과 — AWO-LIFECYCLE-DONE

2026-09-29 coordinator가 동결된 코드/시험으로 최종 검증한 결과:

- `make test`: **240 tests / 173.409초 / OK**.
- `tests/test_cli.sh`: OK. `tests/test_project_value.sh`: OK. `bash -n`: OK.
- `make lint`: **shellcheck OK**.
- 앞선 화면 보존 검사 실패 2개 단독 재실행: **2/2 OK / 2.711초**.
  이전 전체 240개 실행(169.171초)의 2개 실패는 실행 중 fixture 변경으로 초기 import와
  최신 subprocess 코드가 섞인 시점의 결과다. 동결 후 단독 및 전체 재실행이 모두 통과했다.
- coordinator read-only production smoke: 기본 board **4.679초**, **15프로젝트/40WT**,
  기존 메타데이터 **19개 파일 SHA 불변**. 단일 관측이며 반복 성능/모든 파일 무변경을
  측정한 것은 아니다. 이전 12.098초는 cleanup 포함 옛 기본 동작이므로 조건이 다르다.
- coordinator 환경에서 40WT 경로의 존재/read/write/search `os.access` 모두 참.
  이는 해당 coordinator 환경의 관측이며 다른 세션의 sandbox/Git 공유경로 권한을
  보장하지 않는다. worker의 index.lock 거부 사실과 모순되지 않는다.

코드/시험 동결 유지. 최종 변경은 이 결과 문서와 continuation 문서뿐이다.
커밋 상태: worker는 add 실패 후 재시도하지 않음. coordinator가 위 **17개 명시 파일**을
커밋할 예정이며, 현재 worker가 확인한 새 커밋 해시는 없다. 커밋 완료라고 주장하지 않는다.
병합/푸시/운영 창 종료/운영 상태 변경/자동 cleanup 없음.

대표 사용 예:

```bash
awo board
awo task add videos '을지로 변화' --related-to EXISTING_ID --next '자료 조사'
awo task start videos NEW_ID --agent codex
awo task resume videos EXISTING_ID --agent codex
awo task park videos EXISTING_ID --next '결말 수정' --validation '자료 확인 완료'
```

명시적인 안전 창 종료는 문서의 --close/프로세스·입력 확인 절차를 따른다.
후속 범위: 창/분할 UI 배치, 표시명 일괄 변경, 전용 권한 진단 명령은 미구현.
추가 확장 없이 이번 승인 범위의 CLI 구현과 검증을 완료했다.
