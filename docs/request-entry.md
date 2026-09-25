# 자연어 작업 진입

총괄 에이전트가 사용자 문장에서 **대상 저장소와 구체적인 목표**를 읽고,
`awo request`가 등록된 이름·별칭을 매칭하고 Git 상태를 확인한다.
기본 명령은 모델을 호출하지 않는다. 원문만으로 작업 목적을 추측하지 않고,
총괄 에이전트가 확인한 목적을 `--goal`로 전달한다.

선택적으로 `--advise jev`를 붙이면 애매한 프로젝트·기존 목표에 대해서만
외부 Jev API의 후보 추천을 별도 `advisory` 필드로 받는다.
요청문이 외부로 전송되는 명시적 opt-in이다. 추천이 `action`이나 선택을
변경하지 않으며 `--apply`와 함께 사용하면 추천 호출을 생략한다.
키·전송 범위·상태·총괄 확인 및 롤백은 [Jev 추천 안내](jev-advice.md)를 따른다.

## 등록과 호출

기존 `projects.yaml` 형식을 유지하며 `aliases`는 `|`로 나눈 문자열이다.
호출 위치와 무관하게 같은 설정 파일을 쓰려면 `AWO_PROJECTS_FILE`을 지정한다.
개인 경로를 포함한 설정은 Git 무시 대상이다.

```yaml
projects:
  agents:
    path: "/absolute/path/to/agents"
    aliases: "나의 카카오 비서|카카오 비서|카카오"
    base_ref: "origin/main"
    max_worktrees: 3
    default_agent: "codex"
    merge_policy: "manual"
```

`AWO`는 호출 접두사이므로 프로젝트 매칭에서 제외한다. AWO 저장소 자체를
고르려면 `--project awo` 또는 `오케스트레이터` 같은 별칭을 사용한다.
복수 저장소가 매칭되면 `needs_project`와 후보를 반환한다. 총괄 에이전트는
사용자에게 대상을 확인하고 `--project KEY`로 명시한다.

```bash
AWO_PROJECTS_FILE=/absolute/path/to/projects.yaml /absolute/path/to/bin/awo \
  request 'AWO 카카오 비서 관련 작업하고 싶다'
```

이 문장에는 구체적인 목표가 없으므로 `needs_goal`을 반환한다. 사용자에게
어떤 기능이나 문제를 작업할지 묻는다. 저장소 언급만으로 생성하지 않는다.
목표가 있으면 다음 명령으로 먼저 기존 작업과 변경 파일을 살핀다.

```bash
./bin/awo request 'AWO 카카오 비서' --goal '미답 질문 오탐 수정'
```

출력은 항상 JSON이다. `worktrees`에는 경로·브랜치·미커밋 상태·기준 대비
변경 파일이 있고, `known_goals`에는 검증된 기존 목표 연결이 있다.
미리보기는 fetch나 메타데이터 저장을 하지 않으므로 기준 ref가 오래됐을 수 있다.
`--apply`에서 origin을 가져오고 Git 상태를 재검사한다.

| action | 총괄 에이전트의 다음 행동 |
| --- | --- |
| `needs_project` | 대상 경로/이름 확인 후 등록 또는 `--project` 지정 |
| `needs_goal` | 구체적인 작업 목적 질문 |
| `needs_worktree` | 기존 작업 확인 후 `--worktree PATH` 또는 `--new-goal` 지정 |
| `reuse` | `--apply`로 연결을 기록하고 반환 경로에서 작업 재개 |
| `create` | 독립 목표와 파일 중복 여부를 확인한 뒤 `--apply` |
| `blocked` | 원인을 해결한 뒤 재검사; 삭제나 강제 초기화 금지 |

같은 목표는 Unicode NFKC·대소문자·공백을 정규화하여 비교한다. 표현이 다른
동일 목표인지 판단하는 일은 총괄 에이전트가 맡는다. 동일 목표라면 기록된
목표 문구를 `--goal`에 재사용한다. 미등록 worktree는 브랜치 이름만으로 같은
목표라고 간주하지 않는다. 변경과 요구사항을 확인한 뒤 다음과 같이 연결한다.

```bash
./bin/awo request 'AWO 카카오 비서' --goal '미답 질문 오탐 수정' \
  --worktree /absolute/path/to/existing-worktree --apply
```

별개 목표라면 미등록 worktree를 확인한 후에만 `--new-goal`을 사용한다.
자동으로 목표가 같은 worktree를 찾으면 생성보다 재사용이 우선이며, dirty
상태와 worktree 한도 도달은 재사용을 막지 않는다. 파일은 그대로 보존한다.
진행 중 Git 작업, 잠금, 잘못된 경로·메타데이터는 작업을 막는다.

```bash
./bin/awo request 'AWO 카카오 비서' --goal '미답 질문 오탐 수정' \
  --task kakao-question-false-positive --new-goal --apply
```

생성은 기존 `awo start`를 호출한다. 설정한 `base_ref`를 명시하고 Orca
`--no-parent`로 생성한다. 한국어 목표의 기본 작업명은 안정적인 해시이며,
읽기 쉬운 이름을 원하면 `--task`로 ASCII slug를 지정한다.
`request`는 기본적으로 `--agent none`을 사용해 현재 에이전트가 반환 경로에서
작업을 계속한다. 별도 에이전트가 필요하고 허용된 경우만 `--agent codex` 또는
`--agent claude`를 명시한다. 기존 `start`의 기본 에이전트 동작은 유지된다.
재사용은 새 에이전트를 실행하지 않는다.

목표 연결은 대상 저장소의 공용 Git 디렉터리 아래 `awo/tasks.json`에만 저장한다.
예전 경로가 제거되거나 다른 worktree로 바뀌면 연결을 재사용하지 않는다.
동시 `request --apply`는 저장소별 잠금으로 중복 생성을 막는다. 다른 도구나
직접 실행한 `awo start`까지 잠그지는 않으므로 동시에 생성하지 않는다.
Orca가 실패한 뒤에는 기존 경로를 다시 확인한다. 생성된 worktree를 자동 삭제하지 않는다.
목표에는 비밀이나 고객 본문을 넣지 않는다.

## agents/main을 지시 거점으로 연결하는 제안

연동 구현과 별개로 **agents 파일은 자동 변경하지 않는다.** 새 대화에서도
자연어 호출을 발견하려면 agents의 `AGENTS.md`에 아래 지침을 추가해야 한다.
실제 CLI와 설정 파일 경로를 확정한 후 적용할 문구다.

```markdown
## AWO 작업 라우팅

사용자가 “AWO … 작업하고 싶다”라고 하면 AWO 저장소의
docs/request-entry.md와 skills/git-orchestrator/SKILL.md를 읽는다.
고정된 AWO_PROJECTS_FILE과 AWO CLI 절대 경로를 사용한다.
“나의 카카오 비서”와 “카카오 비서”는 agents 저장소의 카카오 작업 별칭이다.
대상 또는 구체적 목표가 불명확할 때만 질문한다.
awo request로 기존 목표·worktree·변경 파일을 확인한다.
동일 목표는 기존 worktree를 재사용한다. 독립 목표만 --apply로 생성한다.
main은 지시 거점으로 유지하고 실제 코드는 반환된 worktree에서 작업한다.
외부 저장소 작업에는 그 저장소의 AGENTS.md를 적용한다.
카카오 작업에서는 기존 읽기 전용 검토 규칙과 요청의 범위를 확인한다.
명시적으로 구현을 요청받은 경우에만 해당 작업 worktree에서 수정한다.
```

이 지침은 각 저장소 규약을 대체하거나 포괄적인 수정 권한을 부여하지 않는다.
연동 문구가 적용되기 전에는 사용자가 직접 AWO 문서/명령 경로를 제공하거나
이미 이를 읽은 대화에서 호출해야 한다. CLI 변경만으로 새 대화의 지침이
자동 설치되지는 않는다.

## 원격 없는 로컬 저장소

원격이 하나도 없는 저장소는 `base_ref: "main"`처럼 실제 로컬 브랜치를
명시하면 `request --apply`와 `start`로 작업할 수 있다. 원격이 설정돼 있다면
기존처럼 origin fetch가 필수다. origin 장애나 origin 대신 다른 원격만 있는
상태를 로컬 모드로 조용히 대체하지 않는다. 로컬 모드에는 원격 최신성·백업
보장이 없다. audit/status/finish/cleanup의 원격 전제는 별도로 유지된다.
