#!/usr/bin/env bash
# Maestro 테스트를 실행하기 위한 사전 조건들을 한 번에 점검한다.
set -uo pipefail

export PATH="$PATH:$HOME/.maestro/bin"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATUS=0

fail() {
  echo "  [실패] $1"
  STATUS=1
}

ok() {
  echo "  [정상] $1"
}

echo "1. Java 버전 (Maestro 는 17 이상을 요구합니다)"
if command -v java >/dev/null 2>&1; then
  ok "$(java -version 2>&1 | head -1)"
else
  fail "java 를 찾을 수 없습니다. Temurin JDK 17 이상을 설치해 주세요."
fi

echo "2. Maestro CLI"
if command -v maestro >/dev/null 2>&1; then
  ok "버전 $(maestro --version 2>/dev/null | tail -1)"
else
  fail 'curl -fsSL "https://get.maestro.mobile.dev" | bash 로 설치해 주세요.'
fi

echo "3. 연결된 기기"
if command -v maestro >/dev/null 2>&1; then
  maestro list-devices 2>/dev/null | sed 's/^/  /'
else
  fail "Maestro CLI 가 없어 기기 목록을 확인할 수 없습니다."
fi

echo "4. 안드로이드 adb"
if command -v adb >/dev/null 2>&1; then
  # adb devices 의 각 줄은 "시리얼<탭>상태" 두 열로 출력된다. 상태가 device 인 기기만 실제로
  # 테스트에 사용할 수 있고, unauthorized 나 offline 상태의 기기는 Maestro 가 목록에 올리지
  # 못한다. 따라서 상태별로 개수를 세어 원인에 맞는 안내를 내보낸다.
  # 데몬 기동 메시지("* daemon not running; ...")는 열이 두 개가 아니므로 NF == 2 로 걸러진다.
  ADB_STATES="$(adb devices 2>/dev/null | tail -n +2 | awk 'NF == 2 {print $2}')"
  ADB_READY="$(grep -cx 'device' <<<"$ADB_STATES")"
  ADB_UNAUTHORIZED="$(grep -cx 'unauthorized' <<<"$ADB_STATES")"
  ADB_OFFLINE="$(grep -cx 'offline' <<<"$ADB_STATES")"

  if [[ "$ADB_READY" -gt 0 ]]; then
    ok "$ADB_READY 대의 안드로이드 기기를 테스트에 사용할 수 있습니다."
    if [[ "$ADB_UNAUTHORIZED" -gt 0 || "$ADB_OFFLINE" -gt 0 ]]; then
      echo "  [참고] 이와 별개로 unauthorized $ADB_UNAUTHORIZED 대, offline $ADB_OFFLINE 대가 연결되어 있습니다."
      echo "         특정 기기에서 실행하려면 maestro test --device <시리얼> 로 대상을 지정해 주세요."
    fi
  elif [[ "$ADB_UNAUTHORIZED" -gt 0 ]]; then
    fail "연결된 안드로이드 기기 $ADB_UNAUTHORIZED 대가 모두 unauthorized 상태여서 사용할 수 없습니다."
    echo "         기기 화면에 표시된 USB 디버깅 허용 대화상자에서 [허용] 을 눌러 주세요."
    echo "         화면이 잠겨 있으면 대화상자가 표시되지 않으므로 잠금을 먼저 해제해야 합니다."
    echo "         대화상자가 보이지 않으면 adb kill-server 를 실행한 뒤 다시 연결해 주세요."
  elif [[ "$ADB_OFFLINE" -gt 0 ]]; then
    fail "연결된 안드로이드 기기 $ADB_OFFLINE 대가 모두 offline 상태여서 사용할 수 없습니다."
    echo "         USB 케이블을 다시 연결하거나 adb kill-server 를 실행해 주세요."
  else
    fail "테스트에 사용할 수 있는 안드로이드 기기가 없습니다."
    echo "         실기기는 USB 로 연결한 뒤 개발자 옵션에서 USB 디버깅을 켜 주세요."
    echo "         에뮬레이터는 maestro start-device --platform android 로 실행할 수 있습니다."
  fi
else
  echo "  [참고] adb 가 없습니다. 안드로이드를 테스트하지 않는다면 무시해도 됩니다."
fi

echo "5. .env 설정"
if [[ -f "$REPO_ROOT/.env" ]]; then
  if grep -qE '^APP_ID=.+' "$REPO_ROOT/.env"; then
    ok "APP_ID 가 설정되어 있습니다."
  else
    fail ".env 에 APP_ID 값을 채워 주세요."
  fi
else
  fail ".env 가 없습니다. cp .env.example .env 로 만든 뒤 값을 채워 주세요."
fi

echo "6. AI 검증용 Maestro Cloud API 키"
if [[ -f "$REPO_ROOT/.env" ]] && grep -qE '^MAESTRO_CLOUD_API_KEY=.+' "$REPO_ROOT/.env"; then
  ok "MAESTRO_CLOUD_API_KEY 가 설정되어 있습니다."
elif [[ -n "${MAESTRO_CLOUD_API_KEY:-}" ]]; then
  ok "MAESTRO_CLOUD_API_KEY 가 환경 변수로 설정되어 있습니다."
else
  echo "  [참고] MAESTRO_CLOUD_API_KEY 가 없습니다. .env 의 AI_ASSERT 를 true 로 켜서"
  echo "         Unity 화면 내용까지 검증하려면 maestro login 으로 발급받아 넣어 주세요."
  echo "         AI_ASSERT 를 끈 상태라면 없어도 모든 플로우가 실행됩니다."
fi

echo "7. Claude Code 의 Maestro MCP 연결"
if command -v claude >/dev/null 2>&1; then
  if claude mcp list 2>/dev/null | grep -qi maestro; then
    ok "maestro MCP 서버가 등록되어 있습니다."
  else
    fail "claude mcp add maestro -- maestro mcp 명령으로 등록해 주세요."
  fi
else
  echo "  [참고] claude CLI 를 찾을 수 없어 MCP 등록 상태를 확인하지 못했습니다."
fi

echo
if [[ $STATUS -eq 0 ]]; then
  echo "모든 점검 항목을 통과했습니다."
else
  echo "일부 점검 항목이 실패했습니다. 위의 안내를 따라 조치해 주세요."
fi
exit $STATUS
