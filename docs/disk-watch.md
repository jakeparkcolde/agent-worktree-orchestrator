# Host disk space monitoring / 호스트 디스크 여유 공간 감시

`awo disk` measures free space on the local filesystem containing an existing
file or directory. It is independent of projects.yaml, Git worktrees,
`awo watch <project>` and `awo launchd ... <project>`. It never deletes files,
collects file contents, or sends data over the network. Python 3 is required;
notifications and LaunchAgent installation require macOS and a logged-in GUI user.

## One scan

```bash
# Read-only preview: no notifications, state writes or job installation.
./bin/awo disk check / --json
./bin/awo disk check "$HOME"

# Persist state and send a macOS notification only when the state changes.
./bin/awo disk check / --notify --json

# Override thresholds (decimal GB: 1 GB = 1,000,000,000 bytes).
./bin/awo disk check / --notify \
  --warning-gb 20 --critical-gb 8 --recovery-gb 25
```

Omitted PATH defaults to `/`. Paths with spaces should be quoted. Existing
symlinks resolve to the same canonical path and share state. Different paths
have independent state even when they reside on the same volume, so choose one
path per volume to avoid receiving separate alerts for the same free space.
The measurement uses `shutil.disk_usage(path).free` (filesystem space available
to the user), not Finder's estimate including potentially purgeable space.

## State transitions

Defaults are warning below **10 GB**, critical below **5 GB**, recovery at
**15 GB or above**. Thresholds must be finite and ordered:
`0 < critical-gb < warning-gb < recovery-gb`. Fractional GB values are supported.

| Previous state | Free space | Next state | Notification with `--notify` |
| --- | --- | --- | --- |
| First check / normal | < 5 GB | critical | Critical |
| First check / normal | ≥ 5 GB and < 10 GB | warning | Warning |
| First check / normal | ≥ 10 GB | normal | None |
| warning | < 5 GB | critical | Critical |
| warning | ≥ 5 GB and < 15 GB | warning | None |
| critical | < 15 GB | critical | None |
| warning / critical | ≥ 15 GB | normal | Recovered |
| normal | ≥ 15 GB | normal | None |

Severity stays at the highest observed level until recovery. In particular,
critical does not downgrade to warning at 5 GB. This prevents repeated alerts
when space fluctuates around either low-space threshold. The first healthy
check is silent. A read-only preview computes the transition from saved state
but does not consume it; repeated previews may show `transition: true`.
Changing thresholds re-evaluates the existing state on the next check, using
the new recovery threshold. Use the same options for manual and scheduled checks.

## Periodic macOS checks

```bash
# Preview a dedicated LaunchAgent: every 300 seconds and once on load.
./bin/awo disk launchd install / --interval-seconds 300

# Explicit installation. This starts checks with notifications enabled.
./bin/awo disk launchd install / --interval-seconds 300 --apply

# Preview removal, then explicitly stop/remove only this disk job.
./bin/awo disk launchd uninstall / --interval-seconds 300
./bin/awo disk launchd uninstall / --interval-seconds 300 --apply
```

`--warning-gb`, `--critical-gb`, `--recovery-gb` and `--state-dir` also apply to
`disk launchd`; the generated job stores their values as literal arguments.
`--interval-seconds` must be a positive integer. `--awo /absolute/path/bin/awo`
selects a stable installed checkout. The default points at the current checkout:
keep it available for the life of the job, or uninstall/reinstall from a stable
location before removing the worktree.

The job uses `StartInterval` and `RunAtLoad`, with a distinct label and plist:
`~/Library/LaunchAgents/com.awo.disk.<SHA-256-of-canonical-path>.plist`.
It cannot collide with the existing default `com.awo.watch` job, and no existing
plist is overwritten. Use the original path and all original options when
uninstalling. The canonical absolute path also supports removal after a mounted
volume disappears. Uninstall keeps notification state. To change settings,
uninstall with the old options and install with the new ones.

launchd skips interval firings during sleep or when that job is still running;
this is periodic checking, not continuous or real-time monitoring. The job runs
in the user's GUI domain. macOS notification settings and Focus may suppress
display even if `osascript` succeeds. `notified: true` means the notification
command succeeded, not that a person saw the banner.

## Persistence and failures

Default state directory:
`~/Library/Application Support/AWO/disk-watch/`. Override it with
`--state-dir /absolute/local/path` consistently across all invocations. Each
canonical path has a SHA-256-named `.json` state file and a persistent `.lock`
file. Locks are held only during a notifying check and automatically released
when the process exits. A leftover lock file does not mean a check is running.
Concurrent notifying checks for the same path/state directory are refused.

State contains schema version, local path, severity, free bytes, check time and
thresholds. A temporary file, flush/fsync and atomic replacement prevent partial
JSON writes. Missing paths, measurement failures, corrupt/unknown state, and
state write failures return an error without sending an alert. Corrupt state
is preserved for inspection; it is never silently reset. Restarts and reinstalls
reuse state. Removing state starts a new history and may alert again.

To prioritize avoiding repeated alerts, a transition is saved **before** invoking
`osascript`. A notification error or 15-second timeout returns exit code 1 and
`notification_error` in JSON, but that transition is not automatically retried.
A crash between saving and sending can therefore lose one notification.
There is no atomic transaction between a local file and Notification Center;
this design provides at most one send attempt per transition during ordinary
process restarts, not guaranteed delivery or power-loss durability. New state
transitions still notify normally. No network service or credentials are used.

`check` exits 0 for a successful measurement regardless of severity; automation
should inspect `level`. Operational/notification failures exit nonzero (argument
syntax errors use argparse's exit code 2). Background errors can be reproduced
with the same manual `disk check ... --notify --json` command; notification
delivery itself is not retried for an already saved transition.

## 한국어 빠른 안내

- `awo disk check 경로 --json`: 읽기 전용 조회. 알림·상태 변경 없음.
- `awo disk check 경로 --notify`: 상태 저장 및 전이 알림. 최초 정상은 조용히 저장.
- 기본값은 10GB 미만 경고, 5GB 미만 긴급, 15GB 이상 정상 회복입니다.
  긴급 상태는 15GB 회복까지 유지해 경계값 부근의 반복 알림을 막습니다.
- `--warning-gb`, `--critical-gb`, `--recovery-gb`로 기준을 조정합니다.
- `awo disk launchd install 경로 --interval-seconds 300`으로 미리 본 뒤
  `--apply`를 붙이면 5분 간격 감시를 설치합니다. 설치 직후에도 한 번 검사합니다.
- 해제는 같은 경로·옵션으로 `awo disk launchd uninstall ... --apply`를 실행합니다.
  기존 worktree 감시와 디스크 상태 파일은 유지됩니다.
- 상태를 먼저 저장하므로 재실행 중복을 방지하지만 알림 호출 실패·직전 종료 시
  해당 전이 알림은 자동 재시도하지 않습니다. 실제 배너는 macOS 알림 설정에 좌우됩니다.
