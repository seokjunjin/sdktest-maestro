"""Maestro 가 남긴 commands.json 을 사람이 읽을 수 있는 단계 목록으로 바꾼다.

commands.json 은 실행한 명령 하나를 `{"command": {...}, "metadata": {...}}` 형태로 담고
있으며, 명령의 종류는 바깥쪽 키 이름으로 구분된다. metadata 에는 상태와 소요 시간, 중첩
깊이, 그리고 그 단계가 남긴 스크린샷 경로가 들어 있다.

명령 설명을 만들 때는 `command` 쪽 값을 쓴다. `metadata.evaluatedCommand` 는 환경 변수가
치환된 형태라서 실제 패키지 이름이 그대로 드러나는데, 치환 전 값을 쓰면 `${APP_ID}` 로
표시되므로 결과 페이지에 내부 식별자를 남기지 않을 수 있다.
"""

import json

STEP_STATUS = {
    "COMPLETED": ("완료", "passed"),
    "SUCCESS": ("완료", "passed"),
    "FAILED": ("실패", "failed"),
    "ERROR": ("실패", "failed"),
    "SKIPPED": ("건너뜀", "skipped"),
    "PENDING": ("실행되지 않음", "skipped"),
}


def describe_selector(selector):
    """선택자를 짧은 문구로 만든다."""
    if not isinstance(selector, dict):
        return "요소"
    for key, prefix in (
        ("idRegex", "id"),
        ("textRegex", "문구"),
        ("below", "아래쪽"),
        ("above", "위쪽"),
    ):
        value = selector.get(key)
        if isinstance(value, str):
            return f"{prefix} {value}"
        if isinstance(value, dict):
            return f"{prefix}의 {describe_selector(value)}"
    return "요소"


def describe_condition(condition):
    if not isinstance(condition, dict):
        return "조건"
    if "visible" in condition:
        return f"{describe_selector(condition['visible'])} 이(가) 보이는지"
    if "notVisible" in condition:
        return f"{describe_selector(condition['notVisible'])} 이(가) 사라졌는지"
    if "scriptCondition" in condition:
        return "스크립트 조건"
    return "조건"


def describe(kind, body):
    """명령 종류와 내용을 하나의 설명 문구로 만든다.

    플로우에 label 을 달아 두었다면 그 값을 그대로 쓴다. 라벨이야말로 작성자가 의도를
    적어 둔 문구이므로, 기계적으로 만든 설명보다 읽기 좋다.
    """
    if isinstance(body, dict) and body.get("label"):
        return body["label"]
    body = body if isinstance(body, dict) else {}

    if kind == "defineVariablesCommand":
        # env 에 APP_ID 같은 내부 식별자가 담기므로 목록을 펼치지 않는다.
        return f"변수 정의 ({len(body.get('env') or {})} 개)"
    if kind == "applyConfigurationCommand":
        name = (body.get("config") or {}).get("name")
        return f"플로우 설정 적용{f': {name}' if name else ''}"
    if kind == "runFlowCommand":
        source = body.get("sourceDescription")
        return f"서브플로우 실행: {source}" if source else "인라인 서브플로우 실행"
    if kind == "clearStateCommand":
        return "앱 상태 초기화"
    if kind == "launchAppCommand":
        return "앱 실행"
    if kind == "stopAppCommand":
        return "앱 종료"
    if kind == "assertConditionCommand":
        timeout = body.get("timeout")
        suffix = f" (최대 {int(timeout) // 1000}초 대기)" if timeout else ""
        return f"{describe_condition(body.get('condition'))} 확인{suffix}"
    if kind == "waitForAnimationToEndCommand":
        timeout = body.get("timeout")
        limit = f" (최대 {int(timeout) // 1000}초)" if timeout else ""
        return f"화면이 멈출 때까지 대기{limit}"
    if kind == "tapOnPointV2Command":
        return f"좌표 탭 {body.get('point', '')}".strip()
    if kind == "tapOnElement":
        repeat = (body.get("repeat") or {}).get("repeat")
        times = f" ({repeat} 회)" if repeat and repeat > 1 else ""
        return f"탭: {describe_selector(body.get('selector'))}{times}"
    if kind == "swipeCommand":
        return f"스와이프 {body.get('startRelative', '')} → {body.get('endRelative', '')}"
    if kind == "takeScreenshotCommand":
        return f"스크린샷 저장: {body.get('path', '')}"
    if kind == "evalScriptCommand":
        return "스크립트 실행"
    if kind == "repeatCommand":
        return f"{body.get('times', '?')} 회 반복"
    if kind == "inputTextCommand":
        return "문자열 입력"
    if kind == "assertWithAICommand":
        return "AI 로 화면 내용 검증"
    # 위에 없는 명령은 키 이름에서 Command 를 떼어 그대로 보여준다.
    return kind.removesuffix("Command")


def parse_commands(path, artifact_prefix=""):
    """commands.json 을 읽어 단계 목록으로 변환한다.

    artifact_prefix 는 스크린샷 경로 앞에 붙일 상대 경로다. commands.json 안의 경로는
    플로우 폴더를 기준으로 하므로, 결과 페이지에서 열 수 있게 하려면 보정이 필요하다.
    """
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    steps = []
    for item in items:
        command = item.get("command") or {}
        metadata = item.get("metadata") or {}
        kind, body = next(iter(command.items()), ("unknownCommand", {}))
        label, slug = STEP_STATUS.get(
            (metadata.get("status") or "").upper(), (metadata.get("status") or "?", "skipped")
        )
        shots = [
            artifact_prefix + a["path"]
            for a in (metadata.get("artifacts") or [])
            if isinstance(a, dict) and a.get("path")
        ]
        steps.append(
            {
                "description": describe(kind, body),
                "status": label,
                "slug": slug,
                "duration": metadata.get("duration") or 0,
                "depth": metadata.get("depth") or 0,
                "screenshots": shots,
            }
        )
    return steps
