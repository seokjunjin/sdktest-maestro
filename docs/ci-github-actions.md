# 깃허브 액션 연동 예시

아래 워크플로 파일은 저장소에 커밋되어 있지 않습니다. 현재 사용 중인 `gh` CLI 토큰에 `workflow` 스코프가 없어서 `.github/workflows/` 경로의 파일을 푸시할 수 없기 때문입니다. CI 를 붙이려면 다음 중 하나를 먼저 처리해 주세요.

- `gh auth refresh -h github.com -s workflow` 명령으로 토큰에 스코프를 추가합니다.
- 또는 깃허브 웹 화면에서 직접 파일을 추가합니다.

## 안드로이드 에뮬레이터에서 실행하기

`.github/workflows/maestro-android.yml` 로 저장합니다.

```yaml
name: Maestro Android E2E

on:
  workflow_dispatch:
  pull_request:

jobs:
  android:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Maestro CLI 설치
        run: |
          curl -Ls "https://get.maestro.mobile.dev" | bash
          echo "$HOME/.maestro/bin" >> "$GITHUB_PATH"

      # 테스트 대상 APK 를 준비하는 단계입니다.
      # 앱을 빌드하는 저장소가 따로 있다면 actions/download-artifact 등으로 받아 오세요.
      - name: 대상 APK 준비
        run: echo "APK 를 ./builds/app.apk 경로로 가져오는 단계를 채워 주세요."

      - name: 에뮬레이터에서 테스트 실행
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 33
          arch: x86_64
          disable-animations: true
          script: |
            adb install -r ./builds/app.apk
            maestro test -e APP_ID=${{ secrets.APP_ID }} .maestro --include-tags=sdk

      - name: 실패 시 산출물 업로드
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: maestro-debug-output
          path: ~/.maestro/tests/
```

## 필요한 시크릿

| 이름 | 설명 |
| --- | --- |
| `APP_ID` | 테스트 대상 앱의 패키지 이름 |
| `TEST_ACCOUNT_ID`, `TEST_ACCOUNT_PW` | 로그인 검증에 사용할 계정 정보 (해당 플로우를 CI 에서 실행하는 경우에만 필요합니다) |

공개 저장소이므로 패키지 이름과 계정 정보는 반드시 시크릿으로 관리하고, 워크플로 파일이나 플로우 YAML 에 직접 적지 않습니다.

## Maestro Cloud 를 사용하는 경우

실기기 병렬 실행이 필요하면 [Maestro Cloud 의 깃허브 액션](https://docs.maestro.dev/maestro-cloud/ci-cd-integration/github-actions)을 사용할 수 있습니다. 이 방식은 별도의 유료 플랜과 API 키가 필요합니다.
