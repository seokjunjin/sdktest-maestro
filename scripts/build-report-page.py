#!/usr/bin/env python3
"""reports/ 에 쌓인 실행 결과를 하나의 정적 HTML 페이지로 모은다.

Maestro 의 `--format HTML` 결과는 실행 한 번만 보여주기 때문에, 여러 번의 실행을
Test suite 처럼 모아 보려면 별도의 페이지가 필요하다. 이 스크립트는 reports/ 하위의
모든 junit.xml 을 읽어서 케이스 하나를 표의 행 하나로 펼친 페이지를 만든다.

    build-report-page.py                    reports/index.html 을 다시 만든다
    build-report-page.py --open             만든 뒤 기본 브라우저로 연다
    build-report-page.py --reports-dir <경로>

만들어진 페이지는 외부 자원을 전혀 참조하지 않으므로, 파일을 그대로 열어도 되고
네트워크가 없는 환경에서도 동작한다. 증적 폴더로 가는 링크는 상대 경로로 넣는다.
"""

import argparse
import base64
import html
import json
import re
import struct
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from junit_results import STATUS_FAILED, STATUS_PASSED, STATUS_SKIPPED, parse_junit
from maestro_steps import parse_commands
from scenarios import (
    STEP_MARKER,
    UNEXECUTED_CODES,
    group_by_scenario,
    load_scenarios,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# 상태마다 기호와 문구를 함께 붙인다. 색만으로 구분하면 색을 구별하기 어려운 사람이나
# 흑백 출력에서 의미가 사라지기 때문이다.
STATUS_META = {
    STATUS_PASSED: {"icon": "✓", "slug": "passed"},
    STATUS_FAILED: {"icon": "✕", "slug": "failed"},
    STATUS_SKIPPED: {"icon": "–", "slug": "skipped"},
}


def collect_steps(run_dir):
    """실행 폴더 안의 commands.json 들을 플로우 이름별 단계 목록으로 모은다.

    Maestro 는 `<실행 폴더>/<시각>/<플로우 이름>/commands.json` 구조로 남기므로,
    플로우 폴더의 이름을 케이스 이름과 맞춰서 연결한다.
    """
    steps_by_case = {}
    for commands_file in run_dir.rglob("commands.json"):
        flow_dir = commands_file.parent
        # 스크린샷 경로는 플로우 폴더 기준이므로, 결과 페이지에서 열 수 있게 보정한다.
        prefix = f"{flow_dir.relative_to(run_dir).as_posix()}/"
        steps = parse_commands(commands_file, artifact_prefix=prefix)
        if steps:
            steps_by_case[flow_dir.name] = steps
    return steps_by_case


EMPTY_META = {"app_version": "", "device_model": "", "android_release": ""}


def read_run_meta(run_dir):
    """실행 폴더의 meta.json 에서 앱 버전과 기기 모델명을 읽는다.

    run.sh 가 테스트를 시작하기 전에 기기에서 조회해 남긴 값이다. Maestro 가 JUnit 에 적는
    device 속성은 adb 시리얼 번호라서 기종을 알 수 없으므로, 모델명은 이 파일에서 가져온다.
    안드로이드가 아니거나 조회에 실패한 실행에는 이 파일이 없다.
    """
    meta_file = run_dir / "meta.json"
    if not meta_file.is_file():
        return dict(EMPTY_META)
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(EMPTY_META)
    name = (meta.get("app_version_name") or "").strip()
    code = (meta.get("app_version_code") or "").strip()
    if name and code:
        version = f"{name}({code})"
    else:
        version = name or (f"({code})" if code else "")
    model = (meta.get("device_model") or "").strip()
    release = (meta.get("android_release") or "").strip()
    return {"app_version": version, "device_model": model, "android_release": release}


def collect_runs(reports_dir):
    """reports/ 하위에서 junit.xml 을 가진 폴더를 최신 순으로 모은다."""
    runs = []
    for run_dir in sorted(reports_dir.iterdir(), reverse=True):
        junit = run_dir / "junit.xml"
        if not run_dir.is_dir() or not junit.is_file():
            continue
        try:
            cases = parse_junit(junit)
        except Exception as error:  # 결과 파일이 깨져 있어도 나머지 실행은 보여준다.
            print(f"  [건너뜀] {junit} 를 읽을 수 없습니다: {error}", file=sys.stderr)
            continue
        if not cases:
            continue

        steps_by_case = collect_steps(run_dir)
        for case in cases:
            case["steps"] = steps_by_case.get(case["name"], [])

        meta = read_run_meta(run_dir)
        for case in cases:
            case["app_version"] = meta["app_version"]
        runs.append(
            {
                "id": run_dir.name,
                "dir": run_dir,
                "cases": cases,
                "passed": sum(1 for c in cases if c["status"] == STATUS_PASSED),
                "failed": sum(1 for c in cases if c["status"] == STATUS_FAILED),
                "skipped": sum(1 for c in cases if c["status"] == STATUS_SKIPPED),
                "duration": round(sum(c["duration"] for c in cases), 1),
                "device": next((c["device"] for c in cases if c["device"]), ""),
                "suite": cases[0]["suite"],
                "ran_at": next((c["ran_at"] for c in cases if c["ran_at"]), None),
                "app_version": meta["app_version"],
                # 모델명을 못 읽었으면 JUnit 의 시리얼 번호라도 보여준다.
                "device_label": meta["device_model"]
                or next((c["device"] for c in cases if c["device"]), ""),
                "android_release": meta["android_release"],
            }
        )
    return runs


def format_time(iso_value):
    """ISO 8601 문자열을 화면에 보여줄 형태로 줄인다."""
    if not iso_value:
        return "시각 정보 없음"
    try:
        return datetime.fromisoformat(iso_value).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso_value


def status_chip(status):
    meta = STATUS_META.get(status, {"icon": "?", "slug": "skipped"})
    return (
        f'<span class="chip chip--{meta["slug"]}">'
        f'<span class="chip__icon" aria-hidden="true">{meta["icon"]}</span>'
        f'<span class="chip__label">{html.escape(status)}</span></span>'
    )


# 단계마다 색, 기호, 문구의 세 단서를 함께 제공한다. 색만으로는 의미를 나르지 않는다.
STEP_ICON = {
    "passed": "✓",
    "failed": "✕",
    "skipped": "–",
    "precondition": "◇",
    "excluded": "⊘",
    "missing": "!",
    "unmapped": "?",
}


def format_duration(milliseconds, decimals=1):
    """밀리초 값을 초 단위 문구로 바꾼다.

    사람이 읽는 화면이므로 단위를 초로 통일한다. 명령 하나하나는 수 밀리초로 끝나는 경우가
    있어서 소수점 자리를 늘려 받을 수 있게 했다.
    """
    return f"{milliseconds / 1000:.{decimals}f}s"


class InlineShots:
    """단일 파일 모드에서 스크린샷을 파일 안에 담되, 같은 이미지는 한 번만 넣는다.

    같은 스크린샷이 케이스별 결과 표와 실행 이력 표 두 곳에 나타나므로, img 태그마다
    base64 를 박으면 파일 크기가 두 배가 된다. 그래서 이미지마다 CSS 규칙을 하나 만들어
    두고 여러 요소가 그 규칙을 함께 쓰게 한다. 배경 이미지로 넣기 때문에 원본 비율을
    유지하려면 크기를 알아야 하므로, PNG 머리표의 IHDR 에서 폭과 높이를 읽는다.
    """

    def __init__(self, reports_dir):
        self.root = reports_dir
        self.index = {}
        self.rules = []

    def reference(self, rel_dir, path):
        """이미지를 등록하고 그 이미지를 가리키는 CSS 클래스 번호를 반환한다."""
        key = (rel_dir, path)
        if key in self.index:
            return self.index[key]
        source = self.root / rel_dir / path
        try:
            raw = source.read_bytes()
        except OSError as error:
            print(f"  [건너뜀] 스크린샷을 읽을 수 없습니다: {source} ({error})", file=sys.stderr)
            return None
        try:
            width, height = struct.unpack(">II", raw[16:24])
        except struct.error:
            width, height = 16, 9
        number = len(self.index) + 1
        encoded = base64.b64encode(raw).decode("ascii")
        self.rules.append(
            f".shot-img--{number}{{aspect-ratio:{width}/{height};"
            f"background-image:url(data:image/png;base64,{encoded})}}"
        )
        self.index[key] = number
        return number

    def css(self):
        return "\n".join(self.rules)


def render_shots(paths, rel_dir, inline):
    """스크린샷을 링크 또는 파일에 담은 이미지로 만든다.

    inline 이 주어지면 이미지를 페이지 안에 담는다. 파일 하나만 전달해도 화면이 깨지지
    않게 하기 위한 것이다. 링크 대신 접이식 이미지를 쓰는 이유는 브라우저가 data: 주소로의
    최상위 이동을 막기 때문이다.
    """
    if not paths:
        return ""
    if inline is None:
        return "".join(
            f'<a class="shot" href="{rel_dir}/{html.escape(path)}">스크린샷</a>'
            for path in paths
        )

    blocks = []
    for path in paths:
        number = inline.reference(rel_dir, path)
        if number is None:
            continue
        name = html.escape(Path(path).name)
        blocks.append(
            f'<details class="shot-box"><summary>스크린샷 {name}</summary>'
            f'<div class="shot-img shot-img--{number}" role="img" aria-label="{name}"></div>'
            "</details>"
        )
    return "".join(blocks)


def render_commands(commands, rel_dir, inline=None):
    """시나리오 단계 하나가 실제로 실행한 Maestro 명령들을 접은 목록으로 만든다."""
    if not commands:
        return ""
    lines = []
    for command in commands:
        shots = render_shots(command["screenshots"], rel_dir, inline)
        lines.append(
            f"""            <li class="cmd cmd--{command['slug']}" style="--depth: {min(command['depth'], 4)}">
              <span class="cmd__icon" aria-hidden="true">{STEP_ICON.get(command['slug'], '?')}</span>
              <span class="cmd__desc">{html.escape(command['description'])}</span>
              <span class="cmd__meta">{format_duration(command['duration'], 3)}{shots}</span>
            </li>"""
        )
    return (
        '<details class="cmds"><summary>'
        + f"실행한 명령 {len(commands)} 개"
        + '</summary>\n          <ol class="cmd-list">\n'
        + "\n".join(lines)
        + "\n          </ol></details>"
    )


def render_scenario(scenario, commands, rel_dir, inline=None, wrap=True):
    """시나리오 단계를 기준으로 케이스의 진행 내역을 만든다.

    Maestro 명령을 그대로 늘어놓으면 변수 정의나 설정 적용 같은 내부 동작이 섞여서 무엇을
    검증했는지 읽기 어렵다. 그래서 QA 시나리오의 문구를 바깥에 두고, 각 단계가 실제로 실행한
    명령은 그 아래에 접어 둔다.
    """
    steps, orphans = group_by_scenario(scenario["steps"], commands)

    automated = sum(1 for s in steps if s["commands"])
    failed = sum(1 for s in steps if s["slug"] == "failed")
    summary = f"시나리오 단계 {len(steps)} 개 · 자동화 {automated} 개"
    if failed:
        summary += f" · 실패 {failed} 개"

    lines = []
    for index, step in enumerate(steps, start=1):
        annotation = step["annotation"]
        # 주석이 붙은 단계는 그 종류를 상태로 앞세운다. 자동화되지 않았다는 사실이나
        # 시나리오와 다르게 구현했다는 사실이 통과 표시에 가려지면 안 된다.
        slug = step["slug"]
        if annotation and annotation["code"] in UNEXECUTED_CODES and not step["commands"]:
            slug = annotation["code"]

        badge = ""
        if annotation:
            badge = (
                f'<span class="badge badge--{annotation["code"]}"'
                f' title="{html.escape(annotation["note"])}">{html.escape(annotation["label"])}</span>'
            )
        note = (
            f'<div class="note">{html.escape(annotation["note"])}</div>'
            if annotation
            else ""
        )
        examples = (
            '<ul class="examples">'
            + "".join(f"<li>{html.escape(v)}</li>" for v in step["examples"])
            + "</ul>"
            if step["examples"]
            else ""
        )
        timing = format_duration(step["duration"]) if step["commands"] else "—"

        lines.append(
            f"""          <li class="sstep sstep--{slug}">
            <span class="sstep__icon" aria-hidden="true">{STEP_ICON.get(slug, '?')}</span>
            <span class="sstep__no">{index}</span>
            <span class="sstep__body">
              <span class="sstep__kw">{html.escape(step['keyword'])}</span>
              <span class="sstep__text">{html.escape(step['text'])}</span>{badge}
              {examples}{note}
              {render_commands(step['commands'], rel_dir, inline)}
            </span>
            <span class="sstep__meta">{timing}<span class="sep"> · </span>{html.escape(step['status'])}</span>
          </li>"""
        )

    warning = ""
    if orphans:
        items = "".join(f"<li>{html.escape(t)}</li>" for t in orphans)
        warning = (
            '<div class="warn">플로우의 라벨이 시나리오 문구와 맞지 않습니다. '
            f"아래 라벨을 확인해 주세요.<ul>{items}</ul></div>"
        )

    body = warning + '<ol class="sstep-list">\n' + "\n".join(lines) + "\n</ol>"
    if not wrap:
        # 실행 이력 표에서는 케이스마다 제목을 따로 붙이므로 감싸지 않고 본문만 넘긴다.
        return body, summary, orphans
    return (
        '<details class="steps"><summary>'
        + html.escape(summary)
        + "</summary>\n"
        + body
        + "</details>"
    ), summary, orphans


def render_case_rows(runs, scenarios, inline=None):
    rows = []
    warnings = []
    for run in runs:
        rel_dir = html.escape(run["id"])
        for case in run["cases"]:
            tags = "".join(
                f'<span class="tag">{html.escape(t)}</span>' for t in case["tags"]
            )
            reason = (
                f'<div class="reason">{html.escape(case["reason"])}</div>'
                if case["reason"]
                else ""
            )
            commands = case.get("steps") or []
            scenario = scenarios.get(case["file"])
            if scenario and commands:
                steps, _, orphans = render_scenario(
                    scenario, commands, rel_dir, inline
                )
                warnings.extend(
                    f"{case['name']}: 라벨 '{t}' 이(가) 시나리오에 없습니다." for t in orphans
                )
            else:
                # 시나리오가 없는 케이스는 실행한 명령을 그대로 보여준다.
                steps = render_commands(commands, rel_dir, inline)
            rows.append(
                f"""      <tr class="case" data-status="{STATUS_META.get(case['status'], {}).get('slug', 'skipped')}"
          data-tags="{html.escape(' '.join(case['tags']))}"
          data-search="{html.escape((case['name'] + ' ' + case['file'] + ' ' + case['reason']).lower())}"
          data-duration="{case['duration']}" data-ran-at="{html.escape(case['ran_at'] or '')}">
        <td>{status_chip(case['status'])}</td>
        <td class="case__name"><div>{html.escape(case['name'])}</div>
            <div class="path">{html.escape(case['file'])}</div>{reason}{steps}</td>
        <td class="ver">{html.escape(case['app_version']) or '<span class="muted">알 수 없음</span>'}</td>
        <td class="num">{case['duration']:.1f}s</td>
        <td class="num">{html.escape(format_time(case['ran_at']))}</td>
      </tr>"""
            )
    return "\n".join(rows), warnings


def render_run_detail(run, scenarios, inline):
    """실행 하나에 속한 케이스들의 시나리오 단계를 접은 블록으로 만든다.

    이력에서 바로 펼쳐 이전 실행과 비교할 수 있게 하기 위한 것이다. 케이스별 결과 표와
    같은 내용이지만, 스크린샷은 InlineShots 가 한 번만 담으므로 파일이 두 배가 되지 않는다.
    """
    blocks = []
    totals = []
    for case in run["cases"]:
        commands = case.get("steps") or []
        scenario = scenarios.get(case["file"])
        head = (
            f'<div class="case-head">{status_chip(case["status"])}'
            f'<span class="case-head__name">{html.escape(case["name"])}</span>'
            f'<span class="path">{html.escape(case["file"])}</span></div>'
        )
        if scenario and commands:
            body, summary, _ = render_scenario(
                scenario, commands, html.escape(run["id"]), inline, wrap=False
            )
            totals.append(summary)
        elif commands:
            body = render_commands(commands, html.escape(run["id"]), inline)
        else:
            body = '<div class="note">기록된 단계가 없습니다.</div>'
        blocks.append(f'<div class="case-block">{head}{body}</div>')

    if not blocks:
        return ""
    label = f"케이스 {len(run['cases'])} 개의 진행 내역"
    if totals:
        label += f" · {totals[0]}"
    return (
        '<details class="steps"><summary>'
        + html.escape(label)
        + "</summary>"
        + "".join(blocks)
        + "</details>"
    )


def render_run_rows(runs, scenarios, inline=None):
    rows = []
    for run in runs:
        verdict = STATUS_PASSED if run["failed"] == 0 else STATUS_FAILED
        device = html.escape(run["device_label"]) or '<span class="muted">알 수 없음</span>'
        if run["android_release"]:
            device += f'<div class="path">Android {html.escape(run["android_release"])}</div>'
        rows.append(
            f"""      <tr>
        <td>{status_chip(verdict)}</td>
        <td>{html.escape(run['suite'])}<div class="path">{html.escape(run['id'])}</div>
            {render_run_detail(run, scenarios, inline)}</td>
        <td class="num">{run['passed']} / {len(run['cases'])}</td>
        <td class="num">{run['duration']:.1f}s</td>
        <td class="ver">{html.escape(run['app_version']) or '<span class="muted">알 수 없음</span>'}</td>
        <td>{device}</td>
        <td class="num">{html.escape(format_time(run['ran_at']))}</td>
      </tr>"""
        )
    return "\n".join(rows)


# 색상 값은 dataviz 지침의 기준 팔레트를 그대로 가져왔다. 상태 색(good, critical)은
# 계열 색과 섞이지 않도록 고정된 값이며, 밝은 배경에서 대비가 3:1 에 못 미치기 때문에
# 반드시 기호와 문구를 함께 표시해서 색이 단독으로 의미를 나르지 않게 한다.
STYLE = """
    :root {
      color-scheme: light;
      --surface-1: #fcfcfb;
      --plane: #f9f9f7;
      --text-primary: #0b0b0b;
      --text-secondary: #52514e;
      --text-muted: #898781;
      --gridline: #e1e0d9;
      --border: rgba(11, 11, 11, 0.10);
      --status-good: #0ca30c;
      --status-critical: #d03b3b;
      --status-warning: #fab219;
      --status-serious: #ec835a;
      --status-none: #898781;
    }
    @media (prefers-color-scheme: dark) {
      :root:where(:not([data-theme="light"])) {
        color-scheme: dark;
        --surface-1: #1a1a19;
        --plane: #0d0d0d;
        --text-primary: #ffffff;
        --text-secondary: #c3c2b7;
        --text-muted: #898781;
        --gridline: #2c2c2a;
        --border: rgba(255, 255, 255, 0.10);
      }
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --surface-1: #1a1a19;
      --plane: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --gridline: #2c2c2a;
      --border: rgba(255, 255, 255, 0.10);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 32px 24px 64px;
      background: var(--plane);
      color: var(--text-primary);
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.55;
    }
    .wrap { max-width: 1180px; margin: 0 auto; }

    header { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
    h1 { margin: 0; font-size: 20px; font-weight: 650; letter-spacing: -0.01em; }
    h2 { margin: 32px 0 12px; font-size: 15px; font-weight: 650; }
    .sub { color: var(--text-secondary); font-size: 13px; }

    button {
      font: inherit; color: var(--text-secondary); cursor: pointer;
      background: var(--surface-1); border: 1px solid var(--border);
      border-radius: 8px; padding: 6px 12px;
    }
    button:hover { color: var(--text-primary); }

    .kpi { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr; gap: 12px; }
    .tile {
      background: var(--surface-1); border: 1px solid var(--border);
      border-radius: 12px; padding: 16px 18px;
    }
    .tile__label { color: var(--text-secondary); font-size: 12px; }
    .tile__value { margin-top: 4px; font-size: 30px; font-weight: 600; letter-spacing: -0.02em; }
    .tile--hero .tile__value { font-size: 48px; line-height: 1.1; }
    .tile__note { margin-top: 2px; color: var(--text-muted); font-size: 12px; }

    .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0; }
    .filters select, .filters input {
      font: inherit; color: var(--text-primary); background: var(--surface-1);
      border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px;
    }
    .filters input { min-width: 240px; }
    .count { color: var(--text-muted); font-size: 12px; margin-left: auto; }

    table { width: 100%; border-collapse: collapse; background: var(--surface-1);
            border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
    th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--gridline); vertical-align: top; }
    tbody tr:last-child td { border-bottom: none; }
    th { color: var(--text-secondary); font-size: 12px; font-weight: 600; white-space: nowrap; }
    th.sortable { cursor: pointer; user-select: none; }
    th.sortable:hover { color: var(--text-primary); }
    td.num, th.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
    td.ver { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .case__name div:first-child { font-weight: 550; }
    .path { color: var(--text-muted); font-size: 12px; word-break: break-all; }
    .reason { margin-top: 4px; color: var(--text-secondary); font-size: 12px; }
    .muted { color: var(--text-muted); }
    a { color: var(--text-secondary); }
    a:hover { color: var(--text-primary); }
    td:last-child { white-space: nowrap; }

    .tag {
      display: inline-block; margin: 0 4px 2px 0; padding: 1px 8px;
      border: 1px solid var(--border); border-radius: 999px;
      color: var(--text-secondary); font-size: 12px; white-space: nowrap;
    }

    /* 상태 표시는 색, 기호, 문구의 세 가지 단서를 함께 제공한다. */
    .chip { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
    .chip__icon { font-weight: 700; }
    .chip__label { color: var(--text-primary); }
    .chip--passed .chip__icon { color: var(--status-good); }
    .chip--failed .chip__icon { color: var(--status-critical); }
    .chip--skipped .chip__icon { color: var(--status-none); }

    /* 단계 목록. details 를 쓰므로 자바스크립트 없이 펼치고 접을 수 있다. */
    .steps { margin-top: 8px; }
    .steps > summary {
      display: inline-block; cursor: pointer; padding: 2px 10px;
      border: 1px solid var(--border); border-radius: 999px;
      color: var(--text-secondary); font-size: 12px;
    }
    .steps > summary:hover { color: var(--text-primary); }
    /* 시나리오 단계. QA 시나리오의 문구를 그대로 앞세우고, 실제 명령은 그 아래에 접어 둔다. */
    .sstep-list { margin: 8px 0 4px; padding: 0; list-style: none; }
    .sstep {
      display: grid; grid-template-columns: 16px 24px 1fr auto; gap: 8px;
      align-items: baseline; padding: 6px 0;
      border-top: 1px solid var(--gridline); font-size: 13px;
    }
    .sstep:first-child { border-top: none; }
    .sstep__icon { font-weight: 700; }
    .sstep--passed .sstep__icon { color: var(--status-good); }
    .sstep--failed .sstep__icon { color: var(--status-critical); }
    .sstep--skipped, .sstep--excluded { color: var(--text-muted); }
    .sstep--skipped .sstep__icon, .sstep--excluded .sstep__icon { color: var(--status-none); }
    .sstep--precondition .sstep__icon { color: var(--text-secondary); }
    .sstep--missing .sstep__icon { color: var(--status-serious); }
    .sstep--unmapped .sstep__icon { color: var(--status-warning); }
    .sstep--failed .sstep__text { font-weight: 600; }
    .sstep__no, .sstep__meta { color: var(--text-muted); font-variant-numeric: tabular-nums; }
    .sstep__no { text-align: right; }
    .sstep__meta { white-space: nowrap; font-size: 12px; }
    .sstep__kw {
      display: inline-block; min-width: 42px; margin-right: 4px;
      color: var(--text-muted); font-size: 12px; font-weight: 600;
    }
    .sstep__text { color: var(--text-primary); }
    .sstep--excluded .sstep__text, .sstep--skipped .sstep__text { color: var(--text-secondary); }
    .examples { margin: 4px 0 0 46px; padding: 0; list-style: none; }
    .examples li {
      display: inline-block; margin: 0 4px 2px 0; padding: 1px 8px;
      border: 1px solid var(--border); border-radius: 999px;
      color: var(--text-secondary); font-size: 12px;
    }
    .note { margin: 2px 0 0 46px; color: var(--text-muted); font-size: 12px; }
    .badge {
      display: inline-block; margin-left: 8px; padding: 0 7px;
      border-radius: 999px; font-size: 11px; font-weight: 600;
      border: 1px solid var(--border); color: var(--text-secondary);
    }
    .badge--missing { color: var(--status-serious); }
    .badge--deviation { color: var(--text-secondary); }
    .badge--precondition { color: var(--text-secondary); }
    .badge--excluded { color: var(--text-muted); }
    .warn {
      margin: 8px 0; padding: 8px 12px; border-radius: 8px;
      border: 1px solid var(--status-warning); color: var(--text-secondary); font-size: 12px;
    }
    .warn ul { margin: 4px 0 0; padding-left: 18px; }

    /* 시나리오 단계 아래에 접어 두는 Maestro 명령 목록 */
    .cmds { margin: 4px 0 0 46px; }
    .cmds > summary {
      cursor: pointer; color: var(--text-muted); font-size: 11px;
    }
    .cmds > summary:hover { color: var(--text-secondary); }
    .cmd-list { margin: 4px 0; padding: 0; list-style: none; }
    .cmd {
      display: grid; grid-template-columns: 14px 1fr auto; gap: 6px;
      align-items: baseline; padding: 2px 0 2px calc(var(--depth) * 14px);
      font-size: 11px; color: var(--text-muted);
    }
    .cmd--passed .cmd__icon { color: var(--status-good); }
    .cmd--failed .cmd__icon { color: var(--status-critical); }
    .cmd--skipped .cmd__icon { color: var(--status-none); }
    .cmd--failed .cmd__desc { color: var(--text-primary); }
    .cmd__desc { word-break: break-word; }
    .cmd__meta { white-space: nowrap; font-variant-numeric: tabular-nums; }
    .shot { margin-left: 8px; white-space: nowrap; }
    .sep { color: var(--gridline); }

    /* 파일 하나로 공유할 때 페이지 안에 담기는 스크린샷 */
    .shot-box { display: inline-block; margin-left: 8px; vertical-align: top; }
    .shot-box > summary { cursor: pointer; color: var(--text-secondary); white-space: nowrap; }
    .shot-box > summary:hover { color: var(--text-primary); }
    .shot-img {
      display: block; width: 100%; max-width: 560px; margin: 6px 0;
      background-size: contain; background-repeat: no-repeat; background-position: top left;
      border: 1px solid var(--border); border-radius: 8px;
    }

    /* 실행 이력에서 펼치는 케이스별 진행 내역 */
    .case-block { margin: 10px 0 14px; }
    .case-block + .case-block { border-top: 1px solid var(--gridline); padding-top: 10px; }
    .case-head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
    .case-head__name { font-weight: 600; }

    footer { margin-top: 32px; color: var(--text-muted); font-size: 12px; }
    @media (max-width: 860px) { .kpi { grid-template-columns: 1fr 1fr; } }
"""

SCRIPT = """
    const root = document.documentElement;
    const saved = localStorage.getItem('sdktest-theme');
    if (saved) root.dataset.theme = saved;
    document.getElementById('theme').addEventListener('click', () => {
      const dark = getComputedStyle(root).colorScheme === 'dark';
      root.dataset.theme = dark ? 'light' : 'dark';
      localStorage.setItem('sdktest-theme', root.dataset.theme);
    });

    const rows = Array.from(document.querySelectorAll('tr.case'));
    const statusFilter = document.getElementById('f-status');
    const tagFilter = document.getElementById('f-tag');
    const search = document.getElementById('f-search');
    const count = document.getElementById('count');

    function apply() {
      const s = statusFilter.value;
      const t = tagFilter.value;
      const q = search.value.trim().toLowerCase();
      let shown = 0;
      for (const row of rows) {
        const ok =
          (s === 'all' || row.dataset.status === s) &&
          (t === 'all' || row.dataset.tags.split(' ').includes(t)) &&
          (q === '' || row.dataset.search.includes(q));
        row.hidden = !ok;
        if (ok) shown += 1;
      }
      count.textContent = `${shown} / ${rows.length} 건 표시 중`;
    }
    [statusFilter, tagFilter].forEach((el) => el.addEventListener('change', apply));
    search.addEventListener('input', apply);
    apply();

    // 열 제목을 누르면 정렬 방향을 뒤집는다. 비교 기준은 data 속성에 들어 있다.
    let sortDir = -1;
    document.querySelectorAll('th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        sortDir = -sortDir;
        const body = document.getElementById('cases-body');
        rows.sort((a, b) => {
          const av = a.dataset[key];
          const bv = b.dataset[key];
          const cmp = key === 'duration' ? av - bv : String(av).localeCompare(String(bv));
          return cmp * sortDir;
        });
        rows.forEach((row) => body.appendChild(row));
      });
    });
"""


def render_page(runs, generated_at, scenarios, inline=None):
    total_cases = sum(len(r["cases"]) for r in runs)
    total_passed = sum(r["passed"] for r in runs)
    total_failed = sum(r["failed"] for r in runs)
    total_skipped = sum(r["skipped"] for r in runs)
    # 건너뛴 케이스는 실행되지 않았으므로 통과율의 분모에서 제외한다. 분모에 넣으면
    # wip 태그가 붙은 템플릿이 늘어날 때마다 통과율이 떨어져서 지표를 신뢰할 수 없게 된다.
    executed = total_passed + total_failed
    pass_rate = (total_passed / executed * 100) if executed else 0.0
    rate_note = f"실행한 {executed} 건 중 통과 {total_passed} 건, 실패 {total_failed} 건"
    if total_skipped:
        rate_note += f" (건너뜀 {total_skipped} 건은 제외)"
    latest = runs[0] if runs else None

    if latest is None:
        latest_value, latest_note = "기록 없음", "아직 실행 결과가 없습니다."
    elif latest["failed"] == 0:
        latest_value = "전체 통과"
        latest_note = f"{format_time(latest['ran_at'])} · {latest['device'] or '기기 정보 없음'}"
    else:
        latest_value = f"실패 {latest['failed']}건"
        latest_note = f"{format_time(latest['ran_at'])} · {latest['device'] or '기기 정보 없음'}"

    all_tags = sorted({t for r in runs for c in r["cases"] for t in c["tags"]})
    tag_options = "".join(
        f'<option value="{html.escape(t)}">{html.escape(t)}</option>' for t in all_tags
    )

    avg = (sum(r["duration"] for r in runs) / len(runs)) if runs else 0.0
    case_rows, warnings = render_case_rows(runs, scenarios, inline)
    run_rows = render_run_rows(runs, scenarios, inline)
    # 표를 모두 렌더링한 뒤라야 담긴 이미지 목록이 확정된다.
    inline_css = f"<style>{inline.css()}</style>" if inline else ""

    for message in warnings:
        print(f"  [경고] {message}", file=sys.stderr)

    return f"""<!DOCTYPE html>
<html lang="ko" data-palette="#0ca30c,#d03b3b">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SDK 테스트 자동화 결과</title>
<style>{STYLE}</style>
{inline_css}
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>SDK 테스트 자동화 결과</h1>
      <div class="sub">{html.escape(generated_at)} 기준 · 실행 {len(runs)} 회 · 케이스 {total_cases} 건</div>
    </div>
    <button id="theme" type="button">밝게 / 어둡게</button>
  </header>

  <section class="kpi">
    <div class="tile tile--hero">
      <div class="tile__label">통과율 (누적)</div>
      <div class="tile__value">{pass_rate:.1f}%</div>
      <div class="tile__note">{html.escape(rate_note)}</div>
    </div>
    <div class="tile">
      <div class="tile__label">마지막 실행</div>
      <div class="tile__value">{html.escape(latest_value)}</div>
      <div class="tile__note">{html.escape(latest_note)}</div>
    </div>
    <div class="tile">
      <div class="tile__label">실행 횟수</div>
      <div class="tile__value">{len(runs)}</div>
      <div class="tile__note">reports/ 에 남아 있는 실행 기준</div>
    </div>
    <div class="tile">
      <div class="tile__label">실행당 평균 소요</div>
      <div class="tile__value">{avg:.1f}s</div>
      <div class="tile__note">케이스 소요 시간의 합계 기준</div>
    </div>
  </section>

  <h2>케이스별 결과</h2>
  <div class="filters">
    <select id="f-status" aria-label="상태로 걸러내기">
      <option value="all">상태 전체</option>
      <option value="failed">실패만</option>
      <option value="passed">통과만</option>
      <option value="skipped">건너뜀만</option>
    </select>
    <select id="f-tag" aria-label="태그로 걸러내기">
      <option value="all">태그 전체</option>
      {tag_options}
    </select>
    <input id="f-search" type="search" placeholder="케이스 이름, 파일 경로, 실패 사유 검색">
    <span class="count" id="count"></span>
  </div>
  <table>
    <thead>
      <tr>
        <th>상태</th>
        <th>케이스</th>
        <th>앱 버전</th>
        <th class="num sortable" data-key="duration">소요 시간</th>
        <th class="num sortable" data-key="ranAt">실행 시각</th>
      </tr>
    </thead>
    <tbody id="cases-body">
{case_rows}
    </tbody>
  </table>

  <h2>실행 이력</h2>
  <table>
    <thead>
      <tr>
        <th>결과</th>
        <th>스위트</th>
        <th class="num">통과 / 전체</th>
        <th class="num">소요 시간</th>
        <th>앱 버전</th>
        <th>기기</th>
        <th class="num">실행 시각</th>
      </tr>
    </thead>
    <tbody>
{run_rows}
    </tbody>
  </table>

  <footer>
    이 페이지는 <code>scripts/build-report-page.py</code> 가 <code>reports/</code> 하위의
    <code>junit.xml</code> 들을 모아 만듭니다. 외부 자원을 참조하지 않으므로 네트워크 없이도 열립니다.
    스크린샷과 로그는 각 행의 증적 링크에서 볼 수 있으며, 내부 식별자가 담기므로 외부로 공유하지 마세요.
  </footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


def check_scenario_links(scenarios):
    """플로우의 `[시나리오]` 라벨이 시나리오 문구와 맞는지 실행 없이 점검한다.

    이 설계는 라벨 문구가 시나리오 문구와 같다는 전제에 기대고 있다. 어느 한쪽만 고치면
    결과 페이지에서 단계가 "연결 안 됨" 으로 나타나므로, 실행하기 전에 미리 잡아낸다.
    """
    label_pattern = re.compile(r"label:\s*(.+)$")
    labels = []
    for flow_file in sorted((REPO_ROOT / ".maestro").rglob("*.yaml")):
        for line in flow_file.read_text(encoding="utf-8").splitlines():
            found = label_pattern.search(line.strip())
            if not found:
                continue
            value = found.group(1).strip().strip('"').strip("'")
            if value.startswith(STEP_MARKER):
                labels.append((value[len(STEP_MARKER):].strip(), flow_file))

    problems = []
    all_texts = {s["text"] for sc in scenarios.values() for s in sc["steps"]}
    for label, flow_file in labels:
        if label not in all_texts:
            problems.append(
                f"{flow_file.relative_to(REPO_ROOT)} 의 라벨 '{label}' 이(가) "
                "어느 시나리오 단계와도 일치하지 않습니다."
            )

    linked = {label for label, _ in labels}
    for scenario in scenarios.values():
        for step in scenario["steps"]:
            if step["text"] in linked or step["annotation"]:
                continue
            problems.append(
                f"{scenario['path'].name} 의 단계 '{step['text']}' 에 연결된 라벨이 없고 "
                "상태 주석도 없습니다."
            )

    if problems:
        print("시나리오 연결에 문제가 있습니다.", file=sys.stderr)
        for problem in problems:
            print(f"  [문제] {problem}", file=sys.stderr)
        return 1

    steps = sum(len(sc["steps"]) for sc in scenarios.values())
    print(
        f"시나리오 {len(scenarios)} 개, 단계 {steps} 개를 점검했습니다. "
        f"라벨 {len(labels)} 개가 모두 일치합니다."
    )
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="reports/ 의 실행 결과를 하나의 정적 HTML 페이지로 모읍니다."
    )
    parser.add_argument(
        "--reports-dir",
        default=str(REPO_ROOT / "reports"),
        help="결과 폴더 경로. 기본값은 저장소의 reports/ 입니다.",
    )
    parser.add_argument(
        "--open", action="store_true", help="만든 뒤 기본 브라우저로 엽니다."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="페이지를 만들지 않고 시나리오와 플로우 라벨의 연결만 점검합니다.",
    )
    parser.add_argument(
        "--standalone",
        nargs="?",
        const="reports/share.html",
        metavar="경로",
        help="스크린샷까지 파일 안에 담은 단일 HTML 을 만듭니다. "
        "경로를 주지 않으면 reports/share.html 로 저장합니다.",
    )
    args = parser.parse_args()

    if args.check:
        return check_scenario_links(load_scenarios(REPO_ROOT / ".maestro" / "scenarios"))

    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_dir():
        raise SystemExit(
            f"결과 폴더가 없습니다: {reports_dir}\n"
            "./scripts/run.sh 로 테스트를 한 번 실행하면 만들어집니다."
        )

    runs = collect_runs(reports_dir)
    scenarios = load_scenarios(REPO_ROOT / ".maestro" / "scenarios")
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

    if args.standalone:
        # 스크린샷을 파일 안에 담으므로 reports/ 폴더 없이도 그대로 열린다.
        output = Path(args.standalone)
        if not output.is_absolute():
            output = REPO_ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        body = render_page(
            runs, generated_at, scenarios, inline=InlineShots(reports_dir)
        )
    else:
        output = reports_dir / "index.html"
        body = render_page(runs, generated_at, scenarios)

    output.write_text(body, encoding="utf-8")

    total = sum(len(r["cases"]) for r in runs)
    size = output.stat().st_size / 1024
    unit = f"{size:.0f} KB" if size < 1024 else f"{size / 1024:.1f} MB"
    print(
        f"{output} 를 만들었습니다. 실행 {len(runs)} 회, 케이스 {total} 건, 크기 {unit} 입니다."
    )
    if args.standalone:
        print("스크린샷을 파일 안에 담았으므로 이 파일만 전달하면 그대로 열립니다.")
    if args.open:
        webbrowser.open(output.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
