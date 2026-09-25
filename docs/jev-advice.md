# Jev 프로젝트·기존 목표 추천

`awo request ... --advise jev`는 터미널 접수에서 총괄 AI가 후보를 검토할 때 쓰는
선택 기능이다. 기본값 `--advise none`에서는 네트워크 호출과 키 파일 읽기가 없다.
명확한 별칭/`--project`, 정확히 일치하는 기존 목표와 Git 검증은 기존 규칙이 담당한다.
모델은 목표 문장을 생성하지 않고 등록된 후보와 요청 유형만 Choice로 추천한다.
추천은 코드 수정·검토·조사에 대한 사용자 승인이나 작업 실행 권한이 아니다.

## 호출과 총괄 절차

```bash
# 고정 CLI 경로와 기존 레지스트리 경로를 사용한다.
AWO_PROJECTS_FILE=/absolute/path/to/projects.yaml /absolute/path/to/bin/awo \
  request '메시지가 와도 알려주지 않던 문제 이어서 고쳐줘' \
  --goal '알림 누락 원인 수정' --advise jev
```

1. 총괄이 요청에서 구체적인 목표를 확인하고 먼저 기본 `request`로 규칙 결과를 본다.
2. 대상 프로젝트나 기존 목표가 애매할 때만 사용자가 허용한 요청문으로
   `--advise jev` 미리보기를 한다. 이 플래그는 외부 전송에 대한 명시적 opt-in이다.
3. `advisory.answers`의 선택 ID와 `advisory.candidates`의 로컬 매핑을 확인한다.
   `project:<key>`는 등록 프로젝트, `task:<opaque-id>`는 검증된 기존 목표다.
   작업 ID는 해당 스냅샷용이며 실행 입력·영구 식별자로 사용하지 않는다.
4. 기존 목표 문구·현재 경로·브랜치·변경·작업 지시를 실제로 확인한다. 추천만으로
   같은 목표라고 확정하지 않는다. `request --project KEY --goal '기록된 목표'`로
   새로 미리보기하고, 같은 작업이면 아래처럼 경로를 명시한다.
5. 새 목표는 기존 작업과 파일 중복을 확인한 뒤 기존 `--new-goal` 절차를 따른다.
   원문의 검토 요청을 구현 권한으로 바꾸지 않는다.

```bash
# 추천 JSON에서 경로를 무조건 실행하지 않는다. 검증 후 수동 선택한다.
AWO_PROJECTS_FILE=/absolute/path/to/projects.yaml /absolute/path/to/bin/awo \
  request '카카오 비서 작업 계속' --project secretary \
  --goal '카카오 알림 누락 수정' --worktree /verified/existing/worktree --apply
```

`--advise jev --apply`를 함께 쓰면 `advisory.reason=apply_boundary`이고 Jev·키 파일을
읽지 않는다. `--apply` 자체는 종전 규칙에 따라 생성·재사용할 수 있다.
즉 이 조합이 실행 전체를 막는 것은 아니다. 별도 미리보기의 추천은 다음 명령에
자동 전달되지 않는다. 어떤 성공·오류 응답도 `action/project/path/goal`을 수정하지 않는다.

프로젝트가 명확하면 프로젝트 질문을 보내지 않는다. 정확한 기존 목표,
명시적 `--worktree`/`--new-goal`, 목표가 없는 명확한 프로젝트는 규칙 결과로 충분하므로
호출하지 않는다. 명확한 프로젝트에서 유사 목표를 찾을 때는 기존 목표 후보가
있어야 호출한다. 한도 도달로 `blocked`인 경우에는 기존 목표를 추천할 수 있지만
차단 결과는 유지한다. 다른 규칙 차단은 추천도 생략한다.

## 키 읽기

우선순위는 `TYPESAFE_API_KEY` 환경변수, 그다음 `~/.config/awo/jev.env`이다.
환경변수가 존재하지만 빈 문자열이면 파일로 대체하지 않고 `missing_key`를 반환한다.
전용 파일은 UTF-8이며 **따옴표·export 없이 다음 할당이 정확히 하나** 있어야 한다.
한국어를 포함한 `#` 주석 줄과 빈 줄, LF/CRLF는 허용한다. 다른 변수·중복 할당·
할당 뒤 inline 주석은 거부한다.

```text
TYPESAFE_API_KEY=YOUR_KEY
```

파일은 현재 사용자 소유의 일반 파일이고 권한이 정확히 0600이어야 한다.
마지막 경로 요소가 심볼릭 링크면 거부하며 열린 descriptor에 `fstat` 검사를 한다.
FIFO 등 특수 파일도 거부한다. 키는 Bearer token 문자만 허용한다.
`shell source`, `eval`, 자동 파일 생성·권한 변경·환경변수 수정은 하지 않는다.
오류에는 키, 파일본문, 원격 응답 본문을 넣지 않는다. 키를 CLI 인수나 레지스트리에 넣지 않는다.

파일 없음·빈 파일·빈 값은 `unavailable/missing_key`, 잘못된 형식은
`key_file_format` 또는 `invalid_key_format`, 잘못된 소유자·권한·파일 유형은
`key_file_owner`, `key_file_permissions`, `key_file_type`이다.
심볼릭 링크/읽기 실패는 `key_file_unreadable`이다. 오류 시 환경 또는 파일을 수정하지 않는다.

## 전송 범위와 제한

공식 [API 스키마](https://docs.typesafe.ai/api)에 따라 고정된
`https://api.typesafe.ai/v1/systemone`으로 `model=jev-1.13.0`을 보낸다.
`state/model/questions`와 Choice 응답을 사용하며 추가 SDK 의존성이 없다.

전송 허용 필드는 다음뿐이다.

- 사용자가 이번 명령에 넣은 요청문과 `--goal` 문구
- 등록 프로젝트 key, aliases, 선택적 `description` 문자열
- 현재 Git identity로 검증된 기존 목표의 opaque ID, 프로젝트 key와 목표 제목
- 고정된 분류 질문·선택지

경로, 브랜치, Git diff, 파일명/내용, 환경변수, 전체 대화는 후보 데이터에 넣지 않는다.
작업 ID와 실제 경로의 매핑은 로컬 결과에만 포함한다. `.env`나 코드 파일, 대화 기록을
검색해 맥락을 보충하지 않는다. 모델은 `none/ambiguous/multiple`도 선택할 수 있다.
요청 유형은 `review/implementation/research/unclear/none/multiple` 중 하나다.

목표 제목·설명·별칭·요청문에는 비밀이나 고객 본문을 넣지 않는 계약을 유지한다.
절대경로/일반적인 비밀 표기와 현재 키가 발견되면 `sensitive_input`으로 전송을 막는다.
이 검사는 완전한 비밀 탐지기가 아니므로, 원문에 민감정보가 있으면 먼저 총괄이
비식별 요약을 준비한다. 사용자 설정에는 자동으로 설명이나 키를 추가하지 않는다.

한 요청은 프로젝트 64개, 검증된 목표 128개, 전체 UTF-8 본문 64 KiB 이내다.
요청문 2,048자, 목표 500자, 프로젝트 설명 240자, aliases 512자로 제한한다.
초과 시 조용히 잘라내거나 여러 번 요청하지 않고 `candidate_limit/input_limit`을 반환한다.
응답은 128 KiB, socket timeout은 5초로 고정하며 자동 재시도·redirect를 하지 않는다.
DNS/OS 지연까지 포함하는 엄격한 전체 wall-clock 상한은 아니다.

`answers`의 모든 질문/선택 ID, 전체 확률 분포, 합계, 최댓값 선택, confidence의 유한한
0~1 범위, 고정 모델과 `usage.input_tokens`를 검증한다. 불완전한 JSON, NaN/Infinity,
알 수 없는 ID는 추천으로 사용하지 않는다. API 응답 뒤 후보를 다시 검사하여
삭제/교체/잠금/목표 변경으로 스냅샷이 바뀌면 `stale_candidates`로 버린다.
검증 후에도 작업 상태는 바뀔 수 있으므로 적용 전 기존 AWO 검증이 반드시 필요하다.

## 상태 읽기

| `advisory.status` | 의미 |
| --- | --- |
| `disabled` | opt-in 없음, 규칙으로 충분함, 명시적 선택, 규칙 차단 또는 apply 경계; 외부 호출 없음 |
| `unavailable` | 키 없음, 입력/후보 검사 실패, timeout/network/429, 잘못된 응답 등; 후보 없음과 다름 |
| `shadow_advisory` | 단일 후보가 없거나, 불명확·복수 요청으로 전체 요청 검토가 필요함; 후보는 보존 |
| `suggested` | 단일 요청 유형과 구체적인 프로젝트 또는 기존 목표 후보가 있음; 총괄 검토 전용 |

`source=none`은 외부 호출 전, `source=live`는 실제 전송 경로를 사용한 상태다.
후자도 오류일 수 있으므로 성공 여부는 status로 확인한다. 운영 CLI에는 fixture를
주입하는 옵션이 없다. `mode=advisory_only`, `execution_authority=false`는 모든 상태에 고정된다.
`request_type=unclear/none/multiple` 또는 후보 선택의 `ambiguous/multiple`은
`shadow_advisory/request_needs_review`로 표시한다. 요청 유형의 모호함은 `unclear` 하나로
표준화했다. 기존 목표는 요청 전체에 맞아야 하며 일부만 맞는 혼합 요청은
`ambiguous`로 검토한다. confidence는 모델의 분포 지표이며 정확도·정답 보장·사용자 승인 확률이 아니다.
한국어 실측 전후 모두 이 구현에는 추천을 자동 실행하는 경로가 없다.

## 한국어 평가와 검증 범위

이 워커는 실제 사용자 키를 읽거나 실제 API를 호출하지 않았다. 계약 테스트는
모두 mock/합성 응답으로 검증했다. root가 별도로 실시한 최초 연결/탐색 결과는 아래에
분리해 기록한다. 이 워커의 live 실행 결과나 일반적인 한국어 정확도 검증으로 취급하지 않는다.

`tests/fixtures/jev-korean-cases.json`에는 표현이 다른 이어하기, 검토 전용,
조사, 새 목표, 해당 없음, 모호함, 복수 작업, 관련 있지만 다른 목표,
인사와 프롬프트 주입 문구 등 12개 공개 합성 샘플과 기대 라벨이 있다.
일부 모호한 라벨은 사람이 검토할 평가 가설이다.

```bash
# 키나 네트워크 없이 스키마만 replay. 정확도 평가가 아니다.
python3 tests/evaluate_jev.py --replay --limit 12

# 사용자가 live 전송을 승인하고 키를 준비한 뒤 별도 실행한다.
# 처음에는 공개 합성 문장 한 건만 보낸다. 기본 limit=3, 최대 12.
python3 tests/evaluate_jev.py --live --limit 1
```

replay 출력은 `source=fixture_replay`, `live_api_verified=false`,
`is_accuracy_measurement=false`이며 기대 라벨로 만든 응답을 검증할 뿐이다.
live 출력에는 실제 answers/usage와 문항별 `label_matches`가 있다. 키가 없으면
정상 JSON의 `missing_key`로 끝난다. 첫 오류에서 중단하여 호출이 증폭되지 않게 한다.
이 스크립트는 provider만 평가하며 규칙 우선 라우팅은 `test_advice.py`가 별도 검증한다.
실측하지 않은 지연·비용·정확도·비교 벤치마크 수치를 보고하지 않는다.

## 롤백

즉시 비활성화하려면 호출에서 `--advise jev`를 제거하거나 `--advise none`으로 바꾼다.
영구 활성화 설정·백그라운드 작업·키 자동 로딩 훅은 없다. 전용 키 파일과 사용자 환경은
삭제하거나 변경할 필요가 없다. 기본 CLI는 해당 파일을 읽지 않는다.

코드 전체 롤백은 깨끗한 별도 작업 브랜치에서 이 기능의 커밋 SHA를 확인하고
`git revert <jev-routing-commit>`으로 한다. 최종 SHA는 작업 완료 보고를 따른다.
롤백은 기존 tasks.json, worktree, 사용자 projects.yaml, 키 파일을 삭제하지 않는다.
`reset --hard`, 강제 브랜치/작업 공간 삭제를 사용하지 않는다.

## 최초 실측 기록과 변경 후 재검증

2026-09-25 root가 사용자 저장키로 공개 한국어 연결 예제 1건 성공을 보고했다
(0.803초, research). 이어 공개 합성 12건 provider 평가를 실행했다.
[초기 원본 결과](evaluations/2026-09-25-jev-initial.json)는 키·실제 프로젝트 정보가 없는
합성 fixture 결과만 담으며 변경 없이 보존했다. 전체 관측 시간 7.505초,
기대 라벨 일치는 project 12/12, existing_goal 11/12, request_type 11/12였다.
이는 해당 12개 탐색 샘플의 관측치이며 모델 정확도·성능 비교·자동 라우팅 검증이 아니다.
원본의 `is_accuracy_measurement=true`도 기대 라벨 대조 모드를 뜻하며 일반화 가능한 정확도가 아니다.

- `ambiguous`: 요청 유형은 기대 `unclear`와 달리 `ambiguous`; 선택지 의미가 중복됐다.
- `mixed-intent`: 일부만 맞는 `task:video`를 추천했다. 기대 라벨 `ambiguous`는 유지했다.

그 뒤 요청 유형에서 `ambiguous`를 제거하여 `unclear`로 통일하고, 전체 요청 적합 조건과
검토 필요 상태를 추가했다. 기대 라벨은 바꾸지 않았다. 초기 결과는 변경 전 스키마이므로
현재 validator에 성공 응답으로 replay하지 않는다. 변경 후 live 재검증은 별도 결과로
남겨야 하며, 회귀테스트/replay 통과를 새 live 결과로 표현하지 않는다.


변경 후 root가 사용자 키 파일을 수정하지 않고 최종 CLI 연결을 재확인했다.
기본 요청은 `action=needs_worktree`, `disabled/not_requested/source=none`,
추천 요청도 동일한 `action=needs_worktree`이며
`suggested/candidate_recommendation/source=live/model=jev-1.13.0`,
`execution_authority=false`였다. 각 관측 시간 5.379초/6.739초는 단일 관측이며
성능 비교 벤치마크가 아니다.

[변경 후 재검증 원본](evaluations/2026-09-25-jev-retest.json)은 최초 결과와 별도 보존했다.
총 7.802초, 스키마 12/12 통과, project/existing_goal/request_type 각 12/12 기대 라벨 일치.
이는 문제를 확인하고 수정한 뒤 **같은 탐색 샘플**로 다시 확인한 결과다.
독립 holdout 정확도나 자동 실행 가능성의 증거로 해석하지 않는다.

## 1주 제한운영과 로컬 관측

이 기능은 서버나 예약을 설치하지 않는다. 운영 담당자가
`~/.awo/jev-trial/config.json`을 준비한 경우에만 기간 내 `--advise jev` 결과를
`~/.awo/jev-trial/events.jsonl`에 append-only로 기록한다. 설정 스키마는 아래 두 필드뿐이다.
각 시간에는 UTC `Z` 또는 명시적 UTC offset이 필요하며, 시작은 포함·종료는 제외한다.

```json
{
  "starts_at": "2026-09-25T09:00:00Z",
  "ends_at": "2026-10-02T09:00:00Z"
}
```

위 시작 시간은 예시다. root가 실제 제한운영 시작 시각을 넣어 설치한다. 설정 파일이
없으면 종전 opt-in 동작을 그대로 유지하고 기록하지 않는다. 기본 `--advise none`은
trial 설정·키를 읽거나 API를 호출하지 않는다. 설정이 있으면 시작 전·만료 후에는
API 호출을 막고 `trial_not_started/trial_expired`를 반환한다. 잘못된 설정도 호출을 막는다.
후보 Git 검사 사이에 기간이 끝나는지도 API 호출 직전에 다시 확인한다.
만료가 요청 도중 발생하면 결과 기록을 생략하고 `trial_window_changed`로 표시한다.
기간을 자동 연장하거나 만료된 파일을 지워 예전 동작으로 되돌리지 않는다.

애매한 프로젝트나 기존 목표에만 `--advise jev`를 명시한다. 정확한 규칙이 있거나
apply인 경우 모델 호출은 하지 않으며, 활성 trial에서는 이 생략 결과도 기록한다.
이 기능이 자동 실행·추가 외부 호출·사용 확대 권한을 부여하지 않는다.

```bash
# 실제 업무: 기본 cohort=production
./bin/awo request '메시지 누락 문제 이어서 검토해줘' --goal '알림 문제 검토' --advise jev

# 공개 합성 연결 확인: 실제 업무와 분리
./bin/awo request '공개 합성 예제 문장' --advise jev --advice-cohort smoke

./bin/awo jev-trial status --json
./bin/awo jev-trial report --json

# 실제 총괄 판단을 마친 뒤 반환된 event_id로 명시 기록
./bin/awo jev-trial feedback EVENT_ID --result accepted --json
./bin/awo jev-trial feedback EVENT_ID --result corrected --critical-misroute --json
./bin/awo jev-trial feedback EVENT_ID --result uncertain --json
```

`accepted`는 총괄이 후보를 검토하고 채택한 경우, `corrected`는 수정한 경우,
`uncertain`은 검토했으나 판단이 끝나지 않은 경우다. 실행 여부나 사용자 승인을
자동 추론해 채택 처리하지 않는다. 정상 추천 응답(`suggested/shadow_advisory`)을
받은 event만 피드백할 수 있다. 실패·API 생략에는 채택 피드백을 붙이지 않는다.
동일 event의 피드백은 추가 기록하되 파일 순서상 최신 값을 집계한다.
기간이 끝난 뒤에도 기존 결과에 대한 명시 피드백은 가능하다.

이벤트에는 UUID `event_id`, UTC timestamp, cohort, status/reason, 고정 모델,
`api_called`, `api_latency_ms`, 알려진 `input_tokens`, 불투명 `selection_ids`만 저장한다.
selection ID는 이벤트별로 다르며 프로젝트 이름·목표 ID 원문을 기록하지 않는다.
요청문·goal·로컬 경로·키·후보 본문·확률 분포는 저장하지 않는다.
API 시간은 provider 호출을 감싼 단조 시계 측정으로, 후보 Git 검사와 후속 검증/기록 시간을
제외한다. `api_called=true`는 호출을 시도했다는 뜻이며 서버 수신·과금을 보장하지 않는다.
실패한 호출도 지연 표본에 포함하고, 응답 사용량을 검증하지 못하면 tokens는 null이다.

기록 파일은 0600 일반 파일로 열고, symlink를 거부하며 flock으로 append를 직렬화한다.
기록 실패 시 AWO action과 추천은 유지하며 `advisory.trial.status=unavailable`,
`reason=record_failed`를 표시한다. 이 경우 보고서가 해당 요청을 셀 수 없으므로
운영 담당자가 실패를 별도로 확인해야 한다. 실패 로그를 다른 위치에 자동 저장하지 않는다.
기록 실패 후 자동 재시도도 하지 않는다. 일부 쓰기나 손상된 JSONL은 report가 오류로
표시하고 조용히 누락시키지 않는다. 16 MiB를 넘는 저널은 `journal_limit`로 보고를 중단한다.

report는 설정 기간의 production/smoke를 **각각** 집계한다. 실제 API 시도·정상 추천 응답·
실패·호출 생략, 검토됨/미검토/채택/정정/불확실/중대오판과 알려진 token 합계를 제공한다.
정상 응답 후 후보 재검증이 실패한 경우도 `live_failures`에 포함한다.
미검토 수는 정상 추천 응답 중 피드백 없는 수다. 중대오판 0은 관측된 최신 피드백에
표시가 없다는 뜻이지 미검토 결과가 옳다는 뜻이 아니다. p50/p95는 관측 표본의
nearest-rank이며 표본 0이면 null이다. 데이터가 없으면 `insufficient_data`, 검토가 있더라도
`exploratory_only`이고, `sufficiency/quality=unknown`을 유지한다. 정확도 비율을 생성하지 않는다.
`tests/evaluate_jev.py`의 합성 provider 평가 자료는 이 업무 저널에 자동 합산하지 않는다.

제한운영 종료 시 `jev-trial report --json`과 총괄 피드백을 근거로 사람이 검토한다.
자동 실행이나 확대는 별도 승인 사항이다. 즉시 중지하려면 추천 플래그를 사용하지 않는다.
config/journal을 자동 삭제하지 않으며 만료 설정을 유지해 호출 차단 상태를 보존한다.
최초 기능으로 코드 롤백하려면 trial 추가 커밋만 `git revert <trial-commit>`한다.
이때 만료 차단도 제거되어 명시적 opt-in API 기능이 남으므로, 제한운영 중단에는 우선
`--advise jev` 사용을 중지해야 한다. 사용자 설정·키·관측 기록은 revert로 삭제하지 않는다.
