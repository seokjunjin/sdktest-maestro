#!/usr/bin/env bash
# 이 저장소를 처음 받은 사람이 테스트를 실행할 수 있는 상태까지 준비한다.
#
# doctor.sh 는 조건을 점검만 하고, 이 스크립트는 없는 것을 설치하고 .env 를 만든다.
# 여러 번 실행해도 이미 준비된 항목은 건너뛰므로 안전하다.
#
#   ./scripts/setup.sh                                준비 상태를 확인하고 필요한 것을 설치한다
#   ./scripts/setup.sh --app-id <값> --sdk-env <값>   .env 값을 인자로 넘긴다
#
# 관리자 암호가 필요한 설치는 하지 않는다. Maestro 는 사용자 홈(~/.maestro)에만 설치되고,
# Java 와 adb 는 설치 명령만 안내한다. 이 둘은 설치 위치와 방식이 환경마다 달라서 임의로
# 건드리면 기존 개발 환경을 망칠 수 있기 때문이다.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$PATH:$HOME/.maestro/bin"
STATUS=0

ARG_APP_ID=""
ARG_SDK_ENV=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) ARG_APP_ID="${2:-}"; shift 2 ;;
    --sdk-env) ARG_SDK_ENV="${2:-}"; shift 2 ;;
    -h | --help)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "알 수 없는 인자입니다: $1" >&2; exit 1 ;;
  esac
done

fail() {
  echo "  [실패] $1"
  STATUS=1
}

ok() {
  echo "  [정상] $1"
}

note() {
  echo "  [안내] $1"
}

# java -version 의 출력에서 주 버전만 뽑는다. 예전 표기(1.8.0)와 현재 표기(17.0.9)를 모두 받는다.
java_major_version() {
  local line version
  line="$(java -version 2>&1 | head -1)" || return 1
  version="$(sed -n 's/.*version "\([0-9][0-9.]*\).*/\1/p' <<<"$line")"
  [[ -z "$version" ]] && return 1
  [[ "$version" == 1.* ]] && version="${version#1.}"
  echo "${version%%.*}"
}

echo "1. 운영체제"
if [[ "$(uname -s)" == "Darwin" ]]; then
  ok "macOS 입니다."
else
  note "$(uname -s) 입니다. 이 저장소는 macOS 에서 확인했습니다. 리눅스에서도 대체로 동작하지만"
  note "       Homebrew 설치 안내는 맞지 않으므로 각 배포판의 방법을 쓰세요."
fi

echo "2. Java 17 이상"
if command -v java >/dev/null 2>&1 && JAVA_MAJOR="$(java_major_version)"; then
  if [[ "$JAVA_MAJOR" -ge 17 ]]; then
    ok "Java $JAVA_MAJOR 이 설치되어 있습니다."
  else
    fail "Java $JAVA_MAJOR 은 너무 낮습니다. Maestro 는 17 이상을 요구합니다."
    note "       brew install --cask temurin"
  fi
else
  fail "Java 를 찾을 수 없습니다."
  note "       brew install --cask temurin"
  note "       Homebrew 가 없으면 https://adoptium.net 에서 내려받으세요."
fi

echo "3. Maestro CLI"
if command -v maestro >/dev/null 2>&1; then
  ok "버전 $(maestro --version 2>/dev/null | tail -1)"
else
  echo "  [설치] Maestro 가 없어 공식 설치 스크립트를 실행합니다. 홈 디렉터리에만 설치됩니다."
  if curl -fsSL "https://get.maestro.mobile.dev" | bash; then
    export PATH="$PATH:$HOME/.maestro/bin"
    if command -v maestro >/dev/null 2>&1; then
      ok "설치했습니다. 버전 $(maestro --version 2>/dev/null | tail -1)"
      note "       새 터미널에서도 쓰려면 아래 한 줄을 ~/.zprofile 에 추가하세요."
      note '       export PATH="$PATH:$HOME/.maestro/bin"'
    else
      fail "설치했지만 실행 파일을 찾지 못했습니다. 새 터미널에서 다시 시도해 주세요."
    fi
  else
    fail "설치에 실패했습니다. 사내 네트워크에서 차단되었는지 확인해 주세요."
  fi
fi

echo "4. 안드로이드 adb"
if command -v adb >/dev/null 2>&1; then
  ok "$(adb --version 2>/dev/null | head -1)"
else
  fail "adb 를 찾을 수 없습니다. 기기를 인식하려면 필요합니다."
  note "       brew install --cask android-platform-tools"
  note "       Android Studio 가 이미 있다면 아래 경로를 PATH 에 추가해도 됩니다."
  note '       export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"'
fi

echo "5. 파이썬 3"
if command -v python3 >/dev/null 2>&1; then
  ok "$(python3 --version 2>&1)"
  note "       결과 페이지를 만드는 데 쓰입니다. 표준 라이브러리만 사용하므로 추가 설치는 없습니다."
else
  fail "python3 를 찾을 수 없습니다. 결과 페이지를 만들 수 없습니다."
fi

echo "6. .env 설정"
ENV_FILE="$REPO_ROOT/.env"
if [[ -f "$ENV_FILE" ]] && grep -qE '^APP_ID=.+' "$ENV_FILE"; then
  ok ".env 가 이미 준비되어 있습니다."
else
  APP_ID_VALUE="$ARG_APP_ID"
  SDK_ENV_VALUE="$ARG_SDK_ENV"

  # 인자로 받지 못했고 터미널에서 실행 중이라면 직접 묻는다.
  if [[ -z "$APP_ID_VALUE" && -t 0 ]]; then
    echo "  대상 앱의 패키지 이름이 필요합니다. 이 값은 공개 저장소에 담지 않으므로"
    echo "  담당자에게 받아 주세요. (예: com.example.game)"
    read -r -p "  APP_ID: " APP_ID_VALUE
  fi
  if [[ -z "$SDK_ENV_VALUE" && -t 0 ]]; then
    read -r -p "  SDK_ENV (dev, qa, live 중 하나. 비우면 qa): " SDK_ENV_VALUE
  fi
  SDK_ENV_VALUE="${SDK_ENV_VALUE:-qa}"

  if [[ -z "$APP_ID_VALUE" ]]; then
    fail "APP_ID 를 받지 못해 .env 를 만들지 못했습니다."
    note "       ./scripts/setup.sh --app-id <패키지 이름> 으로 다시 실행하거나,"
    note "       cp .env.example .env 로 만든 뒤 직접 채워 주세요."
  else
    [[ -f "$ENV_FILE" ]] || cp "$REPO_ROOT/.env.example" "$ENV_FILE"
    # 이미 있는 항목은 값을 바꾸고, 없으면 새로 붙인다.
    for pair in "APP_ID=$APP_ID_VALUE" "SDK_ENV=$SDK_ENV_VALUE"; do
      key="${pair%%=*}"
      if grep -qE "^${key}=" "$ENV_FILE"; then
        # 값에 슬래시가 들어갈 수 있으므로 구분자를 | 로 쓴다.
        sed -i '' "s|^${key}=.*|${pair}|" "$ENV_FILE"
      else
        printf '%s\n' "$pair" >>"$ENV_FILE"
      fi
    done
    ok ".env 를 만들었습니다. APP_ID 와 SDK_ENV=$SDK_ENV_VALUE 를 넣었습니다."
    note "       .env 는 커밋되지 않습니다. 다른 사람에게 그대로 전달하지 마세요."
  fi
fi

echo
if [[ $STATUS -eq 0 ]]; then
  echo "준비가 끝났습니다. 다음 순서로 진행하세요."
  echo
  echo "  1. 테스트할 앱을 기기에 설치합니다. 이 저장소는 설치를 담당하지 않습니다."
  echo "  2. 기기를 USB 로 연결하고 개발자 옵션에서 USB 디버깅을 켭니다."
  echo "  3. ./scripts/doctor.sh      실행 전 조건을 점검합니다."
  echo "  4. ./scripts/run.sh         테스트를 실행합니다."
  echo "  5. open reports/index.html  결과 페이지를 봅니다."
  echo
  echo "자세한 안내는 docs/onboarding.md 에 있습니다."
else
  echo "준비되지 않은 항목이 있습니다. 위의 안내를 따라 조치한 뒤 다시 실행해 주세요."
fi
exit $STATUS
