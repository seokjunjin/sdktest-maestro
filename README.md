# sdktest-maestro

[Maestro](https://maestro.dev/) 를 사용해서 SDK 의 앱 내부 흐름(E2E)을 자동으로 검증하는 테스트 저장소입니다. 테스트 플로우는 사람이 읽을 수 있는 YAML 로 작성하고, Maestro CLI 로 실제 기기와 시뮬레이터에서 실행합니다.

Claude Code 에서는 Maestro MCP 서버를 통해 기기 화면을 직접 조회하면서 플로우를 작성하고 곧바로 실행해 볼 수 있습니다.

## 요구 사항

- Java 17 이상 (`JAVA_HOME` 이 해당 설치 경로를 가리켜야 합니다)
- Maestro CLI 2.x
- 안드로이드는 adb 로 인식되는 실기기 또는 에뮬레이터, iOS 는 Xcode 및 Command Line Tools

## 최초 설정

```bash
# 1. Maestro CLI 설치 (이미 설치되어 있다면 건너뜁니다)
curl -fsSL "https://get.maestro.mobile.dev" | bash
export PATH="$PATH:$HOME/.maestro/bin"

# 2. 환경 변수 파일 준비 후 APP_ID 등을 채웁니다
cp .env.example .env

# 3. Claude Code 에 Maestro MCP 서버를 등록합니다
claude mcp add maestro -- maestro mcp

# 4. 사전 조건을 점검합니다
./scripts/doctor.sh
```

`.env` 는 커밋되지 않습니다. 대상 앱의 패키지 이름과 테스트 계정 정보는 이 파일에만 두고, 플로우 YAML 에는 `${APP_ID}` 처럼 환경 변수로 참조합니다.

대상 앱이 Unity 로 렌더링되는 화면을 가지고 있다면 `.env` 의 `MAESTRO_CLOUD_API_KEY` 도 채워야 합니다. 자세한 이유는 아래 [Unity 화면을 검증하는 방법](#unity-화면을-검증하는-방법)에 적었습니다.

## 테스트 실행

```bash
# 워크스페이스 전체 실행
./scripts/run.sh

# 스모크 테스트만 실행
./scripts/run.sh .maestro --include-tags=smoke

# 특정 플로우 하나만 실행
./scripts/run.sh .maestro/tests/smoke/app_launch.yaml

# 화면 요소를 눈으로 확인하면서 플로우를 작성할 때
maestro studio
```

## 디렉터리 구조

```
.maestro/
├── config.yaml              워크스페이스 전역 설정 (탐색 경로, 전역 태그, 플랫폼 옵션)
├── tests/
│   ├── smoke/               앱이 실행되는지 확인하는 최소 검증
│   └── sdk/                 SDK 기능별 검증 플로우
├── subflows/                runFlow 로 호출되는 공용 서브플로우
└── utils/                   플로우에서 사용하는 자바스크립트 헬퍼
scripts/
├── run.sh                   .env 를 주입해서 Maestro 를 실행
└── doctor.sh                실행 전 사전 조건 점검
docs/
├── writing-flows.md         플로우 작성 규칙과 자주 쓰는 명령
└── ci-github-actions.md     깃허브 액션 연동 예시
```

Maestro 는 지정한 디렉터리의 최상단 파일만 실행하고 하위 폴더는 무시합니다. 이 저장소는 `config.yaml` 의 `flows: ["tests/**"]` 설정으로 `tests/` 하위 전체를 탐색 대상에 포함시켰고, `subflows/` 는 탐색 경로에서 제외되어 있으므로 서브플로우가 단독으로 실행되는 일은 없습니다.

## 태그 정책

| 태그 | 의미 |
| --- | --- |
| `smoke` | 앱 실행처럼 항상 통과해야 하는 최소 검증 |
| `sdk` | SDK 기능 검증 |
| `login` | 로그인 및 계정 연동 관련 검증 |
| `wip` | 작성 중. `config.yaml` 의 `excludeTags` 에 포함되어 실행되지 않습니다 |

플로우를 완성하면 `tags` 에서 `wip` 를 제거해 주세요.

## Unity 화면을 검증하는 방법

이 앱의 화면은 두 종류로 나뉘고, 종류에 따라 다루는 방법이 완전히 다릅니다. 새 플로우를 작성할 때는 먼저 `inspect_screen` 으로 어느 쪽인지 확인해 주세요.

**DevPlay SDK 가 그리는 화면은 네이티브입니다.** 나이 입력과 약관 동의는 `com.devplay.provisioning.presentation.view` 의 별도 액티비티이고, IDP 로그인 창과 게스트 로그인 주의사항 창은 Unity 표면 위에 올라오는 네이티브 화면입니다. 뷰 계층에 문구와 `signin_guest`, `btn_guest_ok`, `btn_plus`, `btn_ok` 같은 식별자가 그대로 노출되므로, 일반적인 앱과 똑같이 선택자로 조작하고 `assertVisible` 로 검증하면 됩니다.

**게임 본체가 그리는 화면은 Unity 입니다.** DevPlay SDK Configuration 화면과 로비 화면은 무엇이 표시되든 뷰 계층에 렌더링 표면인 `unitySurfaceView` 하나만 노출됩니다. 화면 속 문구는 접근성 트리에 전혀 나타나지 않으므로, 조작은 `tapOn` 의 `point` 인자에 백분율 좌표를 지정해야 하고 화면 내용은 뷰 계층으로 검증할 수 없습니다. 이때 지켜야 하는 제약들은 [docs/writing-flows.md](docs/writing-flows.md) 의 "Unity 화면을 좌표로 조작하기" 절에 정리해 두었습니다.

Unity 화면의 내용까지 검증하려면 스크린샷을 판정에 사용하는 `assertWithAI` 가 필요합니다. 이 명령은 스크린샷을 Maestro Cloud 로 전송하므로 기본적으로 꺼 두었고, `.env` 의 `AI_ASSERT` 를 `true` 로 바꾸고 `MAESTRO_CLOUD_API_KEY` 를 함께 설정할 때만 동작합니다. 키는 `maestro login` 으로 발급받거나 Maestro Cloud 콘솔에서 확인할 수 있습니다.

켜기 전에 무엇이 전송되는지 확인해 주세요. SDK Configuration 화면에는 SDK APIKey 가, 로비 화면에는 내부 게임 엔드포인트 주소가 함께 찍힙니다. 끈 상태에서도 두 화면의 스크린샷은 실행 결과 폴더에 증적으로 남습니다. 다만 끈 상태에서는 Environment 가 실제로 QA 로 선택되었는지 확인하지 못하므로, 좌표가 어긋나 Dev 환경으로 실행되어도 플로우는 그대로 통과합니다.

## 기존 devplay-auto-qa 와의 관계

`devplay-auto-qa` 는 adb 를 직접 호출해서 앱 설치와 삭제 등 기기 프로비저닝을 자동화합니다. 반면 이 저장소는 앱이 설치된 다음의 UI 조작과 검증을 담당합니다. 두 작업의 성격이 다르기 때문에 저장소를 분리했습니다.

## 참고 문서

- [Maestro 공식 문서](https://docs.maestro.dev/)
- [Maestro MCP 서버](https://docs.maestro.dev/get-started/maestro-mcp)
- [워크스페이스 설정 레퍼런스](https://docs.maestro.dev/reference/workspace-configuration)
