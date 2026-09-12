# 디스크 여유 공간 감시 구현 결과 — 2026-09-12 KST

AWO 0.2.0의 별도 `awo disk` 명령으로 호스트 디스크 감시를 구현했습니다.
버전 번호는 변경하지 않았습니다. 사용 방법은 [disk-watch.md](../disk-watch.md)에 있습니다.

## 구현

- `awo disk check [PATH]`: 실제 파일시스템 여유 공간을 조회합니다. 기본 경로는 `/`이며
  `--notify` 없이 실행하면 상태를 변경하지 않는 미리보기입니다.
- `--notify`: macOS에서 상태를 저장하고 경고·긴급·회복 전이 때만 알림을 호출합니다.
  최초 정상은 알리지 않습니다. 경고는 10GB 미만, 긴급은 5GB 미만,
  정상 회복은 15GB 이상입니다. GB는 10억 바이트이며 CLI로 조정할 수 있습니다.
- 경고·긴급을 회복 기준까지 유지하는 히스테리시스, 경로별 JSON 영속화,
  원자적 교체와 프로세스 잠금으로 반복·동시 실행의 중복 알림을 방지합니다.
- `awo disk launchd install|uninstall`: 기본 300초 간격, 로드 시 즉시 검사하는
  전용 LaunchAgent입니다. 기본은 미리보기이며 `--apply`로 적용합니다.
  `com.awo.disk.<경로 해시>` 레이블을 사용하고 기존 watch 모듈은 수정하지 않았습니다.
- 로컬 파일시스템 조회·상태 파일·macOS 도구만 사용합니다. 비밀값, 외부 전송,
  파일 정리·삭제 기능은 추가하지 않았습니다. 작업 제거는 해당 plist에 한정됩니다.

## 변경 파일

| 파일 | 실제 변경 |
| --- | --- |
| `bin/awo` | disk 명령 분기 및 도움말 |
| `scripts/awo_disk.py` | 조회, 임계값, 상태 전이, 저장·잠금, macOS 알림, CLI |
| `scripts/awo_disk_launchd.py` | 전용 plist 생성 및 명시적 설치·제거 |
| `tests/test_disk.py` | 신규 테스트 27개 |
| `docs/disk-watch.md` | 사용법, 전이 표, 운영·오류 처리, 한국어 안내 |
| `docs/usage.md` | 디스크 감시 문서 연결 |
| `docs/work-results/2026-09-12-disk-space-watch.md` | 이 작업 기록 |

## 검증 결과

- `make test`: Python 테스트 **63개 통과**, CLI 셸 테스트, 설정 파서 테스트,
  Bash 구문 검사 통과. 신규 디스크 테스트 27개를 포함합니다.
- `make lint`: ShellCheck 통과.
- `git diff --check`: 통과.
- 실제 macOS에서 `bin/awo disk check / --json`: 정상 조회, 미리보기,
  알림 없음 확인. 측정 시 여유 공간 약 16.68GB였으며 현재값을 보장하지 않습니다.
- `bin/awo disk launchd install / --interval-seconds 300`: 전용 레이블,
  `StartInterval=300`, `RunAtLoad=true`, 알림 활성화 인자를 가진 plist 미리보기 확인.
- 실제 별도 프로세스 재실행 시 상태 재사용 및 중복 억제, 다른 프로세스의 잠금 충돌,
  임계값 경계·히스테리시스, 상태 손상·저장 실패·측정 실패·알림 시간 초과,
  경로 인자 이스케이프, 설치 실패 복구·제거 실패 보존을 자동 검증했습니다.
- 최초 대상 테스트의 `/tmp` 기대 경로 1건이 macOS `/private/tmp` 정규화로 실패했고,
  정규화된 기대값으로 수정한 뒤 전체 테스트가 통과했습니다.
- 알림 API와 launchctl은 자동 테스트에서 모의 호출했습니다. 실제 배너 표시,
  실시간 주기 실행, 잠자기 후 동작은 미검증이며 호스트에 감시 작업을 설치하지 않았습니다.

## 운영 한계 및 Git 상태

- 중복 억제를 우선해 알림 호출 전에 전이를 저장합니다. 알림 호출 실패·시간 초과 또는
  저장 직후 프로세스 종료 시 해당 전이를 재시도하지 않으므로 알림이 누락될 수 있습니다.
  macOS 알림 설정에 따른 배너 표시도 보장하지 않습니다.
- 현재 worktree는 `.../orca/workspaces/agent-worktree-orchestrator/disk-space-watch`,
  브랜치는 `jakeparkcolde/disk-space-watch`입니다. 시작 및 최종 코드 검증 시
  `origin/main`과 HEAD는 `e0cf21e`로 동일했습니다. 이 기록은 기능 커밋에 함께 포함합니다.
- 레지스트리에 AWO 프로젝트 항목이 없어 `awo status agent-worktree-orchestrator`는
  실패했습니다. Git으로 기준점·진행 중 Git 작업 없음·worktree 3개를 별도 확인했습니다.
  디스크 명령은 프로젝트 레지스트리에 의존하지 않습니다.
- 다른 worktree의 작업은 보존했습니다. 원격 push, PR 생성·병합, worktree 정리,
  상주 프로세스 시작은 실행하지 않았습니다. 실행한 테스트 프로세스는 모두 종료됐습니다.
- 후속 운영 시 안정적으로 유지할 체크아웃에서 문서의 설치 미리보기를 확인한 후
  원하는 경로·임계값·간격으로 LaunchAgent를 설치하면 됩니다.
