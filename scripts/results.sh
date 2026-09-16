#!/usr/bin/env bash
# 결과 전용 저장소와 실행 산출물을 주고받는다.
#
#   ./scripts/results.sh pull     다른 사람이 올린 결과까지 받아 온다
#   ./scripts/results.sh push     내 실행 결과를 올린다
#   ./scripts/results.sh status    현재 연결 상태와 올리지 않은 실행을 보여준다
#
# 결과를 두는 위치는 .env 의 REPORTS_DIR 로 정한다. 값이 없으면 저장소 안의 reports/ 를
# 쓰므로, 혼자 쓸 때는 이 스크립트가 필요하지 않다.
#
# 결과 페이지(index.html)는 올리지 않는다. 여러 사람이 동시에 갱신하면 충돌이 생기고,
# 실행 폴더만 있으면 언제든 다시 만들 수 있기 때문이다.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# .env 에서 값을 하나 읽는다. 프로세스 환경 변수가 있으면 그쪽을 우선한다.
env_value() {
  local key="$1" value=""
  value="$(printenv "$key" 2>/dev/null || true)"
  if [[ -z "$value" && -f "$REPO_ROOT/.env" ]]; then
    value="$(sed -n "s|^${key}=\(.*\)$|\1|p" "$REPO_ROOT/.env" | head -1)"
  fi
  printf '%s' "$value"
}

REPORTS_DIR="$(env_value REPORTS_DIR)"
if [[ -z "$REPORTS_DIR" ]]; then
  echo ".env 에 REPORTS_DIR 이 없습니다. 결과 전용 저장소를 받은 경로를 지정해 주세요." >&2
  echo "  git clone https://github.com/devsisters/sdktest-maestro-reports.git ~/sdktest-maestro-reports" >&2
  echo "  echo 'REPORTS_DIR=\$HOME/sdktest-maestro-reports' >> .env" >&2
  exit 1
fi
# ~ 나 $HOME 이 들어 있을 수 있으므로 펼친다.
REPORTS_DIR="$(eval echo "$REPORTS_DIR")"

if [[ ! -d "$REPORTS_DIR/.git" ]]; then
  echo "$REPORTS_DIR 이 git 저장소가 아닙니다. 결과 전용 저장소를 그 경로로 받아 주세요." >&2
  exit 1
fi

# 이 저장소에 푸시할 때 키체인에서 자격 증명을 읽지 못하는 경우가 있어, gh 의 자격 증명을
# 이번 명령에만 쓴다. 전역 git 설정은 바꾸지 않는다.
git_in_reports() {
  git -C "$REPORTS_DIR" -c credential.helper='!gh auth git-credential' "$@"
}

case "${1:-}" in
  pull)
    echo "결과를 받아 옵니다: $REPORTS_DIR"
    git_in_reports pull --quiet --rebase || {
      echo "받아 오지 못했습니다. 위의 메시지를 확인해 주세요." >&2
      exit 1
    }
    runs="$(find "$REPORTS_DIR" -mindepth 1 -maxdepth 1 -type d -not -name '.git' | wc -l | tr -d ' ')"
    echo "실행 $runs 회가 보관되어 있습니다."
    echo "결과 페이지를 다시 만듭니다."
    python3 "$REPO_ROOT/scripts/build-report-page.py" --reports-dir "$REPORTS_DIR"
    ;;

  push)
    # 올리기 전에 남의 결과를 먼저 받아 둔다. 그렇지 않으면 푸시가 거부된다.
    git_in_reports pull --quiet --rebase || {
      echo "다른 사람의 결과를 받아 오지 못했습니다. 먼저 해결해 주세요." >&2
      exit 1
    }
    git_in_reports add -A
    if git_in_reports diff --cached --quiet; then
      echo "올릴 새 결과가 없습니다."
      exit 0
    fi
    added="$(git_in_reports diff --cached --name-only | cut -d/ -f1 | sort -u | tr '\n' ' ')"
    git_in_reports commit -q -m "실행 결과 추가: $added" || {
      echo "커밋하지 못했습니다. $REPORTS_DIR 에서 user.name 과 user.email 설정을 확인해 주세요." >&2
      exit 1
    }
    git_in_reports push -q origin HEAD || {
      echo "푸시하지 못했습니다. 저장소 접근 권한을 확인해 주세요." >&2
      exit 1
    }
    echo "올렸습니다: $added"
    ;;

  status | "")
    echo "결과 위치: $REPORTS_DIR"
    echo "원격: $(git -C "$REPORTS_DIR" remote get-url origin 2>/dev/null || echo '없음')"
    runs="$(find "$REPORTS_DIR" -mindepth 1 -maxdepth 1 -type d -not -name '.git' | wc -l | tr -d ' ')"
    echo "보관된 실행: $runs 회"
    pending="$(git -C "$REPORTS_DIR" status --porcelain | wc -l | tr -d ' ')"
    if [[ "$pending" -gt 0 ]]; then
      echo "아직 올리지 않은 변경이 $pending 건 있습니다. ./scripts/results.sh push 로 올리세요."
    else
      echo "올리지 않은 변경이 없습니다."
    fi
    ;;

  *)
    echo "알 수 없는 명령입니다: $1" >&2
    sed -n '3,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
    exit 1
    ;;
esac
