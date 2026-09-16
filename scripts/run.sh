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
# MAESTRO_ 로 시작하는 항목은 플로우에서 참조하는 변수가 아니라 Maestro CLI 자체의 설정이므로,
# -e 로 넘기는 대신 프로세스 환경 변수로 내보낸다. AI 검증에 쓰이는 MAESTRO_CLOUD_API_KEY 와
# 스위트 이름을 지정하는 MAESTRO_TEST_SUITE_NAME 이 여기에 해당한다.
ENV_ARGS=()
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  [[ -z "$key" || -z "$value" ]] && continue
  if [[ "$key" == MAESTRO_* ]]; then
    export "$key=$value"
    continue
  fi
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

# 실행마다 reports/<시각>/ 을 만들어 JUnit 결과와 증적을 한곳에 모은다. 이 폴더는 커밋
# 대상이 아니며, 결과 페이지가 이 경로를 증적 링크로 참조한다.
RUN_DIR="$REPO_ROOT/reports/$(date +%Y-%m-%d_%H%M%S)"
JUNIT_XML="$RUN_DIR/junit.xml"
mkdir -p "$RUN_DIR"

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
python3 "$REPO_ROOT/scripts/build-report-page.py" ||
  echo "결과 페이지를 만들지 못했습니다. 테스트 결과는 위의 출력을 확인해 주세요." >&2

echo "이번 실행의 결과와 증적은 $RUN_DIR 에 있습니다."
exit $MAESTRO_STATUS
