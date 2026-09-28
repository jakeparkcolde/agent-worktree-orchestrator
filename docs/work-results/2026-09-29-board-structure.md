# 구조화 작업판 후속 결과 / 2026-09-29

기준 커밋 b657839, 같은 work-lifecycle 목표의 후속 개선. 코드/시험 완료 후 동결했다.

- 기존 board 조회/JSON 계약을 변경하지 않고 순수 텍스트 renderer를 scripts/awo_board.py로 분리.
- 조회 범위 프로젝트/실제 폴더/agent 집계와 전체 환경 세션/경고를 명시 구분.
- 열린 작업/이어갈 작업/아이디어/보관·완료/확인할 연결/지시 거점으로 분류, 빈 그룹 생략.
- 창 연결을 실행 중으로 표현하지 않음. 정상 legacy 확인필요 상태와 실제 identity 실패 구별.
- 미등록 목표 추론 없이 basename 보조 표시. 거점 별도 그룹.
- 기본 ID/절대경로/cleanup 명령 숨김, --details에 유지. 한국어 셀 너비 기준 줄바꿈.
- 자동 next·상태 미기록 설명은 그룹별 1회, 사용자 next 유지. 거점은 프로젝트별 한 줄.
- 외부 의존성/UI/색 필수 사용 없음. 운영 metadata/세션 변경 없음. 커밋/권한 확대 시도 없음.

검증: 순수 renderer 6 tests OK (0.009초), tests/test_cli.sh OK,
기존 test_light_board_korean_labels_and_actual_wip 1 test OK (1.353초), git diff --check OK.
전체 make test/lint는 이번 작은 renderer 변경에 재실행하지 않았다. 총괄이 추가 표적 시험과
실제 전체 출력 검증을 수행한다. worker는 운영 전체 board를 조회하지 않았다.

사용: awo board / awo board --details / awo board --project KEY / awo board --json.
총괄이 커밋한다. 변경 파일은 bin/awo, scripts/awo_lifecycle.py, scripts/awo_board.py,
tests/test_board_renderer.py, tests/test_cli.sh, docs/work-lifecycle.md, 이 결과 문서다.
다음: 동결된 변경의 실제 출력 검토 → 총괄의 명시 파일 커밋. 병합/푸시 없음.
