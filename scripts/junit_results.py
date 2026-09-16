"""Maestro 가 내보낸 JUnit 결과를 읽어 케이스 목록으로 변환한다.

결과 해석 규칙을 한곳에 모아 두기 위해 build-report-page.py 에서 분리한 모듈이다.

Maestro 2.9.0 이 내보내는 형태는 다음과 같다. 상태는 status 속성으로 전달되고,
실패한 경우에만 failure 요소가 붙으며, 태그는 쉼표로 이어진 하나의 문자열이다.

    <testsuite name="..." device="R3KL205L26F" tests="2" failures="1" timestamp="...">
      <testcase name="..." file="..." time="1.782" timestamp="..." status="ERROR">
        <properties><property name="tags" value="probe, negative"/></properties>
        <failure>Assertion is false: false is true</failure>
      </testcase>
    </testsuite>
"""

import xml.etree.ElementTree as ET
from datetime import datetime

STATUS_PASSED = "통과"
STATUS_FAILED = "실패"
STATUS_SKIPPED = "건너뜀"


def to_iso8601(timestamp):
    """JUnit 의 시각 문자열에 현재 시간대 정보를 붙여 ISO 8601 로 만든다.

    Maestro 는 시간대 없이 `2026-09-16T13:48:27` 형태로 내보낸다. 시간대가 없으면
    받는 쪽이 UTC 로 해석하기 때문에, 실행한 기기의 지역 시간대를 명시해 준다.
    """
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.isoformat()


def parse_junit(xml_path):
    """JUnit XML 을 읽어 케이스 목록으로 변환한다."""
    root = ET.parse(xml_path).getroot()
    # 최상위 요소는 testsuites 이거나 testsuite 하나일 수 있다.
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    cases = []
    for suite in suites:
        suite_name = suite.get("name") or "이름 없는 스위트"
        device = suite.get("device") or ""
        for case in suite.findall("testcase"):
            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")
            reason_node = failure if failure is not None else error
            reason = (reason_node.text or "").strip() if reason_node is not None else ""

            # 상태는 status 속성으로 판단하고, 속성이 없거나 낯선 값이면 하위 요소로 판단한다.
            raw_status = (case.get("status") or "").upper()
            if raw_status == "SUCCESS":
                status = STATUS_PASSED
            elif raw_status in ("ERROR", "FAILURE", "FAILED"):
                status = STATUS_FAILED
            elif raw_status in ("SKIPPED", "SKIP"):
                status = STATUS_SKIPPED
            elif reason_node is not None:
                status = STATUS_FAILED
            elif skipped is not None:
                status = STATUS_SKIPPED
            else:
                status = STATUS_PASSED

            # 태그는 `probe, negative` 처럼 쉼표로 이어진 하나의 문자열로 들어온다.
            tags = []
            for prop in case.findall("./properties/property"):
                if prop.get("name") == "tags":
                    tags = [t.strip() for t in (prop.get("value") or "").split(",")]
                    tags = [t for t in tags if t]

            try:
                duration = float(case.get("time") or 0)
            except ValueError:
                duration = 0.0

            cases.append(
                {
                    "name": case.get("name") or case.get("id") or "이름 없는 케이스",
                    "status": status,
                    "tags": tags,
                    "suite": suite_name,
                    "device": device,
                    "duration": round(duration, 3),
                    "ran_at": to_iso8601(case.get("timestamp") or suite.get("timestamp")),
                    "file": case.get("file") or "",
                    "reason": reason,
                }
            )
    return cases
