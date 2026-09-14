#!/usr/bin/env bash
# .env 에 정의한 값을 Maestro 에 주입해서 테스트를 실행한다.
#
#   ./scripts/run.sh                                  전체 워크스페이스 실행
#   ./scripts/run.sh .maestro/tests/smoke             특정 폴더만 실행
#   ./scripts/run.sh .maestro/tests/sdk/sdk_login_guest.yaml   특정 플로우만 실행
#   ./scripts/run.sh .maestro --include-tags=smoke    태그로 필터링
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
# -e 로 넘기는 대신 프로세스 환경 변수로 내보낸다. AI 검증에 쓰이는 MAESTRO_CLOUD_API_KEY 가
# 여기에 해당한다.
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

# 대상 디렉터리 안의 config.yaml 은 Maestro 가 자동으로 인식하므로 --config 를 넘기지 않는다.
exec maestro test "${ENV_ARGS[@]}" "$TARGET" "$@"
