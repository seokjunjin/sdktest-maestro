# 이 저장소에서 작업할 때의 지침

Maestro YAML 플로우로 SDK 의 앱 내부 흐름을 검증하는 저장소입니다.

## 플로우를 작성하는 순서

1. `maestro list-devices` 또는 Maestro MCP 의 `list_devices` 로 대상 기기를 확인합니다.
2. 화면 요소를 추측하지 말고 `inspect_screen` 으로 실제 뷰 계층을 조회한 뒤 식별자를 확정합니다.
3. `run` 도구로 인라인 YAML 을 짧게 실행해서 동작을 확인하고, 검증이 끝난 다음에 파일로 저장합니다.
4. Maestro 명령 문법이 확실하지 않으면 `cheat_sheet` 도구를 먼저 호출합니다.

## 규칙

- `appId` 는 항상 `${APP_ID}` 로 작성합니다. 패키지 이름을 파일에 직접 적지 않습니다.
- 계정 정보와 환경 구분값도 `.env` 에 두고 환경 변수로 참조합니다. 이 저장소는 공개 저장소이므로 내부 식별자와 자격 증명이 커밋되면 안 됩니다.
- 새 플로우는 `tags` 에 `wip` 를 붙여서 시작하고, 실제 기기에서 통과하는 것을 확인한 뒤 제거합니다.
- 여러 플로우에서 반복되는 동작은 `.maestro/subflows/` 로 분리하고 `runFlow` 로 호출합니다.
- 고정 대기(`- waitForAnimationToEnd` 의 남용이나 임의의 sleep)보다 `extendedWaitUntil` 로 조건을 기다립니다.
- 테스트를 추가하면 `README.md` 의 태그 정책 표를 함께 갱신합니다.

## 자주 쓰는 명령

```bash
./scripts/doctor.sh                             # 실행 전 사전 조건 점검
./scripts/run.sh                                # 전체 실행
./scripts/run.sh .maestro --include-tags=login   # 태그 필터링
maestro studio                                  # 화면 요소 탐색용 GUI
```

## 검증 방법

플로우를 수정했다면 실제로 실행해서 통과를 확인한 다음 보고합니다. 기기가 연결되어 있지 않아 실행할 수 없다면, 실행하지 못했다는 사실을 명시합니다.
