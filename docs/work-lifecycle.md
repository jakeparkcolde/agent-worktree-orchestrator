# CLI 작업판과 작업 인계

고정된 `AWO_PROJECTS_FILE`과 CLI 절대 경로를 사용한다. 모든 명령은 로컬 처리이며
새 기능은 LLM/Jev를 호출하지 않는다. 작업 목표와 인계에는 비밀을 넣지 않는다.

## 작업판 (조회만)

```bash
awo board
awo board --project app --json
awo board --cleanup --json
```

기본 조회는 Git 상태/경로 identity/세션을 읽는다. fetch나 파일 저장을 하지 않는다.
미등록 폴더·삭제된 경로·오프라인 프로젝트·손상된 기록도 숨기지 않는다.
터미널 목록은 한 번 조회해 재사용한다. 조회 실패와 불완전한 목록은 미확인으로 표시한다.
Git 명령별 timeout은 15초다. 목록 전체의 시간 제한은 아니므로 오프라인 프로젝트가
여럿이면 누적 대기할 수 있다. 네트워크/API 호출은 없고 로컬 Orca 조회만 사용한다.

기본 정리는 **미검사 (안전 판정 아님)**이다. `--cleanup`에서 기존 audit.inspect의
판정을 메모리 사본으로 수행하고 관찰 기록도 저장하지 않는다. 상세 검사는 느릴 수 있다.
정리 안내 명령은 미리보기이며 자동으로 `--apply`를 붙이지 않는다.
확인된 연결 세션 수는 미등록 작업을 포함한다. 3개 초과와 같은 경로의 복수 작업자를
경고한다. 이는 권장 수이며 물리 worktree 한도/보관 수와 별개다.

## 할일 → 명시 연결 → 보관 → 새 프로세스 재개

```bash
awo task add app '알림 누락 수정' --next '실패 재현'
awo task show app
# 할일은 폴더를 만들지 않는다. 기록된 목표로 미리보기 후 명시 시작한다.
awo request 'app 작업' --project app --goal '알림 누락 수정'
awo request 'app 작업' --project app --goal '알림 누락 수정' --apply --agent codex
# 기존 폴더가 있으면 생성 대신 연결한다.
awo task bind app task-ID --worktree /exact/existing/path
# 미등록 폴더와 목표를 함께 가져오는 명시적 등록
awo task import app '기존 작업 목표' --worktree /exact/existing/path
awo task park app task-ID --next '실패 테스트 수정' --validation '재현 1개 실패'
# 실제로 관련 프로세스가 남아 있지 않음을 별도 확인한 경우만:
awo task park app task-ID --processes-checked --next '실패 테스트 수정'
# 새 CLI 프로세스에서도 기존 경로를 검증해 연결
awo task resume app task-ID --agent codex
awo task done app task-ID --processes-checked --validation 'make test 통과'
```

stable ID로 선택한다. 기존 tasks.json 목록 형식과 goal/path/branch/identity 필드를
유지한다. 레거시 항목은 결정적인 `legacy-...` ID로 읽고 다음 수정에 영속화한다.
새 항목은 UUID ID다. 이벤트와 timezone 포함 시각/스키마 버전을 각 항목에 저장한다.
잠금과 fsync 후 원자적 replace로 기록한다. 같은 목표의 request는 기존 ID와 이력을 유지한다.

보관/완료는 파일·프로세스·브랜치를 변경하지 않는다. 터미널이 없다는 사실만으로 외부
서버까지 종료됐다고 주장하지 않는다. 완전한 세션 목록에서 해당 창이 없고 사용자가
`--processes-checked`로 별도 확인했을 때만 보관/완료 상태가 된다. 실행 중/미확인 창이나
미확인 dispatch가 있으면 **확인필요**이며 인계 자료는 그래도 저장된다.
보관은 백업/압축이 아니다. dirty/ignored를 포함한 작업폴더 자체를 그대로 보존한다.

인계는 Git common dir의 `awo/handoffs/ID/고유시각-UUID.json`에 append-only로 저장한다.
이전 노트를 덮어쓰지 않는다. 목표, 다음 행동, 검증 결과/사용자 제공 출처, 연결 identity,
보존 경계와 복사 가능한 continuation 명령을 담는다. metadata를 잃으면 복구 보장이 없다.

재개는 기존 Git identity와 브랜치를 재검증한다. 경로/브랜치 교체 시 자동 연결하지 않는다.
`--agent none` (기본값)은 경로 선택만 하며 워커 연결/턴 시작을 주장하지 않는다.
`--agent codex|claude`에서는 기존 창이 정확히 1개이고 terminal show의 경로, branch
(full/short ref 정규화), handle, connected, agentIdentity가 모두 일치할 때만 정확한
handle로 terminal switch한다. 기존 창에는 새 프롬프트/턴을 보내지 않는다.
창이 없으면 기존 start 경로로 새 세션을 만들며 목표·인계 경로·현재 다음 행동·검증
결과/출처를 프롬프트에 직접 넣는다. 복수 창/unknown/다른 agent는 차단한다.
세션 연결 확인과 실제 작업 시작/완료는 구별한다.

## 실행 소유와 중단 복구

start/request/resume는 Git common dir의 동일한 `awo-dispatch.lock`을 쓴다.
추가로 tasks.lock으로 기록을 직렬화한다. 잠금은 비차단이며 다른 실행이 있으면 거부한다.
생성 사전검사가 끝나고 외부 생성 직전에만 `awo/dispatch.json`에 pending을 영속 저장한다.
중복 이름/한도/base 사전 거부는 pending을 만들지 않는다. 생성 timeout·중단·결과 미확인은
다음 실행을 막는다. PID 만료나 시간이 지났다는 이유로 소유를 자동 해제하지 않는다.

```bash
# 생성 결과를 직접 확인하고 기존 폴더를 정확한 목표로 등록한 뒤
awo task import app '중단된 실행의 정확한 목표' --worktree /verified/path
awo task reconcile app task-ID --processes-checked
awo task resume app task-ID --agent codex
```

reconcile은 검증된 기존 경로/목표와 완전한 세션 목록, 사용자 프로세스 확인을 요구한다.
생성 결과가 없어 경로를 검증할 수 없거나 기록이 손상되면 자동 복구하지 않는다.
Orca 상태와 metadata를 수동 점검해야 한다. 무조건적인 force-clear 명령은 제공하지 않는다.
외부에서 직접 실행한 Orca/agent와 CLI 사이의 경쟁은 이 잠금으로 완전히 차단할 수 없다.

## 실행 자원

```bash
awo resource list
awo resource suggest port 4800
awo resource check port 4800
awo resource register app task-ID port 4800
awo resource register app task-ID output /absolute/output/path
awo resource register app task-ID db local/server/database/schema
awo resource release app task-ID port 4800
```

설정 파일 옆 `.awo-resources.json`에서 프로젝트 간 등록을 함께 잠그고 원자적으로 저장한다.
포트는 중복 등록과 현재 bind 가능 여부를 확인한다. 제안은 예약이 아니며 실행 직전 다시
확인해야 한다. 출력 경로의 부모/자식 중첩도 충돌한다. DB 값은 서버/DB/namespace를
일관된 문자열로 명시한다. 다른 설정 파일을 사용하는 AWO와 미등록 자원은 보호 범위 밖이다.
release는 기록만 해제한다. 프로세스 kill/DB 변경/출력폴더 생성/env 파일 변경은 없다.
보관/완료만으로 자원을 자동 해제하지 않는다.

## 거점과 정리

[AWO 전용 템플릿](../examples/awo-hub/AGENTS.md)은 검토 후 수동 설치한다.
거점은 배분/검증 역할이고 구현은 정확한 경로에 연결된 독립 워커에서 한다.
agent none은 worktree-only이며 거점 직접 구현 fallback을 허가하지 않는다.

보관/완료는 정리 허가가 아니다. 기존 `awo cleanup app --worktree PATH` 미리보기와
명시적인 `--apply`만 정리를 수행한다. 기존 안전 gate가 재검사되고 branch는 보존된다.
unknown은 안전으로 승격하지 않는다. 자동 삭제/종료/커밋/병합/발행은 없다.

## 관련된 독립 주제와 명시적인 창 닫기 (추가 승인 범위)

```bash
awo task add videos '을지로 변화' --related-to task-성수동ID --next '자료 조사'
# 나중에 할 아이디어라면 여기서 끝. 별도 창을 열라는 명시적 요청일 때만:
awo task start videos task-을지로ID --agent codex
awo task resume videos task-성수동ID --agent codex
# 작업을 접으라는 명시적 요청이고 보존/프로세스 확인이 끝났다면 거점에서:
awo task park videos task-성수동ID --close --processes-checked \
  --next '결말 구성 보완' --validation '자료 확인 완료, 영상 검증 미완료'
```

`--related-to`는 같은 프로젝트의 정확한 stable ID만 받는다. 다른 작업과 상태/다음행동/
파일/세션을 공유하지 않는다. 작업판은 관련 ID와 목표를 함께 표시한다. `task start`는
미연결 할일을 configured base와 `--no-parent`로 생성한다. 이미 연결된 ID면 resume한다.
물리 한도를 지키고 기존 미완료 변경이나 전체 대화를 자동 복사하지 않는다.
Jev 의미 유사성으로 명시적인 독립 주제를 기존 작업 재사용으로 변경하지 않는다.

기본 park는 창을 닫지 않는다. 명시적인 `--close`는 다음 행동/검증/프로세스 확인이
필요하다. 정확한 단일 창의 경로·브랜치·connected·agent identity를 검증하고 Orca
`terminal wait --for tui-idle` 성공과 `terminal read --screen`의 실제 화면 및 빈 draft를
요구한다. 최근 출력 시각만으로 idle을 추정하지 않는다. 인계와 작업 기록의 디스크 저장
성공 후 동일 검사를 다시 수행하고 화면이 바뀌지 않았을 때만 정확한 handle을 닫는다.
현재 명령을 실행하는 자신의 창, 실행 중/unknown/복수 창, 화면 fallback/미전송 입력,
저장 실패는 닫지 않는다. close 실패/결과 미확인은 확인필요로 남는다.

닫기는 UI 세션에만 명시 요청하며 force/kill/send/자동 커밋/worktree 삭제를 하지 않는다.
다른 프로세스의 완전한 부재나 동시 외부 입력을 원자적으로 보장할 수는 없다. 그래서
프로세스 확인을 사용자가 명시하고 두 번 재검증한다. 화면 본문은 인계에 복사하지 않는다.
닫힌 창 재개는 새 세션에 저장된 목표/다음행동/검증을 전달한다. 전체 대화 복원은 보장하지 않는다.

운영 지침의 자연어 매핑:

- “이거 더 고치자”: 같은 작업 ID 유지, 필요할 때 resume.
- “비슷하지만 다른 주제로 따로 열어줘”: related add + 새 ID start.
- “나중에 해보자”: add만, 창 생성 없음.
- “성수동으로 돌아가자”: 기존 정확한 ID resume.
- “여기까지 접어두자”: 다음 행동/검증을 기록하고 안전 조건이 확인되면 park --close.

명확한 의도는 승인 범위에서 실행하고 애매한 대상/의도만 확인한다. 이는 AWO 자체
스킬/템플릿 지침이며 다른 프로젝트 AGENTS나 전역 파일을 자동 수정하지 않는다.
이미 실행 중인 모든 세션에 지침이 자동 로드됐다고 주장하지 않는다.

Orca 1.4.211처럼 `draft` 필드가 없는 버전은 필드 누락을 빈 입력으로 인증하지 않는다.
이 경우 호출자가 실제 화면에서 미전송 입력이 없음을 별도로 확인한 뒤 `--input-checked`를
추가해야 한다. `draft`가 실제로 비어 있지 않으면 이 옵션으로 우회할 수 없다.
화면 source가 screen이 아니거나 handle 불일치, truncated/limited인 경우도 닫지 않는다.
전체 대화/화면의 영속 보존은 이 기능이 보장하지 않는다. 필요한 결정은 next/validation과
프로젝트 파일에 먼저 저장해야 한다.

## 작업창과 폴더, 접근 권한 진단 (운영 안내)

**작업창/분할 pane은 세션이고, worktree는 Git 작업폴더다.** 같은 worktree에 여러 창이
연결될 수 있으며 창을 닫아도 worktree와 파일을 삭제하는 것은 아니다. 반대로 폴더를
선택하거나 다른 폴더로 cd했다고 새 세션이 만들어지거나 작업 소유가 바뀌는 것도 아니다.
등록 경로는 환경에 따라 다르지만 이번 운영 관측은 주로
`~/orca/workspaces/<repo>/<task>`다. 표시명 `main`만으로 프로젝트나 목표를 식별하지 않는다.
창/작업명은 `프로젝트 · 구체적 목표`처럼 구분하고 stable task ID와 정확한 경로를 함께
확인한다. root main에 여러 세션이 있다면 작업판의 복수 작업자 경고를 확인한다.
AWO는 이름을 자동 변경하거나 기존 창/분할 배치를 재배치하지 않는다.

거점 세션에서 다른 프로젝트로 **cd만 하면 기존 세션의 허용 경로/샌드박스 권한이 자동으로
확장되지 않을 수 있다.** 대상 프로젝트의 정확한 worktree에서 독립 세션을 시작하거나
검증된 기존 세션을 resume한다. 창의 표시명 대신 반환된 경로·branch·handle을 확인한다.

“폴더 접근 거부”가 나오면 다음 순서로 진단한다.

1. 오류 원문, 실행한 명령/앱 동작, 현재 세션의 정확한 worktree 경로를 기록한다.
   비밀·토큰·고객 본문은 제외한다. OS 권한 오류인지 agent sandbox 오류인지 추정으로 단정하지 않는다.
2. `awo board --project KEY --json`, `awo task show KEY ID`에서 등록 path/branch와 실제
   세션 바인딩을 대조한다. 폴더 존재/오타/삭제된 경로/다른 프로젝트 main 여부를 읽기 전용으로 확인한다.
3. 세션에 주어진 writable roots/허용 경로와 대상 worktree를 대조한다. 단순 cd로 범위가
   바뀌었다고 가정하지 말고 정확한 대상 worktree에 바인딩된 세션에서 다시 확인한다.
4. 정확한 경로의 새/기존 세션에서도 같은 오류가 나면 오류 원문과 재현 단계를 보존하고
   해당 앱/OS/sandbox 정책을 별도로 진단한다. 원인 확인 없이 chmod, 신뢰 설정 변경,
   폴더 이동, 샌드박스 확대를 수행하지 않는다.

이번 범위에서 추가 UI, 창/분할 배치 자동화, 프로젝트 main 표시명 일괄 변경,
전용 권한 진단 명령은 **미구현**이다. 기존 폴더 이동/chmod/신뢰 설정 변경도 수행하지 않았다.

worktree 폴더가 쓰기 허용돼 있어도 **공유 Git 메타데이터 경로**가 허용 범위 밖이면
`git add`/`git commit`이 실패할 수 있다. 이번 워커의 실제 오류는 work-lifecycle 폴더가
아닌 원본 저장소의 `.git/worktrees/work-lifecycle/index.lock` 생성 거부였다.

```bash
git rev-parse --git-dir --git-common-dir
```

위 읽기 전용 명령으로 해당 세션의 실제 Git 디렉터리와 공용 Git 디렉터리를 확인하고,
세션 sandbox의 writable roots와 대조한다. 이번 관측은
`/Users/koldeumaegmini/agent-worktree-orchestrator/.git/worktrees/work-lifecycle`와
`/Users/koldeumaegmini/agent-worktree-orchestrator/.git`였다. 필요한 **정확한 경로**의
접근 정책을 진단하며 chmod 문제라고 단정하지 않는다. 권한이 있는 coordinator가
명시 파일만 커밋하는 방법도 있다. 이번 구현은 모든 프로젝트의 권한 확대나 sandbox/
신뢰 설정 자동 변경을 제공하지 않는다.

## 구조화된 텍스트 작업판

```bash
awo board                         # 목적별 그룹과 요약
awo board --project videos        # 조회 범위 집계와 전체 환경 집계를 구분
awo board --details                # 긴 ID, 절대경로, 브랜치, 정리 안내
awo board --cleanup --details      # 상세 정리 안전 판정 포함
awo board --json                   # 기존 JSON 계약 유지
```

기본 텍스트는 열린 작업 / 이어갈 작업 / 아이디어 / 보관·완료 / 확인할 연결 / 지시 거점으로
묶고 빈 그룹은 생략한다. 창이 연결됐다는 것은 작업 실행 중이라는 뜻이 아니다.
정상 Git 연결에 남아 있는 예전 확인필요 상태나 미기록 상태를 연결 오류로 분류하지 않는다.
폴더 identity 검증 실패, 세션 조회 미확인, 복수·미확인 작업자 연결은 따로 표시한다.
미등록 작업은 목표를 추정하지 않고 폴더 basename을 보조 라벨로 표시한다.

상단 프로젝트·실제 폴더·연결된 agent 수는 조회 범위의 집계다. 별도의 **전체 환경**
세션 수와 경고에는 프로젝트 필터 밖의 세션도 포함된다. 기본 화면은 긴 ID·절대경로·
cleanup 명령을 숨기며 --details로 확인한다. 터미널 폭에 맞춰 한국어 목표와 다음 행동을
줄바꿈한다. 렌더러는 기존 조회 결과만 사용하며 추가 세션/파일 조회나 상태 저장을 하지 않는다.

기본 화면에서는 자동 생성된 다음 행동 안내를 그룹당 한 번으로 합치고, 사용자가 남긴
next만 작업 아래 표시한다. 상태 미기록/확인필요 기록 설명도 그룹 공통 안내로 표시한다.
이어갈 작업의 반복적인 '연결된 창 없음'은 생략한다. 지시 거점은 프로젝트명과 연결된
agent/창 수를 표시한다. 완료 작업은 기본 텍스트에서 숨기며 --include-done으로 포함한다. --details에서는 자동 안내,
상태 기록, 거점 경로 등 세부 정보를 다시 확인할 수 있다.

## 작업판의 제안

텍스트 작업판 끝의 **지금 할 만한 일**은 기존 조회 결과만으로 근거와 행동을 최대 3개
표시한다. 조회 실패·미확인 실행, 같은 폴더의 복수 agent, identity 검증 실패, 많은 연결,
열린 작업의 사용자 next 누락, 미등록 목표 순서다. 연결이 많으면 중요도를 대신 정하지 않고
오늘 집중할 한 작업을 직접 선택하고 나머지 next를 기록한 뒤 보관을 검토하도록 안내한다.
보관 안전성은 별도 확인 대상이다. 정상 빈 결과에는 불필요한 제안을 표시하지 않는다.

프로젝트 이름이 붙은 제안은 조회 범위 안의 작업을 근거로 한다. 필터 밖의 연결·복수
agent는 **전체 환경**으로 명시하며 경로에서 프로젝트명을 추측하지 않는다. 세션 조회가
미확인이면 연결 수나 복수 여부를 판단하지 않는다. 창 연결은 실행 여부나 중요도 증거가 아니다.
이 제안은 순수 결정 규칙이며 추가 LLM·네트워크·파일/세션 조회·자동 수정이 없다.
삭제·강제 종료를 권고하지 않는다. `--json`에는 제안을 추가하지 않아 기존 계약을 유지한다.

2026-09-29 후속 검증: 순수 renderer/advice 시험 10개와 기존 CLI 시험 통과.
시험은 우선순위/상한, 실제 복수 agent 수, 미확인 분기, 프로젝트 필터, 빈 결과,
사용자 next 누락, JSON 유지 및 입력 불변을 확인한다. 운영 상태는 변경하지 않았다.

복수 작업자 연결은 폴더마다 제안 칸을 쓰지 않고 한 제안으로 묶는다. 작업자 수가 많은
순서로 최대 3곳의 프로젝트명·실제 수를 표시하고 나머지는 '외 N곳'으로 요약한다.
필터 밖 경로는 프로젝트명을 추측하지 않고 '범위 밖 프로젝트 미확인'으로 표시한다.
작업폴더 연결 검증 실패도 조회 범위의 전체 개수와 대표 프로젝트를 한 제안으로 묶어,
중복 확인·연결 실패 확인·집중 작업 선택을 함께 볼 수 있도록 한다. 조회 실패/미확인 실행은
계속 우선한다. 조언에는 작업자·작업폴더 연결·다음 행동이라는 표현을 사용한다.
집계 조정 후 순수 시험 11개 및 기존 CLI 시험 통과. 실제 운영 조회 없이 합성 자료로 검증했다.

오래된 경로에서 작업폴더 연결 검증 실패와 Git 상태 조회 실패가 함께 나타나면 연결 실패에만
집계한다. 일반 조회 오류·미확인 실행·전체 세션 조회 미확인은 최우선 제안 한 칸으로 묶는다.
오래된 경로 8개 사례와 여러 프로젝트의 일반 오류/실행 미확인 사례를 실패 재현 후 수정했고,
순수 시험 13개·CLI 검사·lint가 통과했다. 이번 후속 수정에서 스테이징 영역은 변경하지 않았다.

## 계획 정보와 아이디어 (2026-09-29 추가)

기본 작업판은 **상태 → 프로젝트 → 작업** 트리다. 마지막 형제만 `└─`, 나머지는 `├─`이고
연속되는 부모 가지는 `│`로 유지한다. 거점은 프로젝트별 연결 작업자/창 수 표로 분리한다.
완료를 제외한 모든 작업을 표시하며, `--include-done`으로 완료도 포함한다. `--details`에 정확한 ID·경로·브랜치를 유지한다.

```bash
awo task add videos '을지로 변화' --related-to CURRENT_ID --later --next '자료 조사'
awo task import videos '기존 주제' --worktree /exact/path --date 2026-10-03
awo task plan videos TASK_ID --date 2026-10-04 --next '초안 비교'
awo task update videos TASK_ID --later --next '다음 회의에서 검토'
awo task plan videos TASK_ID --clear-date --clear-later --clear-next
```

`plan`과 `update`는 같은 계획 수정 동작이다. 예정일은 **KST YYYY-MM-DD** 날짜이며
유효한 달력 날짜만 받는다. 시각/상대 날짜/다른 시간대 표기는 받지 않는다. 과거 날짜도
기록할 수 있다. `--later`/`--clear-later`, `--date`/`--clear-date`, `--next`/`--clear-next`는
각각 상호 배타적이다. 지정하지 않은 값과 기존 사용자 메타데이터는 보존한다.

계획은 선택적인 `planning: {later, scheduled_for, timezone: "Asia/Seoul"}` 필드에 저장한다.
기존 `next`를 그대로 사용하며, 안전 상태/state·identity·경로·브랜치를 계획 수정으로
바꾸지 않는다. 이벤트는 추가한다. 계획의 제거는 실행/재개/삭제를 뜻하지 않는다.
계획에 알림·예약 실행·감시 기능은 **없다**. 날짜가 와도 창을 자동으로 만들지 않는다.

분류 우선순위는 거점 → 완료 기록 → 명시 예정일 → 나중에 표시/보관 → 기존 연결 분류다.
완료 작업의 지난 예정일은 예정 목록에 남지 않는다. 완료가 아닌 명시 예정 작업은
연결이 끊겨도 **예정에 한 번만** 표시하고 연결/Git 조회 경고를 배지로 붙인다.
보관 작업은 **나중에**에 표시한다. 명시 예정일이 있으면 예정이 우선한다.
완료·예정·나중에 분류는 연결 오류를 해결하거나 안전을 인증하는 것이 아니다.

기존 JSON 키/의미는 유지한다. task에 planning이 추가될 수 있고 board의 등록 항목에는
원래 저장된 상태인 `recorded_state`를 추가한다. 기존 `state`는 조회 오류 시 확인필요가
되는 동작을 유지한다. 텍스트 분류는 완료 기록을 보존하면서 현재 연결 경고도 보여준다.
폴더 없는 항목은 **아이디어 카드 · 폴더 없음**으로 표시하며 related_to의 관련 목표를 보여준다.
관계는 Git parent/stacking이나 기존 파일/대화 복사 권한이 아니다.

## 문맥 기반 추천 CLI

```bash
# 읽기 전용 후보: 외부 LLM/네트워크/추가 세션 조회 없음
awo task suggest videos --goal '을지로 변화' --current-task CURRENT_ID \
  --context '비슷하지만 새 주제로 따로 열어줘'
# 사용자의 명시 의도를 확인한 저장. 폴더/창은 만들지 않음.
awo task suggest videos --goal '을지로 변화' --current-task CURRENT_ID \
  --intent separate --next '자료 조사' --apply
# 나중에 할 아이디어만 저장
awo task suggest videos --goal '종로 변화' --current-task CURRENT_ID \
  --intent later --date 2026-10-05 --apply
# 정확한 기존 ID 선택; 창 연결은 별도 단계
awo task suggest videos --goal '성수동 보완' --current-task SEONGSU_ID --intent reuse --apply
# 생성/세션 시작은 기존 안전 경로로만
awo task start videos SAVED_ID --agent codex
```

추천 값은 `reuse`, `separate`, `later`, `needs-choice`와 근거다. 명시 `--intent`가 문맥
단서보다 우선한다. 기본 auto는 좁은 표현 규칙을 사용하는 **휴리스틱 후보**이며 일반적인
자연어 이해가 아니다. 부정/질문/충돌하는 단서는 needs-choice다. 표현/주제 유사도나 같은
목표 문구만으로 재사용하지 않는다. 현재 작업 A와 목표 B가 다르면 auto의 “이어서” 단서도
needs-choice로 남는다. 명시 `--intent reuse`에는 정확한 `--current-task`가 필요하다.

미리보기는 읽기 전용이다. **auto와 --apply 조합은 저장을 거부한다.** 이미 사용자의 의도가
분명하면 에이전트는 해당 명시 intent를 전달한다. 애매한 경우에만 선택을 확인한다.
needs-choice는 적용해도 저장하지 않는다. separate/later 적용은 새 ID의 폴더 없는 카드만
저장하고 current-task를 related_to로 연결한다. reuse 적용은 기존 ID만 선택하며 계획
옵션을 명시한 경우에만 그 계획을 갱신한다. 어느 추천도 세션 생성/전환/전송을 수행하지 않는다.

### 저장 재시도와 의도적인 새 카드

동일 프로젝트의 같은 목표·현재 ID·명시 intent는 기본 재시도 키를 공유한다. 같은 저장
요청을 반복하면 기존 카드를 반환하고 새 이벤트/파일/창을 만들지 않는다. 같은 키에 계획
옵션을 바꾸어 보내면 조용히 덮어쓰지 않고 거부한다. 수정에는 `task plan`을 사용한다.
같은 주제라도 의도적으로 별도 새 카드를 원하면 다른 `--request-id`를 지정한다.

```bash
awo task suggest videos --goal '을지로 변화' --current-task CURRENT_ID \
  --intent separate --request-id euljiro-version-2 --apply
```

이 명령 자체를 재시도하면 같은 카드를 반환한다. 명시 키는 영문/숫자로 시작하는 최대 80자
식별자다. 키는 프로젝트 내에서 유지한다. 아이디어를 실행하려고 동일 제목을 다시 저장하기
보다는 반환된 정확한 ID에 `task start`를 사용한다. 기존 세션의 자동 지침 로딩/감시는 없다.


## 완료 목록 접기

```bash
awo board                         # 완료 작업은 숨김
awo board --details               # 상세 모드도 완료는 숨김
awo board --include-done           # 완료 포함
awo board --include-done --details # 완료의 경로/브랜치/ID도 확인
awo board --json                   # 옵션과 무관하게 기존 전체 task 목록 유지
```

텍스트에서만 완료 섹션을 숨기고 숨긴 개수와 --include-done 힌트를 표시한다.
기록된 완료 상태를 사용하므로 오래된 경로가 현재 확인필요로 표시돼도 같은 원칙을 적용한다.
원본 report/tasks와 실제 연결 집계, 조회 오류·중복 작업자·작업폴더 연결 경고는 필터링하지
않는다. 숨긴 완료에 창 연결/조회 미확인이 있으면 프로젝트별 연결 확인 안내를 별도로 남긴다.
완료는 '사용자가 기록한 다음 행동 없음' 조언 대상으로 다시 포함하지 않는다.
이 옵션은 완료 기록을 만들거나 폴더·세션·메타데이터를 변경하지 않는다.

검증: renderer/CLI 경로 시험 17개, 완료된 old path 표적 통합시험 1개,
tests/test_cli.sh, make lint, git diff --check 통과. 기본/상세 숨김, include-done 표시,
JSON 전체 목록, 원본 report 불변, 숨긴 완료의 연결 위험과 집계 보존을 확인했다.
