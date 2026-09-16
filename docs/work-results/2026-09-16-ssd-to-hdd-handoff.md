# SSD → HDD 이전 인계 — 2026-09-16 KST

## 최종 결과 — 16:04 KST

**이전 종료: 96,884,484,712바이트(96.884GB), 30,327개 파일.**
상태는 `complete_with_preserved_exceptions`이며 아래의 이전 실행 중 기록은 역사적 체크포인트다.
현재 실행 중인 이전 worker는 없다. session 15859는 종료 코드 0으로 완료됐고,
그 후 검증용 session 88356도 종료 코드 0으로 완료됐다. 스크립트를 재실행하지 말 것.

- 계획에 포함한 전 파일의 복사 SHA-256과 HDD 재읽기 SHA-256이 일치한다.
  최종 대조에서 검증 기록 → 원본 정리 기록의 순서, 목적지 파일 존재/크기,
  기존 원본 경로 부재, 전체 바이트 및 파일 수가 일치함을 확인했다.
- 출발 SSD 여유는 **334.905GB → 455.862GB**, 전후 차이는 **120.957GB**다.
  논리 파일 내용 96.884GB와 달리 실제 할당 공간·메타데이터가 포함된 차이이며,
  동시 사용량의 영향도 있을 수 있다.
- 원본 보존 예외는 `백업/6. 후스토` 약 0.898GB와 `백업/데코퐁브랜드` 약 0.107GB다.
  전자는 접근 불가 PDF, 후자는 중복된 원본 디렉터리 항목 때문이다.
  HDD의 데코퐁브랜드는 부분 복사이며 `MIGRATION-INCOMPLETE.txt`로 표시했다.
- 모델 이미지 보존, APFS 모델 볼륨 마운트, 모델 링크, npm/uv/npx 및 임시 영상/uv 캐시
  6개 링크가 모두 유효함을 확인했다. 이들에 대한 새 실행 테스트나 이전은 하지 않았다.
- 작업 디렉터리의 FINAL-VALIDATION.json 및 HDD 루트의 MIGRATION-FINAL-VALIDATION.json에
  최종 대조 결과를 저장했다. HDD에 계획/저널/상태/설명 문서도 보존했다.
- 새 제품 코드 변경, 원격 push, PR/병합, worktree 정리는 하지 않았다.

## 목표와 승인

사용자가 중간 SSD의 영상·백업용 자료를 새 HDD로 옮겨 달라고 요청했다.
복사 및 SHA-256 검증을 마친 변경 없는 원본에 한해 SSD에서 제거한다.
외부 전송, 포맷, 볼륨 이름 변경, 앱/프로세스 종료, 실행 중인 모델·도구 이전은 하지 않는다.

## 확인된 저장소와 범위

- SSD: `/Volumes/My Passport`, ExFAT, UUID `F1C10B49-8F59-3A15-8CB8-745E6106ADE3`.
- HDD: `/Volumes/My Book`, ExFAT, UUID `F10BA045-3F02-3C51-A7CB-B75CAF1DD7AE`.
- 목적지: `/Volumes/My Book/Archives/My-Passport-20260916`.
- 총 30,407개 파일, 약 96.992GB. 사진, 구글드라이브 복사, 맥미니 임시 아카이브,
  백업 폴더의 하위 묶음 15개와 루트 AppleDouble 파일을 원래 구조대로 이전한다.
- `백업/6. 후스토` 전체 약 0.898GB는 보존한다. 하위 PDF 한 개가 디렉터리 목록에는
  있으나 stat/open 경로 해석이 실패한다. NFC 이름으로 접근해도 실패했다.
- AI 모델 sparsebundle과 연결 볼륨, 모델·도구 안내, 다른 미선정 폴더는 유지한다.
- 시작 전 lsof에서 선택된 경로를 연 프로세스 없음. My Passport는 USB 2.0,
  My Book은 허브 경유 USB 5Gbps. My Book 1GiB 연속 I/O 시험 2회 쓰기 198–210MB/s,
  읽기 213–216MB/s, 읽기 내용 검증 및 테스트 파일 제거 완료.

## 실행 및 원본 정리 조건

작업 디렉터리:
`/Users/koldeumaegmini/Library/Application Support/AWO/migrations/ssd-to-hdd-20260916T145207`

- `plan.json`: 소스의 전체 파일명·크기·inode·수정 시각·변경 시각, 폴더별 계획.
- `migrate.py`: 이 작업 전용 실행 스크립트. 저장소 제품 코드와 독립적이다.
- `STATUS.json`: 실제 현재 단계/바이트/파일 수/완료 묶음/오류/PID. 이 파일이 완료 여부의 기준.
- `journal.jsonl`: 복사 시 SHA-256, HDD 재읽기 검증, 원본 제거 이력.
- exec session ID **32039**에서 `/usr/bin/caffeinate -i /usr/bin/python3 -u .../migrate.py` 실행 시작.
  현재 턴 도구로 `write_stdin`을 사용해 결과를 수집할 수 있다.
- 대상 파일은 exclusive 생성하여 덮어쓰지 않는다. 묶음 전체의 쓰기를 flush한 뒤
  OS 캐시를 끈 HDD 재읽기로 SHA-256 검증한다. 디스크 UUID, 열린 파일, 소스 파일 목록과
  fingerprint를 재검사한 뒤 원본 개별 unlink 및 빈 폴더 rmdir만 실행한다.
- 오류 시 해당 위치를 기록하고 중단한다. 검증되지 않은 원본은 제거하지 않는다.
  이미 끝난 묶음은 HDD에 있으며 원본이 제거됐을 수 있으므로 무작정 재실행하지 않는다.
- 완료 시 상태/계획/저널을 HDD에도 복사한다. 이전 안내 문서의 옛 절대 경로는 역사적
  기록으로 유지되며, 새 HDD의 `MIGRATION-README.txt`가 이번 이동을 설명한다.

## 다음 작업

1. `STATUS.json`과 프로세스 생존을 확인. 중복 작업을 시작하지 않는다.
2. 실행 중이면 진행 상황을 주기적으로 사용자에게 알리고 완료/오류를 수집한다.
3. 오류라면 소스·목적지·journal을 먼저 대조하여 보존하며 복구한다.
4. 완료 시 파일 수/바이트/해시 검증 수와 SSD 확보 공간, 모델/도구 연결 보존을 확인한다.
5. 이 인계 문서에 최종 결과를 덧붙이고 사용자에게 목적지·이동량·남은 예외를 보고한다.

## 14:58 재개 체크포인트

- 최초 worker(session 32039)는 아카이브를 복사한 뒤 AppleDouble 메타데이터 1건의
  해시 불일치를 감지해 원본 정리 전에 중단했다. 일반 파일 생성 시 기존 목적지의
  `._Aside-1.0.910.1.dmg` 내용이 macOS에 의해 초기화된 것으로 확인했다.
  해당 소스 파일의 해시는 처음 기록과 동일했으며 원본은 보존됐다.
- 원본 메타데이터 파일을 마지막에 복사하고, 목적지 디렉터리 시각도 검증 전에
  적용하도록 수정했다. 이미 복사한 일반 파일은 기록된 원본 해시와 최종 재읽기로
  검증하여 재사용했으며 AppleDouble만 원본에서 복구했다.
- `resume.py`가 exec session **93894**에서 실행 중이다. 예전 32039는 종료됐다.
  `STATUS-before-appledouble-repair.json`에 중단 당시 상태를 보존했다.
- 맥미니 임시 아카이브 3.497GB는 전체 검증 및 원본 정리가 완료됐으며,
  `구글드라이브 복사` 9.509GB의 복사가 시작됐다. 현재 실제 상태는 STATUS.json 참조.
- 재개 스크립트도 실행 중 중복 호출하지 말 것. 다음 실패가 있으면 오류 종류와
  journal을 확인하고 적절한 복구를 새로 판단해야 한다.

## Git / 감시 상태

### 15:32 체크포인트

exec session 93894의 resume.py가 계속 실행 중이다. 임시 아카이브·구글드라이브 복사·사진
묶음 **54.650GB / 14,520개 파일**의 SHA-256 검증 및 SSD 원본 정리가 완료됐다.
현재 백업/0. 브랜드수입부터 남은 백업 묶음 약 42.342GB를 처리 중이다.
재개 이후 추가 오류는 없었다. 다음 단계와 실제 수치는 작업 디렉터리 STATUS.json을 참조한다.

### 원본 목록 이상 보존 후 재개

- 63.163GB의 검증·원본 정리가 끝난 뒤 `백업/데코퐁브랜드`에서 FileExistsError로 중단.
  원본 디렉터리 열거 결과에 완전히 동일한 경로·inode·크기·시각을 갖는 DWG 항목이
  두 번 포함돼 있었다. 다른 원본 항목을 안전하게 구별할 수 없으므로 이 묶음 전체
  약 0.107GB/80개 열거 항목을 SSD에 보존한다. 파일시스템 수리나 원본 이름 변경은 하지 않았다.
- HDD의 해당 부분 복사 폴더에 MIGRATION-INCOMPLETE.txt를 추가했다. 이 폴더를 완전한
  아카이브로 간주하지 말 것. 원본 제거는 전혀 실행되지 않았다.
- 이전 plan/status는 `plan-before-inventory-anomaly.json`,
  `STATUS-before-inventory-anomaly.json`에 보존. 현재 plan은 이 묶음을 deferred_units로
  분리해 **96.884GB / 30,327개 파일**로 갱신했다.
- 현재 worker는 **continue_remaining.py / exec session 15859**다. 93894는 종료됐다.
  untouched 나머지 묶음만 이어서 복사·검증·원본 정리한다.
- 완료 상태 이름은 `complete_with_preserved_exceptions`. 예외 2개 묶음
  (`6. 후스토`, `데코퐁브랜드`)은 원본 보존이며, 제품 버그나 무조건 재시도 대상으로 취급하지 않는다.

제품 구현 브랜치 `jakeparkcolde/disk-space-watch`, 제품 커밋 `9590b86`.
이번 이전 전 작업 트리는 깨끗했으며, 이 인계 노트는 이후 새로 추가됐다.
기존 디스크 감시는 고정 배포 경로의 launchd 작업으로 계속 운영하며 이 이전에서는 변경하지 않는다.
Git push/PR/merge/cleanup은 하지 않는다.

## 복사해서 이어가기

“docs/work-results/2026-09-16-ssd-to-hdd-handoff.md의 최종 결과와
~/Library/Application Support/AWO/migrations/ssd-to-hdd-20260916T145207/FINAL-VALIDATION.json을
읽으세요. 96.884GB/30,327개 파일 이전은 완료됐으므로 worker를 다시 실행하지 마세요.
HDD 목적지는 /Volumes/My Book/Archives/My-Passport-20260916입니다.
SSD에 유지한 AI 모델/도구와 파일 목록 이상으로 보존한 백업/6. 후스토·데코퐁브랜드를
보호하세요. 추가 이전이나 파일시스템 수리는 새 사용자 요청의 범위를 확인하세요.”
