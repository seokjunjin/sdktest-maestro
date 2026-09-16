"""Gherkin 형식의 시나리오 파일을 읽어 단계 목록으로 변환한다.

결과 페이지는 Maestro 명령을 그대로 늘어놓는 대신 이 시나리오 단계를 기준으로 보여준다.
명령 목록은 기계가 실행한 순서일 뿐이어서 무엇을 검증했는지 읽어 내기 어렵기 때문이다.

시나리오 단계와 실제 실행을 잇는 방법은 플로우의 라벨이다. 각 단계의 첫 명령에
`label: "[시나리오] <단계 문구>"` 를 붙여 두면, 그 라벨이 commands.json 에 그대로 남으므로
별도의 대응표를 두지 않아도 된다. 대응표를 따로 두면 플로우와 어긋나기 쉽다.

단계 위에 붙인 주석으로 자동화 상태를 표시한다. PyYAML 같은 외부 패키지가 없는 환경에서도
동작해야 하므로 표준 라이브러리만 사용한다.
"""

import re

STEP_MARKER = "[시나리오] "

# 단계를 시작하는 Gherkin 키워드. And 와 But 은 바로 앞 단계의 종류를 물려받는다.
KEYWORDS = ("Given", "When", "Then", "And", "But", "*")

# 단계 위에 붙여 자동화 상태를 표시하는 주석. 값은 (상태 코드, 화면에 보일 문구)다.
#
# 사전조건과 자동화 제외를 나눈 이유는 성격이 다르기 때문이다. 사전조건은 테스트를 실행하기
# 전에 갖추어져 있어야 하는 전제이고, 자동화 제외는 시나리오의 동작이지만 도구의 제약으로
# 자동화하지 않기로 한 단계다. 전자가 충족되지 않으면 테스트가 아예 성립하지 않는다.
ANNOTATIONS = {
    "사전조건": ("precondition", "사전조건"),
    "자동화 제외": ("excluded", "자동화 제외"),
    "미구현": ("missing", "미구현"),
    "구현 차이": ("deviation", "구현 차이"),
}

# 실행된 명령이 없는 것이 정상인 상태들. 이 경우에는 상태 문구를 그대로 앞세운다.
UNEXECUTED_CODES = ("precondition", "excluded", "missing")

_ANNOTATION_RE = re.compile(
    r"^#\s*(" + "|".join(map(re.escape, ANNOTATIONS)) + r")\s*:\s*(.*)$"
)


_FLOW_RE = re.compile(r"^#\s*플로우\s*:\s*(.+)$")


def parse_feature(path):
    """시나리오 파일을 읽어 단계 목록과 제목을 반환한다.

    표 형식으로 이어지는 줄(`| 항목 |`)은 바로 앞 단계의 예시 값이므로 별도의 단계로
    세지 않고 앞 단계에 묶어 둔다.

    `# 플로우: <경로>` 주석으로 이 시나리오를 구현한 플로우 파일을 지정한다. JUnit 결과의
    각 케이스에 같은 경로가 담겨 있으므로, 이 값을 열쇠로 케이스와 짝지을 수 있다.
    """
    feature_name = ""
    scenario_name = ""
    flow_path = ""
    steps = []
    pending = None  # 다음 단계에 붙일 주석

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue

        flow = _FLOW_RE.match(line)
        if flow:
            flow_path = flow.group(1).strip()
            continue

        annotation = _ANNOTATION_RE.match(line)
        if annotation:
            code, label = ANNOTATIONS[annotation.group(1)]
            pending = {"code": code, "label": label, "note": annotation.group(2).strip()}
            continue
        if line.startswith("#"):
            continue

        if line.startswith("Feature:"):
            feature_name = line.partition(":")[2].strip()
            continue
        if line.startswith("Scenario:") or line.startswith("Scenario Outline:"):
            scenario_name = line.partition(":")[2].strip()
            continue
        if line.startswith("Background:"):
            continue

        if line.startswith("|"):
            if steps:
                value = line.strip("|").strip()
                if value:
                    steps[-1]["examples"].append(value)
            continue

        keyword, _, text = line.partition(" ")
        if keyword in KEYWORDS and text.strip():
            steps.append(
                {
                    "keyword": keyword,
                    "text": text.strip(),
                    "examples": [],
                    "annotation": pending,
                }
            )
            pending = None

    return {
        "feature": feature_name,
        "scenario": scenario_name,
        "flow": flow_path,
        "path": path,
        "steps": steps,
    }


def load_scenarios(scenarios_dir):
    """시나리오 폴더의 .feature 파일들을 플로우 경로별로 읽어 온다."""
    by_flow = {}
    if not scenarios_dir.is_dir():
        return by_flow
    for feature_file in sorted(scenarios_dir.glob("*.feature")):
        scenario = parse_feature(feature_file)
        if scenario["flow"]:
            by_flow[scenario["flow"]] = scenario
    return by_flow


def group_by_scenario(steps, commands):
    """실행한 명령들을 시나리오 단계별로 묶는다.

    `[시나리오] ` 로 시작하는 라벨을 만나면 그 단계가 열리고, 다음 표식을 만나기 전까지의
    명령은 모두 그 단계에 속한다. 이렇게 하면 서브플로우처럼 여러 명령으로 이루어진 단계도
    표식 하나만으로 묶을 수 있다.

    반환값은 (단계별 결과 목록, 대응되지 않은 라벨 목록)이다. 두 번째 값은 시나리오 문구와
    플로우 라벨이 어긋났다는 뜻이므로 호출한 쪽에서 경고로 알린다.
    """
    by_text = {}
    order = []
    current = None
    leading = []

    for command in commands:
        description = command["description"]
        if description.startswith(STEP_MARKER):
            current = description[len(STEP_MARKER):].strip()
            if current not in by_text:
                by_text[current] = []
                order.append(current)
        if current is None:
            leading.append(command)
        else:
            by_text[current].append(command)

    grouped = []
    for step in steps:
        matched = by_text.pop(step["text"], None)
        annotation = step["annotation"]

        if matched:
            failed = sum(1 for c in matched if c["slug"] == "failed")
            skipped = all(c["slug"] == "skipped" for c in matched)
            slug = "failed" if failed else ("skipped" if skipped else "passed")
            status = "실패" if failed else ("건너뜀" if skipped else "통과")
            duration = sum(c["duration"] for c in matched)
        elif annotation and annotation["code"] in UNEXECUTED_CODES:
            slug, status, duration = annotation["code"], annotation["label"], 0
        else:
            # 라벨이 없고 주석도 없으면 연결이 끊어진 상태다. 통과로 보이게 두면 안 된다.
            slug, status, duration = "unmapped", "연결 안 됨", 0

        grouped.append(
            {
                **step,
                "commands": matched or [],
                "slug": slug,
                "status": status,
                "duration": duration,
            }
        )

    # 남은 항목은 시나리오에 없는 라벨이므로 문구가 어긋났다는 신호다.
    return grouped, [text for text in order if text in by_text]
