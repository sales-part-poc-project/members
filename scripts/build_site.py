#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""요약 JSON 으로부터 개인 시각화 페이지와 통합 대시보드를 만든다.

표준 라이브러리만 쓴다 (Python 3.9+). 네트워크·외부 CDN 을 쓰지 않으며,
생성한 HTML 은 완전 self-contained 라서 file:// 로 열어도 그대로 동작한다.

    python3 scripts/build_site.py --scaffold cc_usage_stats.json \
        --part 영업1파트 --name 홍길동 --date 2026-08-28 [--role "..."] [--highlight "..."] [--force]
    python3 scripts/build_site.py --check  data/영업1파트_홍길동_20260828.json
    python3 scripts/build_site.py --person data/영업1파트_홍길동_20260828.json
    python3 scripts/build_site.py --out _site [--data data]
    python3 scripts/build_site.py --out _site --demo

정본 스키마: docs/SUMMARY_SCHEMA.md
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import math
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "scripts" / "fixtures"
SCHEMA_VERSION = 1
KST = datetime.timezone(datetime.timedelta(hours=9), "KST")

# 화법 마커 10종 — scripts/cc_usage.py 의 MARKERS 와 이름이 정확히 같아야 한다.
MARKERS = ["불만·교정", "완곡·탐색", "검증요구", "강조·단정", "칭찬·수용",
           "위임·자율", "속도·긴급", "범위한정", "설명요구", "사과·완충"]

# 중첩 어디에 있어도 거부하는 키 (프롬프트 원문 · 성별 예상)
FORBIDDEN_KEYS = ("samples_shortest", "samples_longest", "samples_spread", "first_prompt", "gender")

AXIS_ORDER = ["delegation", "verification", "planning", "perfectionism", "exploration"]
AXIS_KO = {"delegation": "위임", "verification": "검증", "planning": "계획",
           "perfectionism": "완성도", "exploration": "탐색"}
AXIS_POLE = {"delegation": "통제형 → 위임형", "verification": "그대로 믿음 → 검증 집착",
             "planning": "즉흥형 → 계획형", "perfectionism": "한 번에 수용 → 완성도 집착",
             "exploration": "단정형 → 탐색형"}

# ── 9장 AI 사용 전문가 지수 (재미용) — docs/SUMMARY_SCHEMA.md 'expert_index 산식' 과 같아야 한다 ──
EI_FORMULA_VERSION = 1
EI_AXES = ["volume", "automation", "delegation", "assets", "omc"]
EI_AXIS_KO = {"volume": "규모", "automation": "자동화", "delegation": "위임",
              "assets": "자산", "omc": "OMC 활용"}
EI_AXIS_FULL = {"volume": "장기 세션 300개면 만점", "automation": "한 지시당 도구 40회면 만점",
                "delegation": "서브에이전트 메시지 비중 35%면 만점", "assets": "자산 점수 12점이면 만점",
                "omc": "OMC 비중 25% · 명령 6종이면 만점"}
EI_LEVELS = [(0, 19, "입문", "🌱"), (20, 39, "견습", "🔧"), (40, 59, "숙련", "⚙️"),
             (60, 79, "전문가", "🧠"), (80, 100, "마스터", "🚀")]

DOW_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DOW_KO = {"Mon": "월", "Tue": "화", "Wed": "수", "Thu": "목", "Fri": "금", "Sat": "토", "Sun": "일"}

ASSET_LABELS = [
    ("global_claude_md", "전역 CLAUDE.md"), ("project_claude_md", "프로젝트 CLAUDE.md"),
    ("rules", "룰 파일"), ("agents", "에이전트"), ("commands", "커맨드"), ("skills", "스킬"),
    ("hooks", "훅"), ("permissions_allow", "권한 허용"), ("statusline", "상태줄"),
    ("mcp_servers", "MCP 서버"), ("plugins", "플러그인"),
]

# ── 색 ────────────────────────────────────────────────────────────────────────
INK = "#17140F"
MUTED = "#8A7F72"
LINE = "#E4DCCF"
LINE2 = "#F0EAE0"
ACCENT = "#D8481F"
ACCENT2 = "#175B63"
SERIES = ["#D8481F", "#175B63", "#C79A2B", "#6B4E9E", "#2F7D4F", "#A8452F", "#4C7FA8", "#8A7F72"]


# ══════════════════════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════════════════════
def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def num(v, d=0):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def fmt_int(v) -> str:
    n = num(v)
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.1f}"
    return f"{int(n):,}"


def fmt_tok(v) -> str:
    n = int(num(v))
    a = abs(n)
    if a >= 1_000_000_000:
        return f"{n / 1e9:.1f}B"
    if a >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if a >= 1_000:
        return f"{n / 1e3:.0f}K"
    return str(n)


def tok_html(v) -> str:
    return f'<span title="{esc(fmt_int(v))}">{esc(fmt_tok(v))}</span>'


def fmt_pct(v, digits=0) -> str:
    return f"{num(v) * 100:.{digits}f}%"


def fmt_dur(sec) -> str:
    """초 → 사람이 읽는 시간. 45초 · 4분 52초 · 1시간 12분 · 18.2시간"""
    s = max(0.0, num(sec))
    if s < 60:
        return f"{int(round(s))}초"
    if s < 3600:
        m, r = divmod(int(round(s)), 60)
        return f"{m}분 {r:02d}초" if r else f"{m}분"
    if s < 36000:
        h, r = divmod(int(round(s)), 3600)
        return f"{h}시간 {r // 60}분" if r // 60 else f"{h}시간"
    return f"{s / 3600:.1f}시간"


def fmt_dec(v, digits=1) -> str:
    return f"{num(v):.{digits}f}"


def g(d, path, default=None):
    """점 경로로 안전하게 꺼낸다. 없거나 None 이면 default."""
    cur = d
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return default if cur is None else cur


def pair_list(v, limit=None):
    out = []
    for it in (v or []):
        if isinstance(it, (list, tuple)) and len(it) >= 2:
            out.append((str(it[0]), num(it[1])))
    return out[:limit] if limit else out


def str_list(v, limit=None):
    out = [str(x).strip() for x in (v or []) if isinstance(x, str) and str(x).strip()]
    return out[:limit] if limit else out


def heat_rgb(t: float, base=(216, 72, 31)) -> str:
    t = max(0.0, min(1.0, t))
    r = int(round(250 + (base[0] - 250) * t))
    gg = int(round(246 + (base[1] - 246) * t))
    b = int(round(240 + (base[2] - 240) * t))
    return f"rgb({r},{gg},{b})"


def heat_fg(t: float) -> str:
    return "#FFFFFF" if t > 0.58 else "#4A423A"


def heat_t(v, vmax) -> float:
    if not vmax:
        return 0.0
    return (max(0.0, num(v)) / float(vmax)) ** 0.65


def short_month(label: str) -> str:
    s = str(label)
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    return f"{m.group(1)[2:]}.{m.group(2)}" if m else s


def tiny_month(label: str) -> str:
    """소형 막대용 — 월 숫자만. 1월에는 연도를 붙여 구간이 넘어간 것을 표시한다."""
    s = str(label)
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if not m:
        return s
    mm = int(m.group(2))
    return f"{m.group(1)[2:]}/1" if mm == 1 else str(mm)


def sh(args, cwd=None, timeout=8) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        if r.returncode == 0:
            return (r.stdout or "").strip()
    except Exception:
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# 파일명 / 검증
# ══════════════════════════════════════════════════════════════════════════════
def parse_stem(stem: str):
    """'{파트}_{이름}_{YYYYMMDD}' → (파트, 이름, YYYYMMDD). 못 읽으면 None."""
    parts = stem.split("_")
    if len(parts) != 3:
        return None
    part, name, ymd = parts
    if not (part and name and re.fullmatch(r"\d{8}", ymd)):
        return None
    return part, name, ymd


def scan_forbidden(node, path="$"):
    hits = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if k in FORBIDDEN_KEYS:
                hits.append(p)
            hits.extend(scan_forbidden(v, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(scan_forbidden(v, f"{path}[{i}]"))
    return hits


def scan_long_strings(node, limit=500, path="$"):
    hits = []
    if isinstance(node, dict):
        for k, v in node.items():
            hits.extend(scan_long_strings(v, limit, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(scan_long_strings(v, limit, f"{path}[{i}]"))
    elif isinstance(node, str) and len(node) > limit:
        hits.append((path, len(node)))
    return hits


def _need_pairs(data, path, E, min_len=0):
    v = g(data, path)
    if not isinstance(v, list):
        E(f"{path}: 리스트여야 합니다 (현재 {type(v).__name__})")
        return
    for i, it in enumerate(v):
        if not (isinstance(it, (list, tuple)) and len(it) >= 2):
            E(f"{path}[{i}]: [\"이름\", 숫자] 형태의 쌍이어야 합니다")
            return
    if len(v) < min_len:
        E(f"{path}: {min_len}개 이상 필요합니다 (현재 {len(v)}개)")


def _need_text(data, path, E, label=None):
    v = g(data, path)
    if not isinstance(v, str) or not v.strip():
        E(f"{path}: 비어 있습니다 — {label or '내용을 채워 주세요'}")


def _need_strings(data, path, E, min_len, label=None):
    v = g(data, path)
    if not isinstance(v, list):
        E(f"{path}: 리스트여야 합니다 (현재 {type(v).__name__})")
        return
    filled = [x for x in v if isinstance(x, str) and x.strip()]
    if len(filled) < min_len:
        E(f"{path}: 비어 있지 않은 문자열 {min_len}개 이상 필요합니다 "
          f"(현재 {len(filled)}개) — {label or ''}".rstrip(" —"))


def validate(data, json_path: Path):
    """(errors, warnings) 를 한국어 문장 리스트로 돌려준다."""
    errors, warnings = [], []
    E, W = errors.append, warnings.append

    if not isinstance(data, dict):
        return ([f"최상위가 객체가 아닙니다 (현재 {type(data).__name__})"], [])

    # 1) 스키마 버전
    if data.get("schema_version") != SCHEMA_VERSION:
        E(f"schema_version: {SCHEMA_VERSION} 이어야 합니다 (현재 {data.get('schema_version')!r})")

    # 2) 파일명 ↔ 필드 일치
    parsed = parse_stem(json_path.stem)
    if parsed is None:
        E(f"파일명: '{json_path.name}' 이 '{{파트}}_{{이름}}_{{YYYYMMDD}}.json' 형식이 아닙니다 "
          f"(파트·이름에 언더스코어 '_' 나 공백을 쓰지 마세요)")
    else:
        f_part, f_name, f_ymd = parsed
        if data.get("part") != f_part:
            E(f"part: {data.get('part')!r} 이 파일명의 {f_part!r} 와 다릅니다")
        if data.get("name") != f_name:
            E(f"name: {data.get('name')!r} 이 파일명의 {f_name!r} 와 다릅니다")
        d = data.get("date")
        if not (isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)):
            E(f"date: 'YYYY-MM-DD' 형식이어야 합니다 (현재 {d!r})")
        elif d.replace("-", "") != f_ymd:
            E(f"date: {d!r} 이 파일명의 {f_ymd!r} 와 다릅니다")

    # 3) 금지 키
    for p in scan_forbidden(data):
        E(f"금지 키: {p} — 프롬프트 원문·성별 예상은 JSON 에 넣지 않습니다 "
          f"(docs/SUMMARY_SCHEMA.md '절대 넣지 말 것')")

    # 4) 필수 블록
    for key, kind in (("coverage", dict), ("summary", dict), ("scale", dict),
                      ("projects_top", list), ("workflow", dict), ("speech", dict),
                      ("assets", dict), ("cases", list), ("profile", dict), ("feedback", dict)):
        if not isinstance(data.get(key), kind):
            E(f"{key}: {'객체' if kind is dict else '리스트'}가 필요합니다 "
              f"(현재 {type(data.get(key)).__name__})")
    for key in ("role", "highlight", "script_commit"):
        if not isinstance(data.get(key), str):
            E(f"{key}: 문자열이어야 합니다 (값이 없으면 \"\")")
    if not isinstance(data.get("env"), dict):
        E("env: 객체가 필요합니다 ({\"claude_code\": \"\", \"os\": \"\", \"python\": \"\"})")

    # 5) coverage
    if isinstance(data.get("coverage"), dict):
        for k in ("history", "session_stats", "transcripts"):
            v = g(data, f"coverage.{k}")
            if v is not None and not isinstance(v, dict):
                E(f"coverage.{k}: {{\"from\": ..., \"to\": ...}} 객체이거나 null 이어야 합니다")
        if not isinstance(g(data, "coverage.speech_sample_size", 0), (int, float)):
            E("coverage.speech_sample_size: 숫자여야 합니다")
        if not isinstance(g(data, "coverage.failed_items", []), list):
            E("coverage.failed_items: 리스트여야 합니다 (없으면 [])")

    # 6) scale
    by_hour = g(data, "scale.by_hour")
    if not (isinstance(by_hour, list) and len(by_hour) == 24):
        E(f"scale.by_hour: 길이 24 리스트여야 합니다 "
          f"(현재 {len(by_hour) if isinstance(by_hour, list) else type(by_hour).__name__})")
    elif not all(isinstance(x, (int, float)) for x in by_hour):
        E("scale.by_hour: 24개 항목이 모두 숫자여야 합니다")
    for k in ("sessions_long", "active_months", "tool_calls_long", "natural_prompts",
              "slash_prompts", "subagent_msgs_30d", "tok_out_30d", "thinking_tok_30d",
              "tok_cache_read_30d"):
        v = g(data, f"scale.{k}")
        if not isinstance(v, (int, float)):
            E(f"scale.{k}: 숫자여야 합니다 (현재 {v!r})")
        elif v < 0:
            E(f"scale.{k}: 음수일 수 없습니다 ({v})")
    for k in ("sessions_by_month", "prompts_by_month", "by_dow"):
        _need_pairs(data, f"scale.{k}", E)

    # 7) projects_top
    if isinstance(data.get("projects_top"), list):
        for i, row in enumerate(data["projects_top"]):
            if not isinstance(row, dict):
                E(f"projects_top[{i}]: 객체여야 합니다")
                continue
            if not str(row.get("project") or "").strip():
                E(f"projects_top[{i}].project: 프로젝트 이름이 비어 있습니다")
    if not isinstance(data.get("projects_other_count"), (int, float)):
        E("projects_other_count: 숫자여야 합니다 (없으면 0)")

    # 8) workflow
    if not isinstance(g(data, "workflow.automation_depth"), (int, float)):
        E("workflow.automation_depth: 숫자여야 합니다 (도구 호출 / 직접 프롬프트)")
    for k in ("tools_top", "subagent_types", "models", "effort",
              "permission_mode", "mcp_servers", "skills"):
        _need_pairs(data, f"workflow.{k}", E)
    if not isinstance(g(data, "workflow.subagent_msg_ratio"), (int, float)):
        E("workflow.subagent_msg_ratio: 숫자여야 합니다 (0~1)")
    td = g(data, "workflow.turn_duration")
    if td is None:
        W("workflow.turn_duration: 없습니다 — 한 지시당 실행 시간. 집계 스크립트를 다시 돌려 스캐폴드하면 채워집니다")
    elif not isinstance(td, dict):
        E("workflow.turn_duration: 객체이거나 null 이어야 합니다")
    else:
        for k in ("n", "median_sec", "p25_sec", "p75_sec", "p90_sec", "max_sec", "mean_sec", "total_sec"):
            if not isinstance(td.get(k), (int, float)):
                E(f"workflow.turn_duration.{k}: 숫자여야 합니다 (현재 {td.get(k)!r})")
        _need_pairs(data, "workflow.turn_duration.buckets", E)
    omc = g(data, "workflow.omc")
    if not isinstance(omc, dict):
        E("workflow.omc: 객체여야 합니다 (cc_usage_stats.json 의 omc 블록)")
    else:
        _need_pairs(data, "workflow.omc.commands", E)
        for k in ("omc_ratio", "prompts_with_omc", "prompts_total"):
            if not isinstance(omc.get(k), (int, float)):
                E(f"workflow.omc.{k}: 숫자여야 합니다 (현재 {omc.get(k)!r})")
        for k in ("omc_ratio", "slash_omc_ratio", "keyword_ratio"):
            if isinstance(omc.get(k), (int, float)) and not (0 <= omc[k] <= 1.0001):
                E(f"workflow.omc.{k}: 비중(0~1) 범위를 벗어납니다 ({omc[k]})")
        if not isinstance(omc.get("distinct_commands"), (int, float)):
            E("workflow.omc.distinct_commands: 숫자여야 합니다")
        if isinstance(omc.get("prompts_with_omc"), (int, float)) and \
                isinstance(omc.get("prompts_total"), (int, float)) and \
                omc["prompts_with_omc"] > omc["prompts_total"]:
            E(f"workflow.omc: prompts_with_omc({omc['prompts_with_omc']}) 가 "
              f"prompts_total({omc['prompts_total']}) 보다 큽니다")
    for k in ("models", "effort", "permission_mode"):
        for label, v in pair_list(g(data, f"workflow.{k}")):
            if not (0 <= v <= 1.0001):
                E(f"workflow.{k}: '{label}' 의 값 {v} 가 비중(0~1) 범위를 벗어납니다 "
                  f"— 카운트가 아니라 비중으로 넣어 주세요")

    # 9) speech
    pol = g(data, "speech.politeness")
    if not isinstance(pol, dict) or any(k not in pol for k in ("formal", "casual", "noun")):
        E("speech.politeness: {\"formal\":…, \"casual\":…, \"noun\":…} 세 키가 모두 필요합니다")
    else:
        s = sum(num(pol.get(k)) for k in ("formal", "casual", "noun"))
        if abs(s - 1.0) > 0.05:
            W(f"speech.politeness: 세 값의 합이 {s:.3f} 입니다 (1.0 근처여야 자연스럽습니다)")
    mk = g(data, "speech.markers_per_100")
    if not isinstance(mk, dict):
        E("speech.markers_per_100: 객체여야 합니다 (화법 마커 10종)")
    else:
        missing = [m for m in MARKERS if m not in mk]
        if missing:
            E(f"speech.markers_per_100: 마커 {len(missing)}종이 빠졌습니다 — {', '.join(missing)}")
        extra = [k for k in mk if k not in MARKERS]
        if extra:
            W(f"speech.markers_per_100: 정의에 없는 마커가 있습니다 — {', '.join(extra)} "
              f"(docs/SPEECH_ANALYSIS.md 의 10종과 이름이 같아야 비교됩니다)")
        for k in MARKERS:
            if k in mk and not isinstance(mk[k], (int, float)):
                E(f"speech.markers_per_100['{k}']: 숫자여야 합니다 (현재 {mk[k]!r})")
    for path, keys in (("speech.len_chars", ("median", "p90", "max")),
                       ("speech.gap_sec", ("median", "p25", "p90"))):
        v = g(data, path)
        if not isinstance(v, dict) or any(k not in v for k in keys):
            E(f"{path}: {', '.join(keys)} 키가 모두 필요합니다")
    for k in ("sentences_per_prompt", "short_followup_ratio", "laugh_prompts", "emoji_prompts",
              "korean_prompts", "non_korean_prompts", "english_mixed_ratio"):
        if not isinstance(g(data, f"speech.{k}"), (int, float)):
            E(f"speech.{k}: 숫자여야 합니다")
    for k in ("endings_top", "first_words_top", "vocab_top"):
        _need_pairs(data, f"speech.{k}", E)
    if not isinstance(g(data, "speech.punctuation"), dict):
        E("speech.punctuation: {\"question\":…, \"exclaim\":…, \"none_ratio\":…} 객체여야 합니다")

    # 10) 서술 필수 필드
    _need_text(data, "summary.one_liner", E, "1장 한 줄 요약")
    for k, ko in (("habit", "습관"), ("effect", "효과"), ("pain", "불편")):
        if not str(g(data, f"summary.{k}", "")).strip():
            W(f"summary.{k}: 비어 있습니다 ({ko} 1가지) — 히어로 칩이 비어 보입니다")
    _need_strings(data, "speech.style_summary", E, 3, "5-5 말투 3줄 요약")
    _need_strings(data, "speech.reproduced_prompts", E, 3,
                  "5-6 가상 프롬프트 3개 (실제 표본 복사 금지)")
    _need_text(data, "profile.definition", E, "8장 한 문장 정의")
    if not str(g(data, "scale.rhythm_note", "")).strip():
        W("scale.rhythm_note: 비어 있습니다 (2장 마지막 1~2줄)")
    if not str(g(data, "workflow.style_note", "")).strip():
        W("workflow.style_note: 비어 있습니다 (4장 작업 방식 3~5줄)")

    # 11) profile.axes
    axes = g(data, "profile.axes")
    if not isinstance(axes, dict):
        E("profile.axes: 객체여야 합니다 (5축 모두)")
    else:
        for k in AXIS_ORDER:
            if k not in axes:
                E(f"profile.axes.{k}: 축이 빠졌습니다 ({AXIS_POLE[k]})")
            elif not isinstance(axes[k], int) or isinstance(axes[k], bool):
                E(f"profile.axes.{k}: 1~5 정수여야 합니다 (현재 {axes[k]!r})")
            elif not (1 <= axes[k] <= 5):
                E(f"profile.axes.{k}: 1~5 범위여야 합니다 (현재 {axes[k]})")
        for k in axes:
            if k not in AXIS_ORDER:
                W(f"profile.axes.{k}: 정의에 없는 축입니다 (5축: {', '.join(AXIS_ORDER)})")
    ev = g(data, "profile.axes_evidence")
    if not isinstance(ev, dict):
        E("profile.axes_evidence: 객체여야 합니다 (축별 근거 한 줄)")
    else:
        empty = [k for k in AXIS_ORDER if not str(ev.get(k, "")).strip()]
        if empty:
            W(f"profile.axes_evidence: 근거가 비어 있는 축 — {', '.join(empty)}")
    if not isinstance(g(data, "profile.teammate_tips", []), list):
        E("profile.teammate_tips: 리스트여야 합니다")

    # 12) cases
    if isinstance(data.get("cases"), list):
        real = [c for c in data["cases"] if isinstance(c, dict) and str(c.get("title") or "").strip()]
        if len(real) < 3:
            E(f"cases: 제목이 있는 대표 사례가 3건 이상 필요합니다 (현재 {len(real)}건)")
        for i, c in enumerate(data["cases"]):
            if not isinstance(c, dict):
                E(f"cases[{i}]: 객체여야 합니다")
                continue
            for k in ("title", "task", "outcome"):
                if not str(c.get(k) or "").strip():
                    W(f"cases[{i}].{k}: 비어 있습니다")

    # 13) feedback
    for k, ko in (("works_well", "효과가 확실한 작업 유형"), ("works_poorly", "잘 안 되는 작업 유형"),
                  ("blockers", "막혔던 지점"), ("proposals", "파트 차원 제안")):
        _need_strings(data, f"feedback.{k}", E, 1, ko)

    # 14) assets
    if not isinstance(g(data, "assets.counts"), dict):
        E("assets.counts: 객체여야 합니다")
    if not isinstance(g(data, "assets.share_worthy", []), list):
        E("assets.share_worthy: 리스트여야 합니다 (없으면 [])")

    # 15) fun (null 허용)
    fun = data.get("fun", None)
    if fun is not None:
        if not isinstance(fun, dict):
            E("fun: 객체이거나 null 이어야 합니다 (9장을 지웠으면 null)")
        else:
            for k in ("mbti", "age_band", "blood_type"):
                blk = fun.get(k)
                if blk is None:
                    W(f"fun.{k}: 비어 있습니다")
                elif not isinstance(blk, dict) or any(x not in blk for x in ("value", "strength", "basis")):
                    E(f"fun.{k}: {{\"value\":…, \"strength\":…, \"basis\":…}} 세 키가 필요합니다")
            if not str(fun.get("nickname") or "").strip():
                W("fun.nickname: 비어 있습니다 (별명이 없으면 히어로에 표시되지 않습니다)")

    # 16) expert_index (재미용 지수 — --scaffold 가 계산한다)
    ei = data.get("expert_index")
    if not isinstance(ei, dict):
        E("expert_index: 객체여야 합니다 — `--scaffold` 가 계산합니다 "
          "(docs/SUMMARY_SCHEMA.md 'expert_index 산식')")
    else:
        s = ei.get("score")
        if not isinstance(s, int) or isinstance(s, bool):
            E(f"expert_index.score: 0~100 정수여야 합니다 (현재 {s!r})")
        elif not (0 <= s <= 100):
            E(f"expert_index.score: 0~100 범위여야 합니다 (현재 {s})")
        bd = ei.get("breakdown")
        if not isinstance(bd, dict):
            E("expert_index.breakdown: 객체여야 합니다 (5축)")
        else:
            miss = [k for k in EI_AXES if k not in bd]
            if miss:
                E(f"expert_index.breakdown: 축 {len(miss)}개가 빠졌습니다 — {', '.join(miss)}")
            for k in EI_AXES:
                if k in bd and not isinstance(bd[k], (int, float)):
                    E(f"expert_index.breakdown.{k}: 숫자여야 합니다 (0~20)")
        if not isinstance(ei.get("formula_version"), int):
            E("expert_index.formula_version: 정수여야 합니다")
        elif ei["formula_version"] != EI_FORMULA_VERSION:
            W(f"expert_index.formula_version: {ei['formula_version']} 입니다 "
              f"(현재 산식 v{EI_FORMULA_VERSION}) — 버전이 다른 보고서끼리는 점수를 비교하지 않습니다")
        if not str(ei.get("level") or "").strip():
            W("expert_index.level: 비어 있습니다")
        if isinstance(ei.get("score"), int) and isinstance(bd, dict):
            calc = sum(num(bd.get(k)) for k in EI_AXES)
            if abs(calc - ei["score"]) > 1.0:
                W(f"expert_index: breakdown 합계 {calc:.1f} 와 score {ei['score']} 가 다릅니다 "
                  f"— 손으로 고치지 말고 `--scaffold` 로 다시 계산하세요")

    # 17) 길이 경고
    for path, n in scan_long_strings(data):
        W(f"{path}: 문자열이 {n}자입니다 (500자 초과) — 프롬프트 원문이 섞이지 않았는지 확인하세요")

    return errors, warnings


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "파일이 없습니다"
    except json.JSONDecodeError as e:
        return None, f"JSON 문법 오류 — {e.lineno}행 {e.colno}열: {e.msg}"
    except Exception as e:  # noqa: BLE001
        return None, f"읽기 실패 — {e}"


# ══════════════════════════════════════════════════════════════════════════════
# 전문가 지수 (재미용) — 산식은 docs/SUMMARY_SCHEMA.md 와 같아야 한다
# ══════════════════════════════════════════════════════════════════════════════
def clamp01(x) -> float:
    return max(0.0, min(1.0, num(x)))


def asset_points(counts: dict) -> int:
    c = counts or {}
    p = 2 if num(c.get("global_claude_md")) > 0 else 0
    for key, cap in (("rules", 3), ("agents", 2), ("commands", 2), ("skills", 2),
                     ("hooks", 2), ("mcp_servers", 2), ("project_claude_md", 3)):
        p += min(int(num(c.get(key))), cap)
    return p


def expert_index(*, sessions_long, automation_depth, subagent_msg_ratio,
                 counts, omc_ratio, distinct_commands) -> dict:
    ap = asset_points(counts)
    bd = {
        "volume": 20 * clamp01(math.log10(1 + max(0.0, num(sessions_long))) / math.log10(301)),
        "automation": 20 * clamp01(num(automation_depth) / 40.0),
        "delegation": 20 * clamp01(num(subagent_msg_ratio) / 0.35),
        "assets": 20 * clamp01(ap / 12.0),
        "omc": 20 * clamp01(0.5 * num(omc_ratio) / 0.25 + 0.5 * num(distinct_commands) / 6.0),
    }
    score = int(round(sum(bd.values())))
    score = max(0, min(100, score))
    level, emoji = "입문", "🌱"
    for lo, hi, ko, em in EI_LEVELS:
        if lo <= score <= hi:
            level, emoji = ko, em
            break
    return {
        "formula_version": EI_FORMULA_VERSION,
        "score": score, "level": level, "emoji": emoji,
        "breakdown": {k: round(v, 1) for k, v in bd.items()},
        "inputs": {"sessions_long": int(num(sessions_long)),
                   "automation_depth": round(num(automation_depth), 1),
                   "subagent_msg_ratio": round(num(subagent_msg_ratio), 3),
                   "asset_points": ap,
                   "omc_ratio": round(num(omc_ratio), 3),
                   "distinct_commands": int(num(distinct_commands))},
    }


def ei_level_of(score) -> tuple:
    s = int(num(score))
    for lo, hi, ko, em in EI_LEVELS:
        if lo <= s <= hi:
            return ko, em
    return "입문", "🌱"


# ══════════════════════════════════════════════════════════════════════════════
# 스캐폴드 — cc_usage_stats.json → 요약 JSON 뼈대
# ══════════════════════════════════════════════════════════════════════════════
CONTAINER_DIRS = {"WebstormProjects", "IdeaProjects", "PycharmProjects", "Projects", "projects",
                  "workspace", "Workspace", "dev", "Dev", "src", "repos", "Repos", "git",
                  "work", "Work", "Documents", "Desktop", "code", "Code", "github", "GitHub"}


def short_project(raw: str) -> str:
    """'-Users-hong-WebstormProjects-crm-api' → 'crm-api' (최선 추정. 사람이 고쳐도 된다)."""
    s = str(raw or "").strip()
    if not s:
        return "?"
    if not s.startswith("-"):
        return s
    toks = [t for t in s.split("-") if t]
    # 홈 디렉터리 접두어 제거: Users/<사람> 또는 home/<사람>
    if len(toks) >= 2 and toks[0] in ("Users", "home"):
        toks = toks[2:]
    while toks and toks[0] in CONTAINER_DIRS:
        toks = toks[1:]
    return "-".join(toks) if toks else s


def normalize_shares(counter_pairs, limit=None, digits=2):
    """[[이름, 카운트], …] → [[이름, 비중]] (합 1.0 이 되도록 최댓값에서 오차 보정)."""
    items = pair_list(counter_pairs)
    total = sum(v for _, v in items)
    if not items or total <= 0:
        return []
    items = sorted(items, key=lambda x: -x[1])
    if limit:
        items = items[:limit]
        total = sum(v for _, v in items) or total
    out = [[k, round(v / total, digits)] for k, v in items]
    drift = round(1.0 - sum(v for _, v in out), digits)
    if out and abs(drift) >= 10 ** (-digits) / 2:
        out[0][1] = round(out[0][1] + drift, digits)
    return out


def turn_duration_block(td):
    """cc_usage_stats.json 의 turn_durations → 요약 JSON workflow.turn_duration. 블록이 없으면 None."""
    if not isinstance(td, dict) or not td:
        return None
    return {
        "n": int(num(td.get("n"))),
        "median_sec": round(num(td.get("median_sec")), 1),
        "p25_sec": round(num(td.get("p25_sec")), 1),
        "p75_sec": round(num(td.get("p75_sec")), 1),
        "p90_sec": round(num(td.get("p90_sec")), 1),
        "max_sec": round(num(td.get("max_sec")), 1),
        "mean_sec": round(num(td.get("mean_sec")), 1),
        "total_sec": round(num(td.get("total_sec")), 1),
        "buckets": [[str(k), int(num(v))] for k, v in pair_list(td.get("buckets"))],
    }


def normalize_dow(pairs):
    d = {str(k): num(v) for k, v in pair_list(pairs)}
    return [[k, int(d.get(k, 0))] for k in DOW_ORDER]


def detect_env() -> dict:
    ver = ""
    raw = sh(["claude", "--version"])
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", raw)
    if m:
        ver = m.group(1)
    try:
        osname = f"{platform.system()} {platform.release()}".strip()
    except Exception:
        osname = ""
    try:
        pyver = platform.python_version()
    except Exception:
        pyver = ""
    return {"claude_code": ver, "os": osname, "python": pyver}


def build_scaffold(stats: dict, *, part: str, name: str, date: str,
                   role: str = "", highlight: str = "") -> dict:
    totals = stats.get("totals") or {}
    ssl = stats.get("session_stats_longwindow") or {}
    prompts = stats.get("prompts") or {}
    speech = stats.get("speech") or {}
    cust = stats.get("customization") or {}
    omc_raw = stats.get("omc") or {}

    human = num(totals.get("human_turns"))
    tool_calls = num(totals.get("tool_calls"))
    automation = round(tool_calls / human, 1) if human else 0.0
    asst = num(totals.get("assistant_msgs"))
    sub = num(totals.get("subagent_msgs"))
    sub_ratio = round(sub / (asst + sub), 2) if (asst + sub) else 0.0

    # 0장 집계 구간 — history 의 실제 시작·종료일은 stats 에 없어 null 로 둔다
    tp_first = [r.get("first") for r in (stats.get("projects") or []) if r.get("first")]
    tp_last = [r.get("last") for r in (stats.get("projects") or []) if r.get("last")]
    transcripts = ({"from": min(tp_first)[:10], "to": max(tp_last)[:10]}
                   if tp_first and tp_last else None)
    session_stats = ({"from": str(ssl.get("first_session"))[:10], "to": str(ssl.get("last_session"))[:10]}
                     if ssl.get("first_session") and ssl.get("last_session") else None)

    # 3장 프로젝트 — 직접 프롬프트 많은 순 상위 10개
    rows = sorted((stats.get("projects") or []), key=lambda r: -num(r.get("human_turns")))
    projects_top = []
    for r in rows[:10]:
        tt = pair_list(r.get("top_tools"))
        projects_top.append({
            "project": short_project(r.get("project")),
            "sessions": int(num(r.get("sessions"))),
            "active_days": int(num(r.get("active_days"))),
            "human_turns": int(num(r.get("human_turns"))),
            "tool_calls": int(sum(v for _, v in tt)),  # 상위 도구 합계 근사
            "main_model": (pair_list(r.get("top_models")) or [("", 0)])[0][0],
            "period": (f"{str(r.get('first'))[:10]} ~ {str(r.get('last'))[:10]}"
                       if r.get("first") and r.get("last") else ""),
        })

    counts = {
        "global_claude_md": 1 if num(cust.get("global_CLAUDE_md_bytes")) > 0 else 0,
        "rules": len(cust.get("rules_files") or []),
        "agents": len(cust.get("global_agents") or []),
        "commands": len(cust.get("global_commands") or []),
        "skills": len(cust.get("global_skills") or []),
        "hooks": len(cust.get("hooks") or []),
        "permissions_allow": int(num(cust.get("permissions_allow_count"))),
        "statusline": bool(cust.get("statusLine")),
        "mcp_servers": len(set(g(stats, "global.mcpServers_global", []) or [])
                           | {k for k, _ in pair_list(stats.get("mcpServers_projectScope"))}),
        "plugins": len(pair_list(stats.get("pluginUsage"))),
        "project_claude_md": sum(1 for a in (stats.get("project_assets") or [])
                                 if num(a.get("CLAUDE_md")) > 0),
    }

    pol_raw = speech.get("politeness") or {}
    pol = normalize_shares([["formal", num(pol_raw.get("존댓말"))],
                            ["casual", num(pol_raw.get("반말"))],
                            ["noun", num(pol_raw.get("중립·체언종결"))]])
    pol_map = {k: v for k, v in pol}
    politeness = {k: pol_map.get(k, 0) for k in ("formal", "casual", "noun")}

    punct = speech.get("punctuation") or {}
    n_sp = num(speech.get("sample_size")) or 1
    gap = speech.get("inter_prompt_gap_sec") or {}
    lench = prompts.get("len_chars") or {}

    omc_block = {
        "commands": [[k, int(v)] for k, v in pair_list(omc_raw.get("commands"))],
        "distinct_commands": int(num(omc_raw.get("distinct_commands"))),
        "prompts_with_omc": int(num(omc_raw.get("prompts_with_omc"))),
        "prompts_total": int(num(omc_raw.get("prompts_total"))),
        "omc_ratio": round(num(omc_raw.get("omc_ratio")), 3),
        "slash_omc_ratio": round(num(omc_raw.get("slash_omc_ratio")), 3),
        "keyword_ratio": round(num(omc_raw.get("keyword_ratio")), 3),
        "keyword_forms": [[k, int(v)] for k, v in pair_list(omc_raw.get("keyword_forms"))],
        "by_month": [[k, int(v)] for k, v in pair_list(omc_raw.get("by_month"))],
    }

    doc = {
        "schema_version": SCHEMA_VERSION,
        "part": part, "name": name, "date": date,
        "role": role or "", "highlight": highlight or "",
        "env": detect_env(),
        "coverage": {
            "history": None,          # history.jsonl 의 실제 시작~종료일은 집계 결과에 없다 — 직접 채운다
            "session_stats": session_stats,
            "transcripts": transcripts,
            "speech_sample_size": int(num(speech.get("sample_size"))),
            "failed_items": [],
        },
        "summary": {"one_liner": "", "habit": "", "effect": "", "pain": ""},
        "scale": {
            "sessions_long": int(num(ssl.get("sessions"))),
            "active_months": len(pair_list(ssl.get("sessions_by_month"))),
            "tool_calls_long": int(num(ssl.get("total_tool_calls"))),
            "natural_prompts": int(num(prompts.get("natural_prompt_count"))),
            "slash_prompts": int(sum(v for _, v in pair_list(prompts.get("slash_top")))),
            "subagent_msgs_30d": int(sub),
            "tok_out_30d": int(num(totals.get("tok_out"))),
            "thinking_tok_30d": int(num(totals.get("thinking_tok"))),
            "tok_cache_read_30d": int(num(totals.get("tok_cache_read"))),
            "sessions_by_month": [[k, int(v)] for k, v in pair_list(ssl.get("sessions_by_month"))],
            "prompts_by_month": [[k, int(v)] for k, v in pair_list(prompts.get("by_month"))],
            "by_hour": [int(num(x)) for x in (prompts.get("by_hour") or [0] * 24)][:24],
            "by_dow": normalize_dow(prompts.get("by_dow")),
            "rhythm_note": "",
        },
        "projects_top": projects_top,
        "projects_other_count": max(0, len(rows) - len(projects_top)),
        "workflow": {
            "automation_depth": automation,
            "turn_duration": turn_duration_block(stats.get("turn_durations")),
            "tools_top": [[k, int(v)] for k, v in pair_list(stats.get("tools_all"), 10)],
            "omc": omc_block,
            "subagent_types": [[k, int(v)] for k, v in pair_list(stats.get("subagent_types"), 10)],
            "subagent_msg_ratio": sub_ratio,
            "models": normalize_shares(stats.get("models_all"), 6),
            "effort": normalize_shares(stats.get("effort"), 6),
            "permission_mode": normalize_shares(stats.get("permissionMode"), 6),
            "mcp_servers": [[k, int(v)] for k, v in pair_list(stats.get("mcp_servers_called"), 10)],
            "skills": [[k, int(v)] for k, v in pair_list(stats.get("skillUsage"), 10)],
            "style_note": "",
        },
        "speech": {
            "politeness": politeness,
            "endings_top": [[k, int(v)] for k, v in pair_list(speech.get("endings_top"), 5)],
            "first_words_top": [[k, int(v)] for k, v in pair_list(speech.get("first_words_top"), 5)],
            "vocab_top": [[k, int(v)] for k, v in pair_list(speech.get("vocab_top"), 10)],
            "markers_per_100": {m: round(num((speech.get("markers_per_100") or {}).get(m)), 1)
                                for m in MARKERS},
            "len_chars": {"median": int(num(lench.get("median"))), "p90": int(num(lench.get("p90"))),
                          "max": int(num(lench.get("max")))},
            "sentences_per_prompt": num((speech.get("sentences_per_prompt") or {}).get("avg")),
            "gap_sec": {"median": int(num(gap.get("median"))), "p25": int(num(gap.get("p25"))),
                        "p90": int(num(gap.get("p90")))},
            "short_followup_ratio": num(speech.get("short_followup_ratio")),
            "laugh_prompts": int(num(speech.get("laugh_prompts"))),
            "emoji_prompts": int(num(speech.get("emoji_prompts"))),
            "korean_prompts": int(num(prompts.get("korean_prompts"))),
            "non_korean_prompts": int(num(prompts.get("non_korean_prompts"))),
            "english_mixed_ratio": num(speech.get("english_mixed_ratio")),
            "punctuation": {"question": int(num(punct.get("물음표"))),
                            "exclaim": int(num(punct.get("느낌표"))),
                            "none_ratio": round(num(punct.get("문장부호_없음")) / n_sp, 2)},
            "style_summary": [],
            "reproduced_prompts": [],
        },
        "assets": {"counts": counts, "share_worthy": []},
        "cases": [],
        "profile": {
            "axes": {k: None for k in AXIS_ORDER},
            "axes_evidence": {k: "" for k in AXIS_ORDER},
            "rhythm": "", "interest": "", "definition": "", "teammate_tips": [],
        },
        "fun": {
            "mbti": {"value": "", "strength": "", "basis": ""},
            "age_band": {"value": "", "strength": "", "basis": ""},
            "blood_type": {"value": "", "strength": "없음(무작위)", "basis": ""},
            "nickname": "", "pair_programming": "",
        },
        "expert_index": expert_index(
            sessions_long=ssl.get("sessions"), automation_depth=automation,
            subagent_msg_ratio=sub_ratio, counts=counts,
            omc_ratio=omc_block["omc_ratio"], distinct_commands=omc_block["distinct_commands"]),
        "feedback": {"works_well": [], "works_poorly": [], "blockers": [], "proposals": []},
        "script_commit": sh(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT)),
    }
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# HTML 뼈대 / 스타일 (완전 self-contained — 외부 CDN·폰트·스크립트 없음)
# ══════════════════════════════════════════════════════════════════════════════
CSS = """
:root{
  --bg:#F4F1EA; --card:#FFFFFF; --ink:#17140F; --ink2:#4A423A; --muted:#8A7F72;
  --line:#E4DCCF; --line2:#F0EAE0; --soft:#FAF7F1;
  --accent:#D8481F; --accent-soft:#FBEADF; --accent2:#175B63; --accent2-soft:#E2EEEF;
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.65;
  letter-spacing:-.01em;
  font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Malgun Gothic","맑은 고딕",sans-serif}
a{color:var(--accent2);text-underline-offset:2px}
h1,h2,h3,h4{margin:0}
p{margin:0 0 10px}
ul{margin:0;padding-left:18px}
li{margin:0 0 6px}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px 60px}
.num{font-variant-numeric:tabular-nums}

/* 히어로 */
.hero{background:var(--ink);color:#F7F3EC;padding:42px 0 38px;border-bottom:6px solid var(--accent)}
.hero .in{max-width:1120px;margin:0 auto;padding:0 20px}
.hero-meta{font-size:12px;letter-spacing:.16em;color:#B0A493;margin-bottom:12px}
.hero-name{font-size:clamp(30px,6vw,52px);line-height:1.08;font-weight:800;letter-spacing:-.035em}
.nick{display:inline-block;font-size:15px;font-weight:700;color:#FFB59B;background:rgba(216,72,31,.18);
  border:1px solid rgba(216,72,31,.45);padding:4px 11px;border-radius:999px;
  vertical-align:middle;margin-left:10px;letter-spacing:0}
.hero-line{font-size:clamp(15px,2.3vw,19px);color:#E9DFD2;margin:14px 0 16px;max-width:74ch}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.17);border-radius:10px;
  padding:7px 12px;font-size:13px;color:#E8DFD3;max-width:100%}
.chip b{color:#FF9E78;font-weight:700;margin-right:7px;font-size:11px;letter-spacing:.09em}
.hero-role{margin-top:16px;font-size:12.5px;color:#968A79}
.hero-score{margin-top:18px;display:inline-flex;align-items:center;gap:12px;
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.16);border-radius:14px;padding:10px 16px}
.hero-score .sc{font-size:30px;font-weight:800;letter-spacing:-.04em;color:#FFCDB8}
.hero-score .lv{font-size:13px;color:#D8CCBC}
.hero-score .fy{font-size:11px;color:#8E8271}

/* KPI */
.kpis{display:grid;grid-template-columns:repeat(7,1fr);gap:12px;margin:30px 0 36px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 14px}
.kpi-k{font-size:12px;color:var(--muted);margin-bottom:5px}
.kpi-v{font-size:clamp(21px,3vw,29px);font-weight:800;letter-spacing:-.045em;line-height:1.12;
  font-variant-numeric:tabular-nums}
.kpi-u{font-size:.55em;font-weight:700;color:var(--muted);margin-left:2px;letter-spacing:0}
.tag{display:inline-block;font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:999px;margin-top:7px}
.tag-long{background:var(--accent2-soft);color:var(--accent2)}
.tag-30d{background:var(--accent-soft);color:#A8380F}

/* 섹션 */
.sec{margin:0 0 38px}
.seclabel{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
  margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--ink)}
.secnum{font-size:11.5px;font-weight:800;color:var(--accent);letter-spacing:.12em}
.sectitle{font-size:19px;font-weight:800;letter-spacing:-.025em}
.secsub{margin-left:auto;font-size:12px;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.card+.card{margin-top:14px}
.cardtitle{font-size:11.5px;font-weight:700;color:var(--muted);letter-spacing:.07em;margin-bottom:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;align-items:start}
.note{font-size:13.5px;color:var(--ink2);margin-top:12px;padding-top:12px;border-top:1px dashed var(--line)}

/* 가로막대 */
.barlist{display:flex;flex-direction:column;gap:7px}
.barrow{display:grid;grid-template-columns:minmax(72px,27%) 1fr auto;gap:10px;align-items:center;font-size:13px}
.barlabel{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink2)}
.bartrack{background:var(--line2);border-radius:5px;height:11px;overflow:hidden}
.barfill{display:block;height:100%;border-radius:5px;min-width:2px}
.barval{font-variant-numeric:tabular-nums;font-size:12.5px;color:var(--muted);min-width:56px;text-align:right}

/* 스택 바 */
.stack{display:flex;height:26px;border-radius:7px;overflow:hidden;border:1px solid var(--line)}
.stack span{display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;
  color:#fff;min-width:0;overflow:hidden;white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:9px;font-size:12px;color:var(--ink2)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}

/* 시간대 스트립 */
.hours{display:grid;grid-template-columns:repeat(24,1fr);gap:2px}
.hours div{height:36px;border-radius:3px;border:1px solid rgba(0,0,0,.04)}
.hourlab{display:grid;grid-template-columns:repeat(24,1fr);gap:2px;margin-top:5px;
  font-size:9.5px;color:var(--muted);text-align:center}

/* 표 */
.scrollx{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tbl{width:100%;border-collapse:collapse;font-size:13px;min-width:620px}
.tbl th{text-align:left;font-size:11.5px;color:var(--muted);font-weight:700;padding:8px 10px;
  border-bottom:1px solid var(--line);white-space:nowrap}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
.tbl .r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tbl tr:last-child td{border-bottom:none}
.pname{font-weight:700}
.minibar{height:5px;background:var(--line2);border-radius:3px;margin-top:5px;overflow:hidden;max-width:220px}
.minibar span{display:block;height:100%;background:var(--accent);border-radius:3px}

/* 칩·알약 */
.pills{display:flex;flex-wrap:wrap;gap:7px}
.pill{background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:5px 11px;
  font-size:12.5px;color:var(--ink2)}
.pill b{font-weight:700;color:var(--accent2);margin-left:6px;font-variant-numeric:tabular-nums}
.pill.hot{background:var(--accent-soft);border-color:#F1CDB9;color:#8E2F10}
.pill.hot b{color:var(--accent)}
.empty{color:var(--muted);font-size:13px;margin:0}

/* 말풍선 */
.bubbles{display:flex;flex-direction:column;gap:10px;align-items:flex-end}
.bubble{max-width:min(620px,94%);background:var(--accent);color:#fff;padding:12px 15px;
  border-radius:16px 16px 4px 16px;font-size:14.5px;line-height:1.6}
.fakebadge{display:inline-block;background:#FBF0D9;color:#7E5A11;border:1px solid #EBD9B0;
  border-radius:999px;padding:3px 11px;font-size:11.5px;font-weight:700;margin-bottom:12px}
.warnbadge{display:inline-block;background:#FBF0D9;color:#7E5A11;border:1px solid #EBD9B0;
  border-radius:999px;padding:3px 10px;font-size:11.5px;font-weight:700}

/* 사례 타임라인 */
.case{position:relative;padding:0 0 18px 24px;border-left:2px solid var(--line2)}
.case:last-child{padding-bottom:0;border-left-color:transparent}
.case::before{content:"";position:absolute;left:-7px;top:5px;width:12px;height:12px;border-radius:50%;
  background:var(--accent);border:3px solid #fff;box-shadow:0 0 0 1px var(--line)}
.case h4{font-size:16px;font-weight:800;letter-spacing:-.02em}
.casemeta{font-size:11.5px;color:var(--muted);margin:2px 0 8px}
.casebody{font-size:13.5px;color:var(--ink2)}
.casebody b{color:var(--ink)}
.casestat{display:inline-block;background:var(--soft);border:1px solid var(--line);border-radius:8px;
  padding:3px 9px;font-size:12px;margin:8px 6px 0 0;font-variant-numeric:tabular-nums}

/* 인용 */
.quote{font-size:clamp(17px,2.5vw,22px);font-weight:700;line-height:1.5;letter-spacing:-.025em;
  border-left:5px solid var(--accent);padding:4px 0 4px 16px;margin:2px 0 14px}

/* fun 카드 */
.fun{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.funcard{background:linear-gradient(158deg,#FFF9F4,#FFFFFF 62%);border:1px solid var(--line);
  border-radius:16px;padding:18px}
.funk{font-size:11.5px;color:var(--muted);letter-spacing:.07em;font-weight:700}
.funval{font-size:30px;font-weight:800;letter-spacing:-.035em;margin:4px 0 8px;line-height:1.15}
.funbasis{font-size:12.5px;color:var(--ink2);margin-top:8px}
.st{display:inline-block;font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px}
.st-strong{background:#DDF0E5;color:#1E6B41}
.st-mid{background:#FBF0D9;color:#7E5A11}
.st-weak{background:#EFEBE4;color:#6B635A}
.st-none{background:#F7E6E2;color:#9E3E2E}

/* OMC 큰 숫자 */
.omcbig{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.omcpct{font-size:clamp(34px,6vw,46px);font-weight:800;letter-spacing:-.05em;line-height:1;
  color:var(--accent2);font-variant-numeric:tabular-nums}
.omcsub{font-size:12.5px;color:var(--ink2);line-height:1.5}
.omcraw{font-size:11.5px;color:var(--muted)}

/* 전문가 지수 */
.eibar{display:flex;flex-direction:column;gap:8px;margin-top:12px}
.eirow{display:grid;grid-template-columns:64px 1fr auto;gap:10px;align-items:center;font-size:12.5px}
.eiscore{font-size:44px;font-weight:800;letter-spacing:-.05em;line-height:1;font-variant-numeric:tabular-nums}
.rankrow{display:grid;grid-template-columns:auto minmax(76px,15%) 1fr auto;gap:10px;align-items:center;
  padding:10px 0;border-bottom:1px solid var(--line2)}
.rankrow:last-child{border-bottom:none}
.rankno{font-size:12px;font-weight:800;color:var(--muted);width:20px;text-align:right;
  font-variant-numeric:tabular-nums}
.rankname{font-weight:700;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rankname span{display:block;font-weight:400;font-size:11px;color:var(--muted)}
.rankbars{display:flex;height:14px;border-radius:4px;overflow:hidden;border:1px solid var(--line)}
.rankbars i{display:block;height:100%}
.rankscore{text-align:right;min-width:96px}
.rankscore b{font-size:19px;font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
@media(max-width:560px){.rankrow{grid-template-columns:auto 1fr auto}.rankbars{display:none}}

/* 도트 매트릭스 */
.dots{display:inline-flex;gap:3px}
.dots i{width:9px;height:9px;border-radius:50%;background:var(--line);display:block}
.dots i.on{background:var(--accent2)}

/* 히트맵 */
.heat{border-collapse:separate;border-spacing:2px;font-size:11.5px;min-width:700px}
.heat th{font-weight:700;color:var(--muted);font-size:10.5px;padding:3px 5px;text-align:center;
  white-space:nowrap}
.heat th.rowh{text-align:left;padding-right:10px;color:var(--ink2);font-size:12px}
.heat td{text-align:center;padding:6px 4px;border-radius:4px;font-variant-numeric:tabular-nums;min-width:32px}

/* 개인별 그래프 */
.pcard+.pcard{margin-top:14px}
.ptop{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.ptop h3{font-size:19px;font-weight:800;letter-spacing:-.03em}
.pcharts{display:grid;grid-template-columns:repeat(3,1fr);gap:16px 20px}
.pchart{min-width:0}
.pchart .cardtitle{margin-bottom:8px}

/* 멤버 카드 */
.members{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}
.mcard{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;
  display:flex;flex-direction:column;gap:9px}
.mcard .mtop{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.mcard h3{font-size:21px;font-weight:800;letter-spacing:-.03em}
.mpart{font-size:11.5px;color:var(--muted)}
.mline{font-size:13px;color:var(--ink2)}
.mkpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.mkpi{background:var(--soft);border-radius:9px;padding:8px 9px}
.mkpi b{display:block;font-size:16px;font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.mkpi span{font-size:10.5px;color:var(--muted)}
.mlinks{display:flex;gap:8px;margin-top:auto;padding-top:6px;flex-wrap:wrap}
.btn{display:inline-block;font-size:12.5px;font-weight:700;text-decoration:none;padding:7px 13px;
  border-radius:9px;border:1px solid var(--line)}
.btn-p{background:var(--ink);color:#FBF7F0;border-color:var(--ink)}
.btn-s{background:#fff;color:var(--ink2)}
.badge{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;
  background:var(--accent2-soft);color:var(--accent2)}
.lv-마스터{background:#FBE4D9;color:#A8380F}
.lv-전문가{background:#E1EEEF;color:#175B63}
.lv-숙련{background:#FBF0D9;color:#7E5A11}
.lv-견습{background:#EFEBE4;color:#6B635A}
.lv-입문{background:#E7F1E9;color:#3B6B4A}

/* 푸터 */
.foot{border-top:1px solid var(--line);margin-top:36px;padding-top:20px;font-size:12.5px;color:var(--muted)}
.foot .tbl{min-width:0;font-size:12.5px}
.notice{display:inline-block;background:#FAE7E3;color:#98311F;border:1px solid #EFCCC4;
  border-radius:8px;padding:6px 12px;font-weight:700;font-size:12px}
.buildnote{background:#FFFBF3;border:1px solid #EEDFC2;border-radius:12px;padding:14px 16px;font-size:13px}
.buildnote code{background:#F4EEE2;padding:1px 5px;border-radius:4px;font-size:12px}

@media(max-width:1100px){.kpis{grid-template-columns:repeat(4,1fr)}}
@media(max-width:900px){.kpis{grid-template-columns:repeat(3,1fr)}.fun{grid-template-columns:1fr}
  .pcharts{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.pcharts{grid-template-columns:1fr}}
@media(max-width:760px){.grid2,.grid3{grid-template-columns:1fr}}
@media(max-width:560px){.kpis{grid-template-columns:repeat(2,1fr)}
  .barrow{grid-template-columns:minmax(62px,34%) 1fr auto}}
"""


def html_doc(title: str, body: str) -> str:
    return ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="robots" content="noindex, nofollow">\n'
            f'<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n'
            f'{body}\n</body>\n</html>\n')


def sec(number: str, title: str, body: str, sub: str = "") -> str:
    subh = f'<span class="secsub">{esc(sub)}</span>' if sub else ""
    return (f'<section class="sec"><div class="seclabel"><span class="secnum">{esc(number)}</span>'
            f'<span class="sectitle">{esc(title)}</span>{subh}</div>{body}</section>')


def card(title: str, body: str) -> str:
    t = f'<div class="cardtitle">{esc(title)}</div>' if title else ""
    return f'<div class="card">{t}{body}</div>'


def kpi_tile(label: str, value: str, tag: str = "", unit: str = "") -> str:
    u = f'<span class="kpi-u">{esc(unit)}</span>' if unit else ""
    t = ""
    if tag:
        cls = "tag-long" if tag == "장기" else "tag-30d"
        t = f'<span class="tag {cls}">{esc(tag)}</span>'
    return (f'<div class="kpi"><div class="kpi-k">{esc(label)}</div>'
            f'<div class="kpi-v">{value}{u}</div>{t}</div>')


# ══════════════════════════════════════════════════════════════════════════════
# 차트 프리미티브 (인라인 SVG · CSS 막대)
# ══════════════════════════════════════════════════════════════════════════════
def bar_list(items, *, color=ACCENT, fmt=fmt_int, suffix="", max_value=None, empty="데이터 없음"):
    items = [(str(k), num(v)) for k, v in (items or [])]
    if not items:
        return f'<p class="empty">{esc(empty)}</p>'
    vmax = max_value if max_value else max((v for _, v in items), default=0)
    rows = []
    for k, v in items:
        w = (v / vmax * 100) if vmax else 0
        rows.append(
            f'<div class="barrow"><span class="barlabel" title="{esc(k)}">{esc(k)}</span>'
            f'<span class="bartrack"><span class="barfill" style="width:{w:.1f}%;background:{color}"></span></span>'
            f'<span class="barval">{esc(fmt(v))}{esc(suffix)}</span></div>')
    return f'<div class="barlist">{"".join(rows)}</div>'


def svg_vbars(pairs, *, color=ACCENT, bar_w=30, gap=14, height=158, fmt=fmt_int,
              label_fmt=short_month, show_values=True):
    pairs = [(str(k), num(v)) for k, v in (pairs or [])]
    if not pairs:
        return '<p class="empty">데이터 없음</p>'
    n = len(pairs)
    pad_t, pad_b, pad_x = (20 if show_values else 6), 24, 3
    plot = height - pad_t - pad_b
    W = pad_x * 2 + n * bar_w + (n - 1) * gap
    vmax = max((v for _, v in pairs), default=0) or 1
    out = [f'<svg viewBox="0 0 {W} {height}" style="width:100%;max-width:{W}px;height:auto" '
           f'role="img" aria-label="월별 막대 차트">',
           f'<line x1="0" y1="{height - pad_b + .5}" x2="{W}" y2="{height - pad_b + .5}" '
           f'stroke="{LINE}" stroke-width="1"/>']
    for i, (label, v) in enumerate(pairs):
        h = max(1.5, plot * (v / vmax))
        x = pad_x + i * (bar_w + gap)
        y = pad_t + (plot - h)
        out.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="3" fill="{color}">'
                   f'<title>{esc(label)} · {esc(fmt(v))}</title></rect>')
        if show_values:
            out.append(f'<text x="{x + bar_w / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
                       f'font-size="10.5" fill="{MUTED}">{esc(fmt(v))}</text>')
        out.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - 8}" text-anchor="middle" '
                   f'font-size="10" fill="{MUTED}">{esc(label_fmt(label))}</text>')
    out.append('</svg>')
    return "".join(out)


def svg_line(pairs, *, color=ACCENT2, height=158, step=54, fmt=fmt_int):
    pairs = [(str(k), num(v)) for k, v in (pairs or [])]
    if not pairs:
        return '<p class="empty">데이터 없음</p>'
    if len(pairs) == 1:
        return svg_vbars(pairs, color=color, height=height, fmt=fmt)
    n = len(pairs)
    pad_t, pad_b, pad_x = 20, 24, 20
    plot = height - pad_t - pad_b
    W = pad_x * 2 + (n - 1) * step
    vmax = max((v for _, v in pairs), default=0) or 1
    pts = []
    for i, (_, v) in enumerate(pairs):
        x = pad_x + i * step
        y = pad_t + plot - plot * (v / vmax)
        pts.append((x, y))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"M{pts[0][0]:.1f},{height - pad_b} " +
            " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts) +
            f" L{pts[-1][0]:.1f},{height - pad_b} Z")
    out = [f'<svg viewBox="0 0 {W} {height}" style="width:100%;max-width:{W}px;height:auto" '
           f'role="img" aria-label="월별 추이 선 차트">',
           f'<line x1="0" y1="{height - pad_b + .5}" x2="{W}" y2="{height - pad_b + .5}" '
           f'stroke="{LINE}" stroke-width="1"/>',
           f'<path d="{area}" fill="{color}" fill-opacity="0.10"/>',
           f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.2" '
           f'stroke-linejoin="round" stroke-linecap="round"/>']
    for (x, y), (label, v) in zip(pts, pairs):
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="#fff" stroke="{color}" stroke-width="2">'
                   f'<title>{esc(label)} · {esc(fmt(v))}</title></circle>')
        out.append(f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-size="10" '
                   f'fill="{MUTED}">{esc(fmt(v))}</text>')
        out.append(f'<text x="{x:.1f}" y="{height - 8}" text-anchor="middle" font-size="10" '
                   f'fill="{MUTED}">{esc(short_month(label))}</text>')
    out.append('</svg>')
    return "".join(out)


def hour_strip(by_hour, *, base=(216, 72, 31)):
    vals = [num(x) for x in (by_hour or [])][:24]
    vals += [0] * (24 - len(vals))
    vmax = max(vals) if vals else 0
    cells, labs = [], []
    for h, v in enumerate(vals):
        t = heat_t(v, vmax)
        cells.append(f'<div style="background:{heat_rgb(t, base)}" title="{h}시 · {esc(fmt_int(v))}건"></div>')
        labs.append(f'<span>{h if h % 3 == 0 else ""}</span>')
    return (f'<div class="hours">{"".join(cells)}</div>'
            f'<div class="hourlab">{"".join(labs)}</div>')


def stack_bar(segments, *, min_label=0.08):
    """segments: [(라벨, 비중0~1, 색)] → 스택 바 + 범례."""
    segs = [(str(k), max(0.0, num(v)), c) for k, v, c in segments]
    total = sum(v for _, v, _ in segs)
    if total <= 0:
        return '<p class="empty">데이터 없음</p>'
    bars, legend = [], []
    for k, v, c in segs:
        r = v / total
        inner = f"{r * 100:.0f}%" if r >= min_label else ""
        bars.append(f'<span style="width:{r * 100:.2f}%;background:{c}" '
                    f'title="{esc(k)} · {r * 100:.1f}%">{esc(inner)}</span>')
        legend.append(f'<span><i style="background:{c}"></i>{esc(k)} {r * 100:.1f}%</span>')
    return f'<div class="stack">{"".join(bars)}</div><div class="legend">{"".join(legend)}</div>'


def share_stack(pairs, *, limit=6):
    items = pair_list(pairs, limit)
    if not items:
        return '<p class="empty">데이터 없음</p>'
    return stack_bar([(k, v, SERIES[i % len(SERIES)]) for i, (k, v) in enumerate(items)])


def svg_radar(axes: dict, *, size=300, color=ACCENT):
    vals = [max(0.0, min(5.0, num(axes.get(k)))) for k in AXIS_ORDER]
    n = len(AXIS_ORDER)
    cx = cy = size / 2
    R = size / 2 - 46
    out = [f'<svg viewBox="0 0 {size} {size}" style="width:100%;max-width:{size}px;height:auto" '
           f'role="img" aria-label="성향 5축 레이더 차트">']

    def pt(i, r):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * math.cos(a), cy + r * math.sin(a)

    for ring in range(1, 6):
        rr = R * ring / 5
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, rr) for i in range(n)))
        out.append(f'<polygon points="{pts}" fill="none" stroke="{LINE if ring < 5 else MUTED}" '
                   f'stroke-width="{1 if ring < 5 else 1.2}"/>')
    for i in range(n):
        x, y = pt(i, R)
        out.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, R * v / 5) for i, v in enumerate(vals)))
    out.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.20" stroke="{color}" stroke-width="2.2"/>')
    for i, v in enumerate(vals):
        x, y = pt(i, R * v / 5)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{color}"/>')
    for i, k in enumerate(AXIS_ORDER):
        x, y = pt(i, R + 20)
        a = -math.pi / 2 + 2 * math.pi * i / n
        ca = math.cos(a)
        anchor = "middle" if abs(ca) < 0.3 else ("start" if ca > 0 else "end")
        dy = 4 if abs(math.sin(a)) < 0.3 else (12 if math.sin(a) > 0 else -3)
        out.append(f'<text x="{x:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}" font-size="12" '
                   f'font-weight="700" fill="{INK}">{esc(AXIS_KO[k])}</text>')
        out.append(f'<text x="{x:.1f}" y="{y + dy + 13:.1f}" text-anchor="{anchor}" font-size="11" '
                   f'fill="{MUTED}">{esc(str(int(num(axes.get(k)))))}</text>')
    out.append('</svg>')
    return "".join(out)


def dots(value, total=5, color=ACCENT2):
    v = int(num(value))
    cells = []
    for i in range(total):
        if i < v:
            cells.append(f'<i class="on" style="background:{color}"></i>')
        else:
            cells.append('<i></i>')
    return f'<span class="dots" title="{v}/{total}">{"".join(cells)}</span>'


# ══════════════════════════════════════════════════════════════════════════════
# 개인 페이지
# ══════════════════════════════════════════════════════════════════════════════
def level_badge(ei) -> str:
    """전문가 지수 레벨 배지 — 등급마다 색이 다르다."""
    score = int(num(g(ei, "score")))
    level = str(g(ei, "level", "")) or ei_level_of(score)[0]
    emoji = str(g(ei, "emoji", "")) or ei_level_of(score)[1]
    return f'<span class="badge lv-{esc(level)}">{esc(emoji)} {esc(level)}</span>'


def strength_class(s: str) -> str:
    t = str(s or "").strip()
    if t.startswith("강"):
        return "st-strong"
    if t.startswith("보통") or t.startswith("중"):
        return "st-mid"
    if "없음" in t or "무작위" in t:
        return "st-none"
    return "st-weak"


def ul(items, empty="적어 두지 않았습니다"):
    items = str_list(items)
    if not items:
        return f'<p class="empty">{esc(empty)}</p>'
    return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"


def fun_is_empty(fun) -> bool:
    if not isinstance(fun, dict):
        return True
    vals = [str(g(fun, f"{k}.value", "")).strip() for k in ("mbti", "age_band", "blood_type")]
    return not (any(vals) or str(fun.get("nickname") or "").strip()
                or str(fun.get("pair_programming") or "").strip())


def expert_index_card(ei: dict) -> str:
    score = int(num(g(ei, "score")))
    level = str(g(ei, "level", "")) or ei_level_of(score)[0]
    emoji = str(g(ei, "emoji", "")) or ei_level_of(score)[1]
    bd = g(ei, "breakdown", {}) or {}
    rows = []
    for k in EI_AXES:
        v = num(bd.get(k))
        rows.append(
            f'<div class="eirow"><span>{esc(EI_AXIS_KO[k])}</span>'
            f'<span class="bartrack"><span class="barfill" '
            f'style="width:{min(100.0, v / 20 * 100):.1f}%;background:{ACCENT2}"></span></span>'
            f'<span class="barval" title="{esc(EI_AXIS_FULL[k])}">{v:.1f}/20</span></div>')
    inputs = g(ei, "inputs", {}) or {}
    inp = " · ".join(filter(None, [
        f"장기 세션 {fmt_int(inputs.get('sessions_long'))}" if "sessions_long" in inputs else "",
        f"자동화 심도 {fmt_dec(inputs.get('automation_depth'))}배" if "automation_depth" in inputs else "",
        f"서브에이전트 비중 {fmt_pct(inputs.get('subagent_msg_ratio'))}" if "subagent_msg_ratio" in inputs else "",
        f"자산 {fmt_int(inputs.get('asset_points'))}점" if "asset_points" in inputs else "",
        f"OMC 비중 {fmt_pct(inputs.get('omc_ratio'))}" if "omc_ratio" in inputs else "",
        f"OMC {fmt_int(inputs.get('distinct_commands'))}종" if "distinct_commands" in inputs else "",
    ]))
    return card("",
                '<span class="fakebadge">재미용 · 산식 공개 (docs/SUMMARY_SCHEMA.md)</span>'
                f'<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-top:12px">'
                f'<div class="eiscore">{score}<span style="font-size:.4em;color:{MUTED}">/100</span></div>'
                f'<div><div style="font-size:19px;font-weight:800">{esc(emoji)} {esc(level)}</div>'
                f'<div style="font-size:12px;color:{MUTED}">산식 v{esc(g(ei, "formula_version", 1))} · '
                f'5축 × 20점. 버전이 다르면 비교하지 않습니다</div></div></div>'
                f'<div class="eibar">{"".join(rows)}</div>'
                f'<div class="note">입력값 — {esc(inp) if inp else "기록 없음"}</div>')


def turn_duration_card(td) -> str:
    """workflow.turn_duration → 큰 숫자(중앙값) + 분위 칩 + 구간 분포 막대."""
    if not isinstance(td, dict) or not td:
        return '<p class="empty">데이터 없음 — 집계 스크립트를 다시 돌려 스캐폴드하면 채워집니다</p>'
    head = (f'<div class="omcbig"><span class="omcpct">{esc(fmt_dur(td.get("median_sec")))}</span>'
            f'<span class="omcsub">지시 1건이 돌아간 시간 · 중앙값<br>'
            f'<span class="omcraw">측정 {esc(fmt_int(td.get("n")))}건 · '
            f'합계 {esc(fmt_dur(td.get("total_sec")))}</span></span></div>'
            f'<div class="pills" style="margin-top:10px">'
            f'<span class="pill">p25<b>{esc(fmt_dur(td.get("p25_sec")))}</b></span>'
            f'<span class="pill">p75<b>{esc(fmt_dur(td.get("p75_sec")))}</b></span>'
            f'<span class="pill">p90<b>{esc(fmt_dur(td.get("p90_sec")))}</b></span>'
            f'<span class="pill">최장<b>{esc(fmt_dur(td.get("max_sec")))}</b></span>'
            f'<span class="pill">평균<b>{esc(fmt_dur(td.get("mean_sec")))}</b></span></div>')
    body = ('<div style="margin-top:14px">'
            + bar_list(pair_list(td.get("buckets")), color=ACCENT, suffix="건") + '</div>'
            '<div class="note">사람이 프롬프트를 친 시각부터, 다음 프롬프트 전 <b>마지막 메인 어시스턴트 메시지</b>까지 '
            '걸린 시간입니다. 자율 모드(ulw · ralph · team)가 이어서 돈 시간은 포함되고, '
            '결과를 검토하며 기다린 시간은 빠집니다.</div>')
    return head + body


def render_person(data: dict) -> str:
    name = str(data.get("name") or "")
    part = str(data.get("part") or "")
    date = str(data.get("date") or "")
    fun = data.get("fun")
    nick = str(g(fun, "nickname", "") if isinstance(fun, dict) else "").strip()
    ei = data.get("expert_index") or {}

    # ── 히어로 ──
    chips = []
    for k, ko in (("habit", "습관"), ("effect", "효과"), ("pain", "불편")):
        v = str(g(data, f"summary.{k}", "")).strip()
        if v:
            chips.append(f'<span class="chip"><b>{esc(ko)}</b>{esc(v)}</span>')
    nick_html = f'<span class="nick">{esc(nick)}</span>' if nick else ""
    role = str(data.get("role") or "").strip()
    highlight = str(data.get("highlight") or "").strip()
    rolebits = []
    if role:
        rolebits.append(f"주 담당 · {role}")
    if highlight and highlight != "없음":
        rolebits.append(f"강조 · {highlight}")
    score = int(num(g(ei, "score")))
    hero_score = ""
    if ei:
        hero_score = (f'<div class="hero-score"><span class="sc">{score}</span>'
                      f'<span><span class="lv">{esc(g(ei, "emoji", ""))} '
                      f'{esc(g(ei, "level", ""))}</span><br>'
                      f'<span class="fy">AI 사용 전문가 지수 · 재미용</span></span></div>')
    hero = (f'<header class="hero"><div class="in">'
            f'<div class="hero-meta">{esc(part)} · {esc(date)} 작성</div>'
            f'<h1 class="hero-name">{esc(name)}{nick_html}</h1>'
            f'<p class="hero-line">{esc(g(data, "summary.one_liner", ""))}</p>'
            f'<div class="chips">{"".join(chips)}</div>'
            + (f'<div class="hero-role">{esc(" · ".join(rolebits))}</div>' if rolebits else "")
            + hero_score + '</div></header>')

    # ── KPI ──
    kpis = "".join([
        kpi_tile("세션 수", esc(fmt_int(g(data, "scale.sessions_long"))), "장기"),
        kpi_tile("도구 호출", esc(fmt_int(g(data, "scale.tool_calls_long"))), "장기"),
        kpi_tile("직접 프롬프트", esc(fmt_int(g(data, "scale.natural_prompts"))), "장기"),
        kpi_tile("자동화 심도", esc(fmt_dec(g(data, "workflow.automation_depth"))), "최근 30일", unit="배"),
        kpi_tile("한 지시당 실행 시간 (중앙값)",
                 esc(fmt_dur(g(data, "workflow.turn_duration.median_sec")))
                 if isinstance(g(data, "workflow.turn_duration"), dict) else "-", "최근 30일"),
        kpi_tile("활동 개월", esc(fmt_int(g(data, "scale.active_months"))), "장기", unit="개월"),
        kpi_tile("출력 토큰", tok_html(g(data, "scale.tok_out_30d")), "최근 30일"),
    ])
    kpis = (f'<div class="kpis">{kpis}</div>'
            f'<p class="empty" style="margin-bottom:30px">구간이 서로 다릅니다 — <b>장기</b>는 수개월, '
            f'<b>최근 30일</b>은 트랜스크립트 보존 기간입니다. 두 구간의 값을 섞어 비교하지 마세요.</p>')

    # ── 01 사용 규모와 리듬 ──
    dow_pairs = [(DOW_KO.get(k, k), v) for k, v in pair_list(g(data, "scale.by_dow"))]
    s1 = (f'<div class="grid2">'
          + card("월별 세션 (장기)", svg_vbars(pair_list(g(data, "scale.sessions_by_month")), color=ACCENT))
          + card("월별 직접 프롬프트 (장기)", svg_line(pair_list(g(data, "scale.prompts_by_month")), color=ACCENT2))
          + '</div><div class="grid2" style="margin-top:14px">'
          + card("시간대 분포 (0~23시)", hour_strip(g(data, "scale.by_hour")))
          + card("요일 분포", bar_list(dow_pairs, color=ACCENT2, suffix="건"))
          + '</div>')
    rn = str(g(data, "scale.rhythm_note", "")).strip()
    if rn:
        s1 += card("", f'<p style="margin:0">{esc(rn)}</p>')
    extra = "".join([
        f'<span class="pill">슬래시 커맨드<b>{esc(fmt_int(g(data, "scale.slash_prompts")))}</b></span>',
        f'<span class="pill">서브에이전트 메시지 (30일)<b>{esc(fmt_int(g(data, "scale.subagent_msgs_30d")))}</b></span>',
        f'<span class="pill">사고 토큰 (30일)<b>{fmt_tok(g(data, "scale.thinking_tok_30d"))}</b></span>',
        f'<span class="pill">캐시 읽기 (30일)<b>{fmt_tok(g(data, "scale.tok_cache_read_30d"))}</b></span>',
    ])
    s1 += card("", f'<div class="pills">{extra}</div>')

    # ── 02 프로젝트 ──
    rows = g(data, "projects_top", []) or []
    if rows:
        vmax = max((num(r.get("human_turns")) for r in rows), default=0) or 1
        trs = []
        for r in rows:
            ht = num(r.get("human_turns"))
            trs.append(
                f'<tr><td><div class="pname">{esc(r.get("project"))}</div>'
                f'<div class="minibar"><span style="width:{ht / vmax * 100:.1f}%"></span></div></td>'
                f'<td class="r">{esc(fmt_int(r.get("sessions")))}</td>'
                f'<td class="r">{esc(fmt_int(r.get("active_days")))}</td>'
                f'<td class="r">{esc(fmt_int(ht))}</td>'
                f'<td class="r" title="상위 도구 합계 근사">{esc(fmt_int(r.get("tool_calls")))}</td>'
                f'<td>{esc(r.get("main_model") or "-")}</td>'
                f'<td style="white-space:nowrap;color:{MUTED};font-size:12px">{esc(r.get("period") or "-")}</td></tr>')
        tbl = ('<div class="scrollx"><table class="tbl"><thead><tr><th>프로젝트</th>'
               '<th class="r">세션</th><th class="r">활동일</th><th class="r">직접 프롬프트</th>'
               '<th class="r">도구 호출</th><th>주 모델</th><th>기간</th></tr></thead><tbody>'
               + "".join(trs) + '</tbody></table></div>')
    else:
        tbl = '<p class="empty">프로젝트 기록이 없습니다</p>'
    other = int(num(data.get("projects_other_count")))
    s2 = card("", tbl + (f'<div class="note">그 외 {other}개 프로젝트. '
                         f'도구 호출은 프로젝트별 <b>상위 도구 합계 근사</b>입니다.</div>' if other else
                         '<div class="note">도구 호출은 프로젝트별 <b>상위 도구 합계 근사</b>입니다.</div>'))

    # ── 03 워크플로 ──
    omc = g(data, "workflow.omc", {}) or {}
    omc_cmds = pair_list(omc.get("commands"))          # 전부
    omc_kw = pair_list(omc.get("keyword_forms"))
    omc_month = pair_list(omc.get("by_month"))
    omc_head = (
        f'<div class="omcbig"><span class="omcpct">{esc(fmt_pct(omc.get("omc_ratio"), 1))}</span>'
        f'<span class="omcsub">OMC 명령어 사용 비중<br>'
        f'<span class="omcraw">직접 프롬프트 {esc(fmt_int(omc.get("prompts_with_omc")))}'
        f'/{esc(fmt_int(omc.get("prompts_total")))}건 · '
        f'{esc(fmt_int(omc.get("distinct_commands")))}종 사용</span></span></div>'
        f'<div class="pills" style="margin-top:10px">'
        f'<span class="pill">슬래시 커맨드 중<b>{esc(fmt_pct(omc.get("slash_omc_ratio"), 1))}</b></span>'
        f'<span class="pill">자연어 키워드<b>{esc(fmt_pct(omc.get("keyword_ratio"), 1))}</b></span>'
        f'</div>')
    omc_body = ('<div style="margin-top:14px">'
                + bar_list(omc_cmds, color=ACCENT2, empty="OMC 명령 기록 없음") + '</div>')
    if omc_kw:
        omc_body += ('<div class="note"><b>자연어 매직 키워드</b><div class="pills" style="margin-top:8px">'
                     + "".join(f'<span class="pill hot">{esc(k)}<b>{esc(fmt_int(v))}</b></span>'
                               for k, v in omc_kw) + '</div></div>')
    if omc_month:
        omc_body += ('<div class="note"><b>도입 추이</b> (월별 OMC 명령 프롬프트 수)'
                     f'<div style="margin-top:8px">'
                     + svg_vbars(omc_month, color=ACCENT2, bar_w=18, gap=9, height=86,
                                 show_values=False, label_fmt=tiny_month) + '</div></div>')
    s3 = (f'<div class="grid2">'
          + card("한 지시당 실행 시간 (최근 30일)", turn_duration_card(g(data, "workflow.turn_duration")))
          + card("OMC 명령어 (장기)", omc_head + omc_body)
          + '</div><div class="grid3" style="margin-top:14px">'
          + card("모델 비중", share_stack(g(data, "workflow.models")))
          + card("effort 비중", share_stack(g(data, "workflow.effort")))
          + card("permission mode 비중", share_stack(g(data, "workflow.permission_mode")))
          + '</div>')
    def chips_of(pairs, cls="pill"):
        items = pair_list(pairs, 12)
        if not items:
            return '<p class="empty">기록 없음</p>'
        return ('<div class="pills">' + "".join(
            f'<span class="{cls}">{esc(k)}<b>{esc(fmt_int(v))}</b></span>' for k, v in items) + '</div>')
    s3 += ('<div class="grid3" style="margin-top:14px">'
           + card(f'서브에이전트 (메시지 비중 {esc(fmt_pct(g(data, "workflow.subagent_msg_ratio"), 1))})',
                  chips_of(g(data, "workflow.subagent_types")))
           + card("MCP 서버 (실제 호출)", chips_of(g(data, "workflow.mcp_servers")))
           + card("스킬", chips_of(g(data, "workflow.skills")))
           + '</div>')
    sn = str(g(data, "workflow.style_note", "")).strip()
    if sn:
        s3 += card("", f'<p style="margin:0">{esc(sn)}</p>')

    # ── 04 말투 ──
    pol = g(data, "speech.politeness", {}) or {}
    sample_n = int(num(g(data, "coverage.speech_sample_size")))
    warn = (f'<span class="warnbadge">표본 {sample_n}건 · 해석 주의 (100건 미만)</span>'
            if sample_n < 100 else "")
    markers = g(data, "speech.markers_per_100", {}) or {}
    mk_pairs = sorted(((m, num(markers.get(m))) for m in MARKERS), key=lambda x: -x[1])
    s4 = (f'<div class="grid2">'
          + card("존댓말 · 반말 · 체언종결",
                 stack_bar([("존댓말", num(pol.get("formal")), SERIES[1]),
                            ("반말", num(pol.get("casual")), SERIES[0]),
                            ("체언종결", num(pol.get("noun")), SERIES[2])]))
          + card("화법 마커 10종 (프롬프트 100건당)",
                 bar_list(mk_pairs, color=ACCENT, fmt=lambda v: fmt_dec(v, 1)))
          + '</div>')
    def kv_chips(pairs, limit, hot=False):
        items = pair_list(pairs, limit)
        if not items:
            return '<p class="empty">기록 없음</p>'
        cls = "pill hot" if hot else "pill"
        return ('<div class="pills">' + "".join(
            f'<span class="{cls}">{esc(k)}<b>{esc(fmt_int(v))}</b></span>' for k, v in items) + '</div>')
    s4 += ('<div class="grid3" style="margin-top:14px">'
           + card("종결 표현 Top 5", kv_chips(g(data, "speech.endings_top"), 5, hot=True))
           + card("첫 단어 Top 5", kv_chips(g(data, "speech.first_words_top"), 5))
           + card("어휘 Top 10", kv_chips(g(data, "speech.vocab_top"), 10))
           + '</div>')
    gap = g(data, "speech.gap_sec", {}) or {}
    lench = g(data, "speech.len_chars", {}) or {}
    punct = g(data, "speech.punctuation", {}) or {}
    rhythm_pills = "".join([
        f'<span class="pill">프롬프트 간격 중앙값<b>{esc(fmt_int(gap.get("median")))}초</b></span>',
        f'<span class="pill">p25<b>{esc(fmt_int(gap.get("p25")))}초</b></span>',
        f'<span class="pill">p90<b>{esc(fmt_int(gap.get("p90")))}초</b></span>',
        f'<span class="pill">짧은 후속 지시<b>{esc(fmt_pct(g(data, "speech.short_followup_ratio"), 1))}</b></span>',
        f'<span class="pill">길이 중앙값<b>{esc(fmt_int(lench.get("median")))}자</b></span>',
        f'<span class="pill">p90<b>{esc(fmt_int(lench.get("p90")))}자</b></span>',
        f'<span class="pill">최장<b>{esc(fmt_int(lench.get("max")))}자</b></span>',
        f'<span class="pill">문장/프롬프트<b>{esc(fmt_dec(g(data, "speech.sentences_per_prompt"), 2))}</b></span>',
        f'<span class="pill">물음표<b>{esc(fmt_int(punct.get("question")))}</b></span>',
        f'<span class="pill">문장부호 없이 끝냄<b>{esc(fmt_pct(punct.get("none_ratio"), 0))}</b></span>',
        f'<span class="pill">ㅋㅋ/ㅠㅠ<b>{esc(fmt_int(g(data, "speech.laugh_prompts")))}건</b></span>',
        f'<span class="pill">이모지<b>{esc(fmt_int(g(data, "speech.emoji_prompts")))}건</b></span>',
        f'<span class="pill">영어 섞임<b>{esc(fmt_pct(g(data, "speech.english_mixed_ratio"), 0))}</b></span>',
    ])
    s4 += card("대화 리듬과 프롬프트 모양", f'<div class="pills">{rhythm_pills}</div>'
               + (f'<div class="note">{warn}</div>' if warn else ""))
    ss = str_list(g(data, "speech.style_summary"))
    if ss:
        s4 += card("말투 3줄 요약", ul(ss))
    rp = str_list(g(data, "speech.reproduced_prompts"))
    if rp:
        bub = "".join(f'<div class="bubble">{esc(x)}</div>' for x in rp)
        s4 += card("이 사람이라면 이렇게 쓸 것 같다",
                   '<span class="fakebadge">가상 프롬프트 · 실제 발화 아님</span>'
                   f'<div class="bubbles">{bub}</div>')

    # ── 05 자산 ──
    counts = g(data, "assets.counts", {}) or {}
    tiles = []
    for key, ko in ASSET_LABELS:
        if key not in counts:
            continue
        v = counts[key]
        disp = ("있음" if v else "없음") if isinstance(v, bool) else fmt_int(v)
        tiles.append(f'<div class="mkpi"><b>{esc(disp)}</b><span>{esc(ko)}</span></div>')
    sw = g(data, "assets.share_worthy", []) or []
    sw_html = ("<ul>" + "".join(
        f'<li><b>{esc(x.get("asset"))}</b> — {esc(x.get("reason"))}</li>'
        for x in sw if isinstance(x, dict)) + "</ul>") if sw else '<p class="empty">고른 것이 없습니다</p>'
    s5 = ('<div class="grid2">'
          + card("커스터마이징 자산",
                 f'<div class="mkpis" style="grid-template-columns:repeat(auto-fill,minmax(96px,1fr))">'
                 f'{"".join(tiles) or ""}</div>' if tiles else '<p class="empty">기록 없음</p>')
          + card("파트에 공유할 만한 것", sw_html)
          + '</div>')

    # ── 06 대표 사례 ──
    cases = [c for c in (g(data, "cases", []) or []) if isinstance(c, dict)]
    if cases:
        items = []
        for c in cases:
            meta = " · ".join(filter(None, [str(c.get("project") or ""), str(c.get("when") or "")]))
            stats_ = []
            if c.get("human_turns") is not None:
                stats_.append(f'<span class="casestat">직접 프롬프트 {esc(fmt_int(c.get("human_turns")))}</span>')
            if c.get("tool_calls") is not None:
                stats_.append(f'<span class="casestat">도구 호출 {esc(fmt_int(c.get("tool_calls")))}</span>')
            if str(c.get("saving") or "").strip():
                stats_.append(f'<span class="casestat">{esc(c.get("saving"))}</span>')
            body = []
            if str(c.get("task") or "").strip():
                body.append(f'<p><b>시킨 일</b> — {esc(c.get("task"))}</p>')
            if str(c.get("how") or "").strip():
                body.append(f'<p><b>어떻게</b> — {esc(c.get("how"))}</p>')
            if str(c.get("outcome") or "").strip():
                body.append(f'<p><b>결과</b> — {esc(c.get("outcome"))}</p>')
            items.append(f'<div class="case"><h4>{esc(c.get("title"))}</h4>'
                         f'<div class="casemeta">{esc(meta)}</div>'
                         f'<div class="casebody">{"".join(body)}</div>{"".join(stats_)}</div>')
        s6 = card("", "".join(items))
    else:
        s6 = card("", '<p class="empty">대표 사례가 없습니다</p>')

    # ── 07 성향 프로파일 ──
    axes = g(data, "profile.axes", {}) or {}
    ev = g(data, "profile.axes_evidence", {}) or {}
    ev_rows = "".join(
        f'<tr><td style="white-space:nowrap"><b>{esc(AXIS_KO[k])}</b> '
        f'<span style="color:{MUTED};font-size:11.5px">{esc(AXIS_POLE[k])}</span></td>'
        f'<td class="r">{dots(axes.get(k))}</td>'
        f'<td style="color:{ACCENT2}">{esc(ev.get(k, "")) or "-"}</td></tr>' for k in AXIS_ORDER)
    s7 = ('<div class="grid2">'
          + card("5축 프로파일", f'<div style="text-align:center">{svg_radar(axes)}</div>')
          + card("축별 근거", f'<div class="scrollx"><table class="tbl" style="min-width:0">'
                            f'<tbody>{ev_rows}</tbody></table></div>')
          + '</div>')
    s7 += card("", f'<div class="quote">{esc(g(data, "profile.definition", ""))}</div>'
               + "".join(f'<p style="margin:0 0 6px"><b>{ko}</b> — {esc(g(data, f"profile.{k}", ""))}</p>'
                         for k, ko in (("rhythm", "작업 리듬"), ("interest", "관심 영역"))
                         if str(g(data, f"profile.{k}", "")).strip())
               + '<div class="note"><b>동료가 알아두면 좋은 것</b>'
               + ul(g(data, "profile.teammate_tips")) + '</div>')

    # ── 08 전문가 지수 ──
    s8 = expert_index_card(ei) if ei else card("", '<p class="empty">지수가 계산되지 않았습니다</p>')

    # ── 09 재미 코너 ──
    s9 = ""
    if isinstance(fun, dict) and not fun_is_empty(fun):
        fcards = []
        for k, ko in (("mbti", "MBTI"), ("age_band", "나이대"), ("blood_type", "혈액형")):
            blk = fun.get(k) or {}
            st = str(blk.get("strength") or "")
            fcards.append(
                f'<div class="funcard"><div class="funk">{esc(ko)}</div>'
                f'<div class="funval">{esc(blk.get("value") or "-")}</div>'
                f'<span class="st {strength_class(st)}">근거 강도 · {esc(st or "미기재")}</span>'
                f'<div class="funbasis">{esc(blk.get("basis") or "")}</div></div>')
        s9 = (f'<div class="fun">{"".join(fcards)}</div>'
              + card("", '<span class="fakebadge">재미용 · 근거 강도를 함께 보세요</span>'
                         + (f'<p style="margin:10px 0 0"><b>페어 프로그래밍 한다면</b> — '
                            f'{esc(fun.get("pair_programming"))}</p>'
                            if str(fun.get("pair_programming") or "").strip() else "")))

    # ── 10 효과·한계·제안 ──
    s10 = ('<div class="grid2">'
           + card("효과가 확실한 작업 유형", ul(g(data, "feedback.works_well")))
           + card("잘 안 되는 작업 유형", ul(g(data, "feedback.works_poorly")))
           + card("막혔던 지점 · 반복 실패 패턴", ul(g(data, "feedback.blockers")))
           + card("파트 차원 제안", ul(g(data, "feedback.proposals")))
           + '</div>')

    # ── 푸터 ──
    cov = g(data, "coverage", {}) or {}
    cov_rows = []
    for key, ko, src in (("history", "프롬프트 이력", "~/.claude/history.jsonl"),
                         ("session_stats", "세션 통계", "~/.claude/.session-stats.json"),
                         ("transcripts", "트랜스크립트", "~/.claude/projects/**.jsonl (약 30일)")):
        blk = cov.get(key)
        rng = (f'{esc(g(blk, "from", "?"))} ~ {esc(g(blk, "to", "?"))}'
               if isinstance(blk, dict) else '<span style="color:#B23A2E">구하지 못함</span>')
        cov_rows.append(f'<tr><td>{esc(ko)}</td><td>{rng}</td>'
                        f'<td style="font-size:11.5px">{esc(src)}</td></tr>')
    failed = str_list(cov.get("failed_items"))
    env = g(data, "env", {}) or {}
    envtxt = " · ".join(filter(None, [
        f'Claude Code {env.get("claude_code")}' if env.get("claude_code") else "",
        str(env.get("os") or ""), f'Python {env.get("python")}' if env.get("python") else ""]))
    foot = (f'<footer class="foot"><div class="scrollx"><table class="tbl" style="min-width:0">'
            f'<thead><tr><th>집계 구간</th><th>기간</th><th>원본</th></tr></thead>'
            f'<tbody>{"".join(cov_rows)}</tbody></table></div>'
            f'<p style="margin-top:12px">말투 표본 {esc(fmt_int(cov.get("speech_sample_size")))}건'
            + (f' · 수집 실패 — {esc(", ".join(failed))}' if failed else " · 수집 실패 없음")
            + (f' · {esc(envtxt)}' if envtxt else "")
            + (f' · 집계 스크립트 <code>{esc(data.get("script_commit"))}</code>'
               if str(data.get("script_commit") or "").strip() else "")
            + '</p>'
            + '<p class="notice">사외 공유 금지 — 파트 내부 회람용입니다</p></footer>')

    body = (hero + '<div class="wrap">' + kpis
            + sec("01", "사용 규모와 리듬", s1, "장기 = 수개월 · 30일 = 트랜스크립트")
            + sec("02", "프로젝트별 사용", s2, "직접 프롬프트 많은 순")
            + sec("03", "워크플로", s3, "도구 · OMC · 모델")
            + sec("04", "말투", s4, f"표본 {fmt_int(g(data, 'coverage.speech_sample_size'))}건")
            + sec("05", "커스터마이징 자산", s5)
            + sec("06", "대표 사례", s6)
            + sec("07", "성향 프로파일", s7, "1~5 · 방향은 축 이름 옆 참고")
            + sec("08", "AI 사용 전문가 지수", s8, "재미용")
            + (sec("09", "재미 코너", s9, "재미용 · 근거 강도 참고") if s9 else "")
            + sec("10" if s9 else "09", "효과 · 한계 · 제안", s10)
            + foot + '</div>')
    return html_doc(f"{name} · {part} · Claude Code 활용 실태", body)


# ══════════════════════════════════════════════════════════════════════════════
# 통합 대시보드
# ══════════════════════════════════════════════════════════════════════════════
def heat_table(row_labels, col_labels, matrix, *, fmt=fmt_int, base=(216, 72, 31), per_row=False):
    if not row_labels or not col_labels:
        return '<p class="empty">데이터 없음</p>'
    gmax = max((num(v) for row in matrix for v in row), default=0)
    head = "".join(f"<th>{esc(c)}</th>" for c in col_labels)
    trs = []
    for label, row in zip(row_labels, matrix):
        vmax = max((num(v) for v in row), default=0) if per_row else gmax
        tds = []
        for c, v in zip(col_labels, row):
            t = heat_t(v, vmax)
            tds.append(f'<td style="background:{heat_rgb(t, base)};color:{heat_fg(t)}" '
                       f'title="{esc(label)} · {esc(c)} · {esc(fmt(v))}">{esc(fmt(v))}</td>')
        trs.append(f'<tr><th class="rowh">{esc(label)}</th>{"".join(tds)}</tr>')
    return (f'<div class="scrollx"><table class="heat"><thead><tr><th class="rowh"></th>{head}</tr>'
            f'</thead><tbody>{"".join(trs)}</tbody></table></div>')


def compare_card(title, members, getter, *, fmt=fmt_int, suffix="", color=ACCENT, reverse=True):
    items = [(str(m["data"].get("name") or ""), num(getter(m["data"]))) for m in members]
    items.sort(key=lambda x: -x[1] if reverse else x[1])
    return card(title, bar_list(items, color=color, fmt=fmt, suffix=suffix))


def render_index(members, history, notes) -> str:
    built = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    if not members:
        body = ('<header class="hero"><div class="in">'
                '<div class="hero-meta">CLAUDE CODE 활용 실태</div>'
                '<h1 class="hero-name">통합 대시보드</h1>'
                f'<p class="hero-line">아직 보고서가 없습니다 — Claude Code 에서 '
                f'<code>진단</code> 을 입력해 첫 보고서를 만드세요.</p>'
                f'<div class="hero-role">빌드 {esc(built)}</div></div></header>'
                '<div class="wrap">'
                + card("", '<p style="margin:0">아직 보고서가 없습니다 — Claude Code 에서 '
                           '<code>진단</code> 을 입력해 첫 보고서를 만드세요. '
                           '만들어진 <code>data/{파트}_{이름}_{YYYYMMDD}.json</code> 이 '
                           '이 대시보드의 원본입니다.</p>')
                + build_note_html(notes)
                + '<footer class="foot"><p class="notice">사외 공유 금지 — 파트 내부 회람용입니다</p>'
                  '</footer></div>')
        return html_doc("Claude Code 활용 실태 — 통합 대시보드", body)

    parts = sorted({str(m["data"].get("part") or "") for m in members})
    latest_date = max(str(m["data"].get("date") or "") for m in members)
    title = f"Claude Code 활용 실태 — {' · '.join(parts)}"

    # ── 헤더 + 파트 합계 ──
    tot_sessions = sum(num(g(m["data"], "scale.sessions_long")) for m in members)
    tot_tools = sum(num(g(m["data"], "scale.tool_calls_long")) for m in members)
    tot_prompts = sum(num(g(m["data"], "scale.natural_prompts")) for m in members)
    depths = [num(g(m["data"], "workflow.automation_depth")) for m in members]
    avg_depth = sum(depths) / len(depths) if depths else 0

    hero = ('<header class="hero"><div class="in">'
            '<div class="hero-meta">CLAUDE CODE 활용 실태</div>'
            f'<h1 class="hero-name">{esc(" · ".join(parts))}</h1>'
            f'<p class="hero-line">멤버 {len(members)}명 · 최신 작성일 {esc(latest_date)}</p>'
            f'<div class="hero-role">빌드 {esc(built)} · 각자 <code>진단</code> 을 다시 돌리면 '
            f'새 날짜로 갱신됩니다</div></div></header>')

    kpis = '<div class="kpis">' + "".join([
        kpi_tile("합계 세션", esc(fmt_int(tot_sessions)), "장기"),
        kpi_tile("합계 도구 호출", esc(fmt_int(tot_tools)), "장기"),
        kpi_tile("합계 직접 프롬프트", esc(fmt_int(tot_prompts)), "장기"),
        kpi_tile("평균 자동화 심도", esc(fmt_dec(avg_depth)), "최근 30일", unit="배"),
        kpi_tile("파트", esc(fmt_int(len(parts))), unit="개"),
        kpi_tile("멤버", esc(fmt_int(len(members))), unit="명"),
    ]) + '</div>'

    # ── 01 멤버 카드 ──
    mcards = []
    for m in members:
        d = m["data"]
        fun = d.get("fun")
        nick = str(g(fun, "nickname", "") if isinstance(fun, dict) else "").strip()
        mbti = str(g(fun, "mbti.value", "") if isinstance(fun, dict) else "").strip()
        ei = d.get("expert_index") or {}
        pol = g(d, "speech.politeness", {}) or {}
        badges = []
        if mbti:
            badges.append(f'<span class="badge">{esc(mbti)}</span>')
        if ei:
            badges.append(f'{level_badge(ei)}<span class="badge" style="margin-left:5px">'
                          f'{esc(fmt_int(g(ei, "score")))}점</span>')
        mcards.append(
            f'<div class="mcard"><div class="mtop"><h3>{esc(d.get("name"))}</h3>'
            f'<span class="mpart">{esc(d.get("part"))} · {esc(d.get("date"))}</span></div>'
            + (f'<div><span class="badge" style="background:var(--accent-soft);color:#A8380F">'
               f'{esc(nick)}</span></div>' if nick else "")
            + f'<div class="mline">{esc(g(d, "summary.one_liner", ""))}</div>'
            + f'<div class="mkpis">'
              f'<div class="mkpi"><b>{esc(fmt_int(g(d, "scale.sessions_long")))}</b><span>세션 (장기)</span></div>'
              f'<div class="mkpi"><b>{esc(fmt_tok(g(d, "scale.tool_calls_long")))}</b><span>도구 호출 (장기)</span></div>'
              f'<div class="mkpi"><b>{esc(fmt_dec(g(d, "workflow.automation_depth")))}배</b>'
              f'<span>자동화 심도 (30일)</span></div></div>'
            + stack_bar([("존댓말", num(pol.get("formal")), SERIES[1]),
                         ("반말", num(pol.get("casual")), SERIES[0]),
                         ("체언종결", num(pol.get("noun")), SERIES[2])])
            + (f'<div class="pills">{"".join(badges)}</div>' if badges else "")
            + f'<div class="mlinks"><a class="btn btn-p" href="{esc(m["page_href"])}">개인 페이지</a>'
              f'</div></div>')
    s1 = f'<div class="members">{"".join(mcards)}</div>'

    # ── 02 비교 차트 ──
    s2 = ('<div class="grid2">'
          + compare_card("세션 수 (장기)", members, lambda d: g(d, "scale.sessions_long"))
          + compare_card("도구 호출 (장기)", members, lambda d: g(d, "scale.tool_calls_long"), color=ACCENT2)
          + compare_card("직접 프롬프트 (장기)", members, lambda d: g(d, "scale.natural_prompts"))
          + compare_card("자동화 심도 (최근 30일)", members, lambda d: g(d, "workflow.automation_depth"),
                         fmt=lambda v: fmt_dec(v, 1), suffix="배", color=ACCENT2)
          + compare_card("프롬프트 길이 중앙값", members, lambda d: g(d, "speech.len_chars.median"),
                         suffix="자")
          + compare_card("짧은 후속 지시 비율", members, lambda d: g(d, "speech.short_followup_ratio"),
                         fmt=lambda v: fmt_pct(v, 1), color=ACCENT2)
          + compare_card("OMC 명령 사용 비중", members, lambda d: g(d, "workflow.omc.omc_ratio"),
                         fmt=lambda v: fmt_pct(v, 1))
          + compare_card("서브에이전트 메시지 비중", members,
                         lambda d: g(d, "workflow.subagent_msg_ratio"),
                         fmt=lambda v: fmt_pct(v, 1), color=ACCENT2)
          + compare_card("한 지시당 실행 시간 중앙값 (최근 30일)", members,
                         lambda d: g(d, "workflow.turn_duration.median_sec"), fmt=fmt_dur)
          + '</div>')

    # ── 03 개인별 그래프 ── (파트 합산이 아니라 사람마다 같은 6개 미니 차트를 나란히)
    pcards = []
    for m in members:
        d = m["data"]
        td = g(d, "workflow.turn_duration") or {}
        markers = g(d, "speech.markers_per_100", {}) or {}
        mk = sorted(((str(k), num(v)) for k, v in markers.items()), key=lambda x: -x[1])[:5]
        panels = [
            ("월별 세션 (장기)",
             svg_vbars(pair_list(g(d, "scale.sessions_by_month")), color=ACCENT, bar_w=18, gap=8,
                       height=110, show_values=False, label_fmt=tiny_month)),
            ("시간대 분포 (0~23시)", hour_strip(g(d, "scale.by_hour"), base=(23, 91, 99))),
            ("OMC 명령 Top 5 (장기)",
             bar_list(pair_list(g(d, "workflow.omc.commands"), 5), color=ACCENT2, empty="OMC 명령 기록 없음")),
            ("한 지시당 실행 시간 분포 (최근 30일)",
             bar_list(pair_list(td.get("buckets")), color=ACCENT, suffix="건",
                      empty="데이터 없음 — 집계 스크립트를 다시 돌리면 채워집니다")),
            ("성향 5축", svg_radar(g(d, "profile.axes", {}) or {}, size=220, color=ACCENT2)),
            ("화법 마커 Top 5 (100건당)", bar_list(mk, color=ACCENT2, fmt=lambda v: fmt_dec(v, 1))),
        ]
        pcards.append(
            f'<div class="card pcard"><div class="ptop"><h3>{esc(d.get("name"))}</h3>'
            f'<span class="mpart">{esc(d.get("part"))} · {esc(d.get("date"))}</span>'
            f'<a class="btn btn-s" href="{esc(m["page_href"])}" style="margin-left:auto">개인 페이지</a></div>'
            f'<div class="pcharts">'
            + "".join(f'<div class="pchart"><div class="cardtitle">{esc(t)}</div>{b}</div>' for t, b in panels)
            + '</div></div>')
    s2b = "".join(pcards)

    # ── 03 AI 사용 전문가 지수 순위 (재미용) ──
    ranked = sorted(members, key=lambda m: -num(g(m["data"], "expert_index.score")))
    rank_rows = []
    for i, m in enumerate(ranked, 1):
        d = m["data"]
        ei = d.get("expert_index") or {}
        score = int(num(ei.get("score")))
        level = str(ei.get("level") or ei_level_of(score)[0])
        emoji = str(ei.get("emoji") or ei_level_of(score)[1])
        bd = ei.get("breakdown") or {}
        segs = "".join(
            f'<i style="width:{max(0.0, num(bd.get(k))) / 100 * 100:.2f}%;'
            f'background:{SERIES[j % len(SERIES)]}" title="{esc(EI_AXIS_KO[k])} '
            f'{esc(fmt_dec(bd.get(k), 1))}/20"></i>' for j, k in enumerate(EI_AXES))
        rank_rows.append(
            f'<div class="rankrow"><span class="rankno">{i}</span>'
            f'<span class="rankname">{esc(d.get("name"))}<span>{esc(d.get("part"))}</span></span>'
            f'<span class="rankbars">{segs}</span>'
            f'<span class="rankscore"><b>{score}</b>'
            f'<span style="font-size:11px;color:{MUTED}">/100</span><br>'
            f'{level_badge(ei)}</span></div>')
    axis_legend = " ".join(
        f'<span><i style="background:{SERIES[j % len(SERIES)]}"></i>{esc(EI_AXIS_KO[k])}</span>'
        for j, k in enumerate(EI_AXES))
    s3 = card("", '<span class="fakebadge">재미용 · 인사 평가나 줄세우기에 쓰지 마세요</span>'
                  f'<div style="margin-top:12px">{"".join(rank_rows)}</div>'
                  f'<div class="legend" style="margin-top:12px">{axis_legend}</div>'
                  '<div class="note">막대는 5축 각 0~20점을 이어 붙인 것입니다. '
                  '산식은 <b>docs/SUMMARY_SCHEMA.md</b> 에 공개돼 있고, '
                  '<code>formula_version</code> 이 다른 보고서끼리는 점수를 비교하지 않습니다.</div>')

    # ── 04 성향 프로파일 비교 ──
    names = [str(m["data"].get("name") or "") for m in members]
    axis_rows = []
    for m in members:
        axes = g(m["data"], "profile.axes", {}) or {}
        tds = "".join(f'<td>{dots(axes.get(k))}</td>' for k in AXIS_ORDER)
        axis_rows.append(f'<tr><th class="rowh">{esc(m["data"].get("name"))}</th>{tds}</tr>')
    axis_head = "".join(f'<th title="{esc(AXIS_POLE[k])}">{esc(AXIS_KO[k])}</th>' for k in AXIS_ORDER)
    s4 = card("멤버 × 5축 (채워진 점 = 점수, 1~5)",
              f'<div class="scrollx"><table class="heat" style="min-width:0">'
              f'<thead><tr><th class="rowh"></th>{axis_head}</tr></thead>'
              f'<tbody>{"".join(axis_rows)}</tbody></table></div>'
              + '<div class="note">' + " · ".join(
                  f"<b>{esc(AXIS_KO[k])}</b> {esc(AXIS_POLE[k])}" for k in AXIS_ORDER) + '</div>')

    # ── 05 말투 비교 ──
    pol_rows = []
    for m in members:
        pol = g(m["data"], "speech.politeness", {}) or {}
        pol_rows.append(
            f'<div style="margin-bottom:12px"><div style="font-size:13px;font-weight:700;'
            f'margin-bottom:5px">{esc(m["data"].get("name"))}</div>'
            + stack_bar([("존댓말", num(pol.get("formal")), SERIES[1]),
                         ("반말", num(pol.get("casual")), SERIES[0]),
                         ("체언종결", num(pol.get("noun")), SERIES[2])]) + '</div>')
    marker_matrix = [[num((g(m["data"], "speech.markers_per_100", {}) or {}).get(mk)) for mk in MARKERS]
                     for m in members]
    s5 = ('<div class="grid2">'
          + card("존댓말 · 반말 · 체언종결", "".join(pol_rows))
          + card("화법 마커 10종 (100건당)",
                 heat_table(names, MARKERS, marker_matrix, fmt=lambda v: fmt_dec(v, 1)))
          + '</div>')

    # ── 06 시간대 히트맵 ──
    hour_matrix = []
    for m in members:
        row = [num(x) for x in (g(m["data"], "scale.by_hour", []) or [])][:24]
        row += [0] * (24 - len(row))
        hour_matrix.append(row)
    s6 = card("멤버 × 24시간 (행마다 자기 최댓값 기준으로 색을 매깁니다)",
              heat_table(names, [str(h) for h in range(24)], hour_matrix,
                         base=(23, 91, 99), per_row=True))

    # ── 08 OMC · 모델 합산 ──
    def agg(getter):
        acc = {}
        for m in members:
            for k, v in pair_list(getter(m["data"])):
                acc[k] = acc.get(k, 0) + v
        return sorted(acc.items(), key=lambda x: -x[1])[:10]

    def agg_share():
        acc = {}
        for m in members:
            for k, v in pair_list(g(m["data"], "workflow.models")):
                acc[k] = acc.get(k, 0) + v
        return sorted(acc.items(), key=lambda x: -x[1])[:6]

    s7 = ('<div class="grid2">'
          + card("OMC 명령 Top 10 (파트 합산)",
                 bar_list(agg(lambda d: g(d, "workflow.omc.commands")), color=ACCENT2))
          + card("모델 비중 (멤버 평균)", share_stack([[k, v] for k, v in agg_share()]))
          + '</div>')

    # ── 08 공유 자산 · 제안 ──
    sw_items = []
    for m in members:
        for x in (g(m["data"], "assets.share_worthy", []) or []):
            if isinstance(x, dict) and str(x.get("asset") or "").strip():
                sw_items.append(f'<li><b>{esc(x.get("asset"))}</b> — {esc(x.get("reason"))} '
                                f'<span style="color:{MUTED};font-size:12px">'
                                f'({esc(m["data"].get("name"))})</span></li>')
    def gather(path):
        out = []
        for m in members:
            for x in str_list(g(m["data"], path)):
                out.append(f'<li>{esc(x)} <span style="color:{MUTED};font-size:12px">'
                           f'({esc(m["data"].get("name"))})</span></li>')
        return f"<ul>{''.join(out)}</ul>" if out else '<p class="empty">모인 것이 없습니다</p>'
    s8 = ('<div class="grid3">'
          + card("파트에 공유할 만한 자산",
                 f"<ul>{''.join(sw_items)}</ul>" if sw_items else '<p class="empty">모인 것이 없습니다</p>')
          + card("제안 모음", gather("feedback.proposals"))
          + card("잘 안 되는 작업 유형", gather("feedback.works_poorly"))
          + '</div>')

    # ── 09 이력 ──
    hist_rows = []
    for key in sorted(history.keys()):
        olds = history[key]
        if not olds:
            continue
        part_, name_ = key
        links = " · ".join(f'<a href="{esc(o["page_href"])}">{esc(o["date"])}</a>' for o in olds)
        hist_rows.append(f'<tr><td>{esc(part_)}</td><td><b>{esc(name_)}</b></td><td>{links}</td></tr>')
    s9 = card("이전 회차 보고서",
              (f'<div class="scrollx"><table class="tbl" style="min-width:0"><thead><tr>'
               f'<th>파트</th><th>이름</th><th>이전 회차</th></tr></thead>'
               f'<tbody>{"".join(hist_rows)}</tbody></table></div>')
              if hist_rows else '<p class="empty">아직 이전 회차가 없습니다 — 각자 첫 보고서입니다</p>')

    body = (hero + '<div class="wrap">' + kpis
            + sec("01", "멤버", s1, f"{len(members)}명 · (파트, 이름) 별 최신 1건")
            + sec("02", "비교", s2, "정렬된 가로막대")
            + sec("03", "개인별 그래프", s2b, "사람마다 같은 6개 차트 · 파트 합산 아님")
            + sec("04", "AI 사용 전문가 지수 순위", s3, "재미용")
            + sec("05", "성향 프로파일 비교", s4)
            + sec("06", "말투 비교", s5)
            + sec("07", "시간대", s6)
            + sec("08", "OMC · 모델", s7, "파트 합산")
            + sec("09", "공유 자산과 제안", s8)
            + sec("10", "이력", s9)
            + build_note_html(notes)
            + '<footer class="foot">'
              '<p>전문가 지수·MBTI·나이대·혈액형은 <b>재미용</b>입니다. 인사 평가나 줄세우기에 쓰지 마세요.</p>'
              '<p class="notice">사외 공유 금지 — 파트 내부 회람용입니다</p></footer>'
            + '</div>')
    return html_doc(title, body)


def build_note_html(notes) -> str:
    if not notes:
        return ""
    items = "".join(f'<li><code>{esc(n["file"])}</code> — {esc(n["reason"])}</li>' for n in notes)
    return ('<section class="sec"><div class="seclabel">'
            '<span class="secnum">!</span><span class="sectitle">빌드 노트</span></div>'
            f'<div class="buildnote"><p style="margin:0 0 8px"><b>검증에 걸려 건너뛴 파일 '
            f'{len(notes)}개</b> — 아래 이유를 고친 뒤 다시 커밋하면 대시보드에 올라옵니다. '
            f'<code>python3 scripts/build_site.py --check &lt;파일&gt;</code> 로 로컬에서 확인할 수 있습니다.</p>'
            f'<ul>{items}</ul></div></section>')


# ══════════════════════════════════════════════════════════════════════════════
# 명령
# ══════════════════════════════════════════════════════════════════════════════
def print_issues(errors, warnings, *, prefix="") -> None:
    for e in errors:
        print(f"{prefix}  [오류] {e}")
    for w in warnings:
        print(f"{prefix}  [경고] {w}")


def cmd_scaffold(args) -> int:
    src = Path(args.scaffold)
    if not src.exists():
        print(f"집계 결과 파일이 없습니다: {src}")
        print("먼저 `python3 scripts/cc_usage.py` 를 돌려 cc_usage_stats.json 을 만드세요.")
        return 1
    stats, err = load_json(src)
    if err:
        print(f"{src}: {err}")
        return 1

    part, name = (args.part or "").strip(), (args.name or "").strip()
    if not part or not name:
        print("--part 와 --name 은 필수입니다. 예) --part 영업1파트 --name 홍길동")
        return 1
    for label, v in (("파트", part), ("이름", name)):
        if "_" in v or " " in v:
            print(f"{label} 에 언더스코어 '_' 나 공백을 쓸 수 없습니다: {v!r}")
            print("언더스코어는 파일명 구분자입니다. 공백은 하이픈 '-' 으로 바꿔 주세요.")
            return 1
    date = (args.date or datetime.datetime.now(KST).strftime("%Y-%m-%d")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print(f"--date 는 YYYY-MM-DD 형식이어야 합니다: {date!r}")
        return 1

    out_dir = Path(args.data) if args.data else (ROOT / "data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{part}_{name}_{date.replace('-', '')}.json"
    if out.exists() and not args.force:
        print(f"이미 있습니다: {out}")
        print("덮어쓰려면 --force 를 붙이세요. (기존 내용의 서술 필드가 사라집니다)")
        return 1

    doc = build_scaffold(stats, part=part, name=name, date=date,
                         role=args.role or "", highlight=args.highlight or "")
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ei = doc["expert_index"]
    print(f"만들었습니다 -> {out}")
    print(f"  수치 자동 입력 — 장기 세션 {fmt_int(doc['scale']['sessions_long'])} · "
          f"도구 호출 {fmt_int(doc['scale']['tool_calls_long'])} · "
          f"자동화 심도 {fmt_dec(doc['workflow']['automation_depth'])}배 · "
          f"전문가 지수 {ei['score']} {ei['emoji']} {ei['level']}")
    env = doc["env"]
    miss = [k for k, v in env.items() if not v]
    if miss:
        print(f"  자동 수집 실패 (직접 채워 주세요) — env: {', '.join(miss)}")
    if not doc["script_commit"]:
        print("  자동 수집 실패 (직접 채워 주세요) — script_commit")
    print("  아직 비어 있는 것 — summary · rhythm_note · style_note · style_summary · "
          "reproduced_prompts · assets.share_worthy · cases · profile · fun · feedback · coverage.history")
    print(f"  다 채운 뒤: python3 scripts/build_site.py --check {out}")
    return 0


def cmd_check(args) -> int:
    path = Path(args.check)
    data, err = load_json(path)
    if err:
        print(f"{path.name}: [오류] {err}")
        return 1
    errors, warnings = validate(data, path)
    if errors:
        print(f"{path.name}: 검증 실패 — 오류 {len(errors)}개"
              + (f", 경고 {len(warnings)}개" if warnings else ""))
        print_issues(errors, warnings)
        return 1
    print(f"{path.name}: 검증 통과"
          + (f" (경고 {len(warnings)}개)" if warnings else ""))
    print_issues([], warnings)
    return 0


def cmd_person(args) -> int:
    path = Path(args.person)
    data, err = load_json(path)
    if err:
        print(f"{path.name}: [오류] {err}")
        return 1
    errors, warnings = validate(data, path)
    if errors:
        print(f"{path.name}: 검증 실패 — 렌더하지 않습니다 (오류 {len(errors)}개)")
        print_issues(errors, warnings)
        return 1
    print_issues([], warnings)
    out = path.with_suffix(".html")
    out.write_text(render_person(data), encoding="utf-8")
    print(f"만들었습니다 -> {out}  ({out.stat().st_size:,} bytes)")
    return 0


def cmd_site(args) -> int:
    data_dir = FIXTURES if args.demo else (Path(args.data) if args.data else ROOT / "data")
    out_dir = Path(args.out)
    out_data = out_dir / "data"
    out_data.mkdir(parents=True, exist_ok=True)

    if not data_dir.exists():
        print(f"데이터 디렉터리가 없습니다: {data_dir}")
        return 1
    print(f"데이터: {data_dir}" + (" (데모)" if args.demo else ""))

    entries, notes = [], []
    for jp in sorted(data_dir.glob("*.json")):
        data, err = load_json(jp)
        if err:
            notes.append({"file": jp.name, "reason": err})
            print(f"건너뜀 {jp.name}: {err}")
            continue
        errors, warnings = validate(data, jp)
        if errors:
            reason = errors[0] + (f" (외 {len(errors) - 1}건)" if len(errors) > 1 else "")
            notes.append({"file": jp.name, "reason": reason})
            print(f"건너뜀 {jp.name}: 검증 실패 오류 {len(errors)}개")
            print_issues(errors, warnings, prefix="  ")
            continue
        if warnings:
            print(f"{jp.name}: 경고 {len(warnings)}개")
            print_issues([], warnings, prefix="  ")
        stem = jp.stem
        (out_data / f"{stem}.html").write_text(render_person(data), encoding="utf-8")
        entries.append({"data": data, "stem": stem, "date": str(data.get("date") or ""),
                        "page_href": f"data/{stem}.html"})

    # (파트, 이름) 별 최신 1건이 대표, 나머지는 이력
    grouped = {}
    for e in entries:
        grouped.setdefault((str(e["data"].get("part")), str(e["data"].get("name"))), []).append(e)
    members, history = [], {}
    for key, items in grouped.items():
        items.sort(key=lambda x: x["date"], reverse=True)
        members.append(items[0])
        history[key] = items[1:]
    members.sort(key=lambda m: (str(m["data"].get("part")), str(m["data"].get("name"))))

    index = out_dir / "index.html"
    index.write_text(render_index(members, history, notes), encoding="utf-8")
    print(f"만들었습니다 -> {index}  (멤버 {len(members)}명 · 페이지 {len(entries)}개"
          + (f" · 건너뜀 {len(notes)}개" if notes else "") + ")")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="build_site.py",
        description="요약 JSON 으로 개인 시각화 페이지와 통합 대시보드를 만든다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="예)\n"
               "  python3 scripts/build_site.py --scaffold cc_usage_stats.json "
               "--part 영업1파트 --name 홍길동 --date 2026-08-28\n"
               "  python3 scripts/build_site.py --check  data/영업1파트_홍길동_20260828.json\n"
               "  python3 scripts/build_site.py --person data/영업1파트_홍길동_20260828.json\n"
               "  python3 scripts/build_site.py --out _site\n"
               "  python3 scripts/build_site.py --out _site --demo\n")
    p.add_argument("--scaffold", metavar="cc_usage_stats.json",
                   help="집계 결과에서 요약 JSON 뼈대를 만든다 (--part --name 필수)")
    p.add_argument("--check", metavar="요약JSON", help="스키마 검증만 한다")
    p.add_argument("--person", metavar="요약JSON", help="개인 페이지 .html 을 같은 위치에 렌더한다")
    p.add_argument("--out", metavar="디렉터리", help="통합 대시보드를 빌드할 위치 (예: _site)")
    p.add_argument("--data", metavar="디렉터리", help="요약 JSON 이 모인 디렉터리 (기본: data)")
    p.add_argument("--demo", action="store_true", help="scripts/fixtures 를 데이터로 데모 빌드")
    p.add_argument("--part", help="파트 이름 (언더스코어·공백 금지)")
    p.add_argument("--name", help="이름 (언더스코어·공백 금지)")
    p.add_argument("--date", help="작성일 YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--role", default="", help="주 담당 업무 한 줄")
    p.add_argument("--highlight", default="", help="특별히 강조하고 싶은 것")
    p.add_argument("--force", action="store_true", help="--scaffold 가 기존 파일을 덮어쓴다")
    args = p.parse_args(argv)

    if args.scaffold:
        return cmd_scaffold(args)
    if args.check:
        return cmd_check(args)
    if args.person:
        return cmd_person(args)
    if args.out:
        return cmd_site(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
