# 플로우 작성 규칙과 자주 쓰는 명령

## 파일 구조

플로우 파일은 설정 블록과 명령 블록을 `---` 로 구분합니다.

```yaml
appId: ${APP_ID}          # 필수. 대상 앱의 패키지 이름 또는 번들 식별자
name: 게스트 로그인 검증   # 선택. 실행 결과에 표시되는 이름
tags:                     # 선택. 실행 대상을 필터링하는 태그
  - sdk
env:                      # 선택. 이 플로우에서만 사용하는 환경 변수
  RETRY_COUNT: 3
---
- launchApp
- tapOn: "로그인"
- assertVisible: "환영합니다"
```

## 자주 쓰는 명령

| 명령 | 용도 |
| --- | --- |
| `launchApp` | 앱을 실행합니다. `clearState: true` 옵션으로 상태를 초기화할 수 있습니다 |
| `clearState` | 앱의 저장 데이터를 삭제합니다 |
| `tapOn` | 텍스트, `id`, `point` 등으로 지정한 요소를 탭합니다 |
| `inputText` | 현재 포커스된 입력란에 문자열을 입력합니다 |
| `assertVisible` / `assertNotVisible` | 요소의 표시 여부를 검증합니다 |
| `extendedWaitUntil` | 조건이 충족될 때까지 최대 `timeout` 밀리초 동안 기다립니다 |
| `runFlow` | 서브플로우를 호출합니다. `when` 으로 조건 분기, `env` 로 인자 전달이 가능합니다 |
| `evalScript` | 자바스크립트 표현식을 실행합니다 |
| `takeScreenshot` | 스크린샷을 남깁니다. 실패 원인 추적에 유용합니다 |

전체 명령 목록은 Maestro MCP 의 `cheat_sheet` 도구나 [공식 레퍼런스](https://docs.maestro.dev/reference/commands)에서 확인할 수 있습니다.

## 환경 변수

`.env` 의 값은 `scripts/run.sh` 가 `-e KEY=VALUE` 형태로 전달합니다. 플로우에서는 `${KEY}` 로 참조하고, 기본값이 필요하면 `${KEY || "기본값"}` 처럼 자바스크립트 표현식을 사용합니다.

`appId` 에도 환경 변수 치환이 적용됩니다. 다만 콘솔 출력의 라벨에는 치환되기 전의 문자열이 그대로 표시되므로, 로그에 `${APP_ID}` 가 보이더라도 실제로는 값이 적용된 상태입니다.

## 태그로 실행 범위를 조절하기

같은 플래그 안에 여러 태그를 나열하면 OR 조건으로 동작하고, `--include-tags` 와 `--exclude-tags` 를 함께 쓰면 두 그룹 사이에는 AND 조건이 적용됩니다.

```bash
./scripts/run.sh .maestro --include-tags=smoke,sdk
./scripts/run.sh .maestro --include-tags=sdk --exclude-tags=login
```

`config.yaml` 의 `excludeTags` 에 정의한 태그는 명령행 플래그와 무관하게 항상 제외됩니다. 이 저장소에서는 `wip` 가 여기에 해당합니다.

## 안정적인 플로우를 위한 권장 사항

- 화면 문구는 변경되기 쉬우므로, 가능하면 `id` 로 요소를 지정합니다.
- 네트워크 응답을 기다려야 하는 지점에는 `extendedWaitUntil` 을 사용하고 `timeout` 을 충분히 잡습니다.
- 로그인처럼 여러 테스트에서 반복되는 절차는 서브플로우로 분리합니다.
- 검증 실패 지점 직전에 `takeScreenshot` 을 넣어 두면 원인을 파악하기 쉬워집니다.
