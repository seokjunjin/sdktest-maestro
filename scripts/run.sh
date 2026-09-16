#!/usr/bin/env bash
# .env 에 정의한 값을 Maestro 에 주입해서 테스트를 실행한다.
#
#   ./scripts/run.sh                                  전체 워크스페이스 실행
#   ./scripts/run.sh .maestro/tests/sdk                특정 폴더만 실행
#   ./scripts/run.sh .maestro/tests/sdk/sdk_login_guest.yaml   특정 플로우만 실행
#   ./scripts/run.sh .maestro --include-tags=login     태그로 필터링
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$PATH:$HOME/.maestro/bin"

if ! command -v maestro >/dev/null 2>&1; then
  echo "maestro 명령을 찾을 수 없습니다. ./scripts/doctor.sh 를 먼저 실행해 주세요." >&2
  exit 1
fi

ENV_FILE="$REPO_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo ".env 파일이 없습니다. 다음 명령으로 만든 뒤 값을 채워 주세요." >&2
  echo "  cp .env.example .env" >&2
  exit 1
fi

# .env 의 각 항목을 maestro 의 -e 인자로 변환한다. 값이 비어 있는 항목은 건너뛴다.
# MAESTRO_ 로 시작하는 항목과 REPORTS_DIR 은 플로우에서 참조하는 변수가 아니라 도구 쪽
# 설정이므로, -e 로 넘기는 대신 프로세스 환경 변수로 내보낸다. AI 검증에 쓰이는
# MAESTRO_CLOUD_API_KEY, 스위트 이름을 지정하는 MAESTRO_TEST_SUITE_NAME, 결과를 둘 위치를
# 정하는 REPORTS_DIR 이 여기에 해당한다.
ENV_ARGS=()
APP_ID_VALUE=""
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  [[ -z "$key" || -z "$value" ]] && continue
  if [[ "$key" == MAESTRO_* || "$key" == "REPORTS_DIR" ]]; then
    export "$key=$value"
    continue
  fi
  [[ "$key" == "APP_ID" ]] && APP_ID_VALUE="$value"
  ENV_ARGS+=(-e "$key=$value")
done <"$ENV_FILE"

if [[ ${#ENV_ARGS[@]} -eq 0 ]]; then
  echo ".env 에 채워진 값이 없습니다. 최소한 APP_ID 는 설정해야 합니다." >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  TARGET="$1"
  shift
else
  TARGET="$REPO_ROOT/.maestro"
fi

# 결과를 둘 위치는 .env 의 REPORTS_DIR 로 정한다. 값이 없으면 저장소 안의 reports/ 를
# 쓴다. 여러 사람이 결과를 모으려면 결과 전용 저장소를 받은 경로를 넣으면 된다.
REPORTS_DIR="${REPORTS_DIR:-$REPO_ROOT/reports}"
# ~ 나 $HOME 이 들어 있을 수 있으므로 펼친다.
REPORTS_DIR="$(eval echo "$REPORTS_DIR")"

# 실행마다 <시각>-<사용자>/ 를 만들어 JUnit 결과와 증적을 한곳에 모은다. 사용자 이름을
# 붙이는 이유는 여러 사람이 결과를 한 저장소에 모을 때 폴더가 겹치지 않게 하기 위한 것이다.
RUN_DIR="$REPORTS_DIR/$(date +%Y-%m-%d_%H%M%S)-$(id -un)"
JUNIT_XML="$RUN_DIR/junit.xml"
mkdir -p "$RUN_DIR"

# 테스트 대상 앱의 버전과 기기 모델명을 기록한다. JUnit 결과에도 commands.json 에도 이
# 정보가 없다. Maestro 가 JUnit 에 적는 device 속성은 adb 시리얼 번호(예: R3KL205L26F)라서
# 어느 기종인지 알 수 없다. 실행 시점에 읽어 두어야 의미가 있으므로 테스트 전에 조회한다.
#
# 안드로이드 전용이다. adb 가 없거나 기기가 여러 대여서 대상이 정해지지 않거나 앱이 설치되어
# 있지 않으면 조용히 건너뛴다. 결과 페이지는 이 경우 해당 칸을 비워 두거나 시리얼 번호를
# 대신 보여준다.
if command -v adb >/dev/null 2>&1; then
  DEVICE_MODEL="$(adb shell getprop ro.product.model 2>/dev/null | tr -d '\r')"
  DEVICE_RELEASE="$(adb shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')"
  APP_VERSION_NAME=""
  APP_VERSION_CODE=""
  if [[ -n "$APP_ID_VALUE" ]]; then
    PKG_DUMP="$(adb shell dumpsys package "$APP_ID_VALUE" 2>/dev/null || true)"
    APP_VERSION_NAME="$(sed -n 's/.*versionName=\([^ ]*\).*/\1/p' <<<"$PKG_DUMP" | head -1)"
    APP_VERSION_CODE="$(sed -n 's/.*versionCode=\([0-9]*\).*/\1/p' <<<"$PKG_DUMP" | head -1)"
  fi
  if [[ -n "$APP_VERSION_NAME$APP_VERSION_CODE$DEVICE_MODEL" ]]; then
    printf '{\n  "app_version_name": "%s",\n  "app_version_code": "%s",\n  "device_model": "%s",\n  "android_release": "%s"\n}\n' \
      "$APP_VERSION_NAME" "$APP_VERSION_CODE" "$DEVICE_MODEL" "$DEVICE_RELEASE" \
      >"$RUN_DIR/meta.json"
    echo "대상 기기: ${DEVICE_MODEL:-알 수 없음} (Android ${DEVICE_RELEASE:-?})"
    echo "대상 앱 버전: ${APP_VERSION_NAME:-?}(${APP_VERSION_CODE:-?})"
  else
    echo "기기 정보와 앱 버전을 읽지 못했습니다. 결과 페이지의 해당 칸이 비워집니다." >&2
  fi
fi

# 대상 디렉터리 안의 config.yaml 은 Maestro 가 자동으로 인식하므로 --config 를 넘기지 않는다.
# 테스트가 실패해도 결과를 기록해야 하므로, set -e 로 중단되지 않게 종료 코드를 받아 둔다.
MAESTRO_STATUS=0
maestro test \
  "${ENV_ARGS[@]}" \
  --format JUNIT \
  --output "$JUNIT_XML" \
  --test-output-dir "$RUN_DIR" \
  --test-suite-name "${MAESTRO_TEST_SUITE_NAME:-SDK 테스트 자동화}" \
  "$TARGET" "$@" || MAESTRO_STATUS=$?

# 결과 페이지를 다시 만든다. 이 페이지는 reports/ 에 쌓인 모든 실행을 함께 보여주므로,
# 실행마다 갱신해야 최신 결과가 반영된다. 페이지 생성이 실패해도 종료 코드는 유지한다.
python3 "$REPO_ROOT/scripts/build-report-page.py" --reports-dir "$REPORTS_DIR" ||
  echo "결과 페이지를 만들지 못했습니다. 테스트 결과는 위의 출력을 확인해 주세요." >&2

echo "이번 실행의 결과와 증적은 $RUN_DIR 에 있습니다."
echo "결과 페이지: $REPORTS_DIR/index.html"
exit $MAESTRO_STATUS
