# 전체 작업판 연속 개선: ②·③·⑤ / 2026-09-29

## 승인 범위와 작업 위치

목표: 전체 작업판과 안전한 보관·재개 구현의 연속 개선.
시작 시 pwd=/Users/koldeumaegmini/orca/workspaces/agent-worktree-orchestrator/work-lifecycle,
branch=jakeparkcolde/work-lifecycle, git status clean을 확인했다.
승인된 ② 트리/거점 표, ③ 나중에·KST 예정일·다음 행동, ⑤ 아이디어/문맥 추천 CLI만 구현.
다른 worker/worktree 생성, 실데이터/설정/다른 저장소 변경, 커밋/병합/push를 하지 않았다.
코드/시험/문서는 이 워커가 작성하고 총괄이 리뷰 및 실데이터 이관을 맡는다.

## 구현

- 기본 board는 상태→프로젝트→작업 트리. 실제 형제 순서에 맞는 ├─/└─/│ 사용.
  지시 거점은 표로 분리. 작업 생략 없음, details는 ID/경로/브랜치 유지.
- 선택적 planning(later, scheduled_for, timezone)과 기존 next를 plan/update로 편집.
  KST YYYY-MM-DD의 실제 날짜 검증, 제거 옵션, add/import 옵션 제공.
  기존 state/identity/path/branch/사용자 확장 필드는 보존하고 이벤트를 추가.
- 분류: 완료 기록 우선, 다음 명시 예정일, 나중에/보관, 나머지 기존 연결 분류.
  예정/나중에/완료에서도 연결·Git 조회 경고를 배지로 표시, 중복 분류 없음.
  기존 board JSON state 의미는 유지하고 기록된 상태 recorded_state만 추가.
- 폴더 없는 아이디어 카드와 related_to 목표 표시.
- task suggest의 goal/current-task/intent/context로 reuse/separate/later/needs-choice와 근거 반환.
  auto는 휴리스틱 후보이며 apply 거부. 명시 intent를 확인해서 적용해야 한다.
  현재 A와 목표 B가 다른 자동 “이어서”는 needs-choice. 명시 reuse는 정확한 current-task 필요.
  explicit intent가 문맥/목표 유사성보다 우선. 추천 자체는 읽기 전용, LLM/네트워크 없음.
- separate/later apply는 새 작업 ID의 아이디어만 저장. 폴더/창 생성·전환 없음.
  기본 요청 키로 같은 저장 재시도 중복 방지. 내용이 달라지면 거부하고 plan 수정 안내.
  의도적인 별도 새 카드에는 다른 request-id. 실제 시작은 기존 task start 경로만 사용.
- docs/work-lifecycle.md, docs/request-entry.md와 AWO 전용 허브 템플릿 갱신.
  사용자/다른 프로젝트 지침 자동 설치 또는 기존 세션 자동 로딩/감시 주장 없음.

## 검증

합성 임시 Git + 기존 Orca CLI 대역과 순수 renderer/recommendation 시험만 사용했다.
- 계획/추천 10 tests OK (9.131초).
- renderer 15 tests OK (0.021초).
- 기존 request/start/lifecycle regressions 70 tests OK (32.175초).
- tests/test_cli.sh OK, make lint(shellcheck) OK, git diff --check OK.
- 새 테스트 단독 최초 실행에서 scripts import 경로 누락으로 ImportError가 발생해 시험 경로를
  보완했으며 이후 10개 전부 통과. 제품 결함이나 실제 운영 상태 오류가 아니다.
- 총괄 최종 검증: make test **264 tests / 175.853초 / OK**, CLI/project value/bash syntax 및 make lint 전부 통과.
  마지막 추가 test_planning 10개는 worker에서 통과했고 총괄도 별도 재확인 중이라고 전달했다.

계획 field 추가/수정/삭제, invalid date 무변경, 알려지지 않은 metadata 보존,
보관/완료 우선순위와 삭제된 old path 경고, 트리 형제 prefix와 작업 미생략,
auto preview/auto apply 거부/needs-choice 무저장/명시 reuse 무실행,
명시 separate 우선/related card/저장 재시도 중복 방지/새 request-id 및 start 연결을 검증했다.

## CLI 예

```bash
awo board
awo task add videos '을지로 변화' --related-to CURRENT_ID --later --next '자료 조사'
awo task plan videos TASK_ID --date 2026-10-04 --next '초안 비교'
awo task update videos TASK_ID --clear-date --clear-later --clear-next
awo task suggest videos --goal '을지로 변화' --current-task CURRENT_ID --context '새 주제로 따로 열어줘'
awo task suggest videos --goal '을지로 변화' --current-task CURRENT_ID --intent separate --apply
awo task start videos SAVED_ID --agent codex
```

## 한계 / 다음 단계

- 예정일은 계획 정보다. 알림/예약 실행/자동 감시는 미구현.
- 문맥 추천은 좁은 로컬 표현 규칙으로 일반 자연어 이해/의미 유사도 판단이 아니다.
  부정/질문/충돌 표현은 보수적 후보 처리하며 auto 자체에는 저장 권한이 없다.
- 연결 창은 실행 중/중요도 증거가 아니다. 계획 변경은 안전 상태나 보관 조건을 해결하지 않는다.
- 기본 재시도 키는 같은 프로젝트의 목표·현재 ID·intent 조합. 같은 키에서 옵션 변경은
  자동 덮어쓰지 않음. 명시 request-id는 프로젝트별로 관리하며 다른 키는 새 카드 생성 의도다.
- 기존 기록 손상은 자동 수리하지 않는다. 실데이터 이관은 총괄이 별도로 담당한다.

코드/시험 동결. 실행 중 서버/상주 프로세스 없음. Git staging/commit/merge/push 없음.
최종 검증 결과를 반영했다. 다음은 총괄이 명시 파일만 커밋하는 단계다. main 병합/push 없음.

## 총괄의 실제 계획 적용 확인 (worker가 실행하지 않음)

총괄 전달: 21gram의 `task-13130509a44844cd9e9dada404fb3eae`에
`task plan --date 2026-09-30`을 실제 적용했다. 기존 **id/goal/path/branch/identity/state/next**가
모두 동일하게 유지됨을 총괄이 검증했다. 이 워커는 실제 운영 task/config를 수정하지 않았다.

최종 상태: 승인된 ②·③·⑤ 구현/문서/표적 및 전체 검증 완료. 코드·시험 동결 유지.
전체 검증 전달 후 수정한 것은 결과/continuation 문서뿐이다. 커밋은 총괄이 명시 파일만
수행할 예정이며 이 워커는 staging/commit을 시도하지 않았다. main 병합/push 없음.

총괄 최종 확인: 계획 시험 10개/6.141초 통과. 실제 post-series 기본·상세 작업판의 나중에 표시 및 21gram 예정 목록 확인. 문맥 추천 separate 미리보기 전후 tasks.json 바이트 동일 확인. 아래 변경은 총괄이 명시 파일로 커밋하며 main 병합·push는 수행하지 않는다.
