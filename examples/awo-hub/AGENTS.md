# AWO 전용 배분 거점

이 파일은 복사/검토용 템플릿이다. 다른 저장소에 자동 설치하지 않는다.
설치할 때 아래 두 경로를 실제 절대 경로로 바꾼다.

- CLI: `/absolute/path/to/awo/bin/awo`
- 설정: `AWO_PROJECTS_FILE=/absolute/path/to/projects.yaml`

사용자 목표를 구체적인 프로젝트와 작업으로 해석한다. 프로젝트 언급만으로 생성하지 않는다.
`awo board`와 `awo request TEXT --project KEY --goal GOAL`로 기존 작업을 확인한다.
미등록 작업은 변경과 목표를 확인하고 `task import`로 명시 등록한다.
할일은 `task add`로 기록한다. 이것은 폴더/세션을 만들지 않는다.
같은 목표는 stable ID와 기존 경로를 재사용한다. 독립 목표만 새 worktree를 사용한다.
`request --apply --agent codex|claude`는 사용자가 승인한 독립 워커 배분에만 쓴다.
`--agent none`은 폴더 선택/생성만 수행한다. 거점은 직접 구현하지 않는다.
생성/세션 연결/턴 시작을 구별해서 보고한다. 세션 연결은 작업 완료 증거가 아니다.
`task resume KEY ID --agent codex|claude`는 검증된 기존 창으로 전환하거나,
정확한 경로에 세션이 없을 때만 새 독립 워커를 시작한다. unknown/복수 세션은 확인한다.
실패하면 폴더를 보존하고 재시도 전 실행 의도를 확인한다. 거점 구현으로 대체하지 않는다.
작업자는 대상 저장소 AGENTS.md를 따른다. 겹치는 파일과 자원을 배분 전에 조정한다.
`task park`는 프로세스를 종료하지 않는다. 인계를 저장하고 폴더/dirty/ignored를 보존한다.
프로세스 상태를 실제로 별도 확인했을 때만 `--processes-checked`를 사용한다.
보관/완료와 삭제 가능성은 다르다. `board --cleanup` 또는 `cleanup`으로 정리 안내를 확인한다.
삭제/종료/커밋/병합/발행은 작업 상태 변경의 자동 부작용으로 실행하지 않는다.

## 접두어 없는 명시적인 의도

AWO라는 접두어 없이도 사용자가 명확히 요청하면 위 절차를 적용한다.
“이거 더 고치자”는 같은 ID를 유지한다.
“을지로도 나중에 해보자”는 `task add KEY GOAL --related-to CURRENT_ID`만 한다.
“비슷하지만 다른 주제로 따로 열어줘”는 related add 후 새 ID로 task start한다.
“성수동으로 돌아가자”는 정확한 기존 ID로 resume한다.
“여기까지 접어두자”는 다음 행동/검증을 인계하고, 안전 조건을 확인한 뒤 거점에서
`task park KEY ID --close --processes-checked --next ... --validation ...`를 사용한다.
기본 park는 비파괴다. close는 단일 정확한 idle 세션/보존 확인이 안 되면 차단된다.
아이디어 언급만으로 창을 만들지 않는다. 의미 유사성/Jev는 명시적인 별도 작업 의도를
재사용으로 뒤집지 않는다. 관계는 Git stacking이나 기존 변경/대화 복사 허가가 아니다.
대상/의도가 분명하면 실행하고 애매할 때만 질문한다. 기존 세션 자동 reload를 주장하지 않는다.
Orca가 draft 필드를 제공하지 않으면 미전송 입력의 부재를 추정하지 않는다.
실제 화면에서 입력이 없음을 확인한 호출자만 park --close에 --input-checked를 추가한다.
부분 화면/실제 draft 존재는 이 옵션으로 우회하지 않는다.

## 계획과 문맥 추천

작업판은 상태→프로젝트→작업 트리와 거점 표로 읽는다. 계획 변경은 `task plan/update`로
`--later`, `--date YYYY-MM-DD`(KST), `--next`를 지정한다. 제거는 --clear-later/--clear-date/
--clear-next다. 계획은 안전 상태나 identity를 바꾸지 않고, 날짜 알림/자동 실행을 하지 않는다.
폴더 없는 아이디어의 related_to는 관련 목표일 뿐 Git parent나 대화 복사 허가가 아니다.

문맥이 필요하면 `task suggest KEY --goal GOAL --current-task ID --context TEXT`로 후보와
근거를 확인한다. auto는 휴리스틱이며 쓰기 권한이 아니다. 사용자의 의도가 명확하면
--intent reuse|separate|later를 명시해 --apply한다. 불명확할 때만 질문한다.
현재 A와 새 목표 B가 다른데 “이어서”라고만 하면 재사용을 확정하지 않는다.
reuse는 정확한 current-task ID를 명시해야 한다. 명시 separate는 유사도가 높아도 별도 카드다.
separate/later 적용은 아이디어만 저장한다. 창/폴더 시작은 반환된 ID로 기존 task start를 쓴다.
동일 저장 재시도는 기본 키로 중복 방지한다. 의도적인 별도 새 카드에는 다른 --request-id를
사용하고 재시도에는 같은 키/옵션을 유지한다. 기존 카드 변경에는 task plan을 쓴다.
다른 프로젝트/전역 지침 자동 설치나 이미 실행 중인 세션의 자동 로딩/감시를 주장하지 않는다.
