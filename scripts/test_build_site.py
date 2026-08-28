#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_site.py 테스트.

    python3 -m unittest discover -s scripts -p 'test_*.py'

임시 파일은 전부 tempfile 로 만든다. 저장소의 data/ 에는 아무것도 쓰지 않는다.
"""
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_site as B  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CC_USAGE = Path(__file__).resolve().parent / "cc_usage.py"

# 일부러 검증에 걸리게 만든 fixture — 빌드 노트 동작을 보여주기 위한 파일이다.
INVALID_FIXTURES = {"샘플파트_샘플-오류_20260820.json"}


def valid_fixtures():
    return [p for p in sorted(FIXTURES.glob("*.json")) if p.name not in INVALID_FIXTURES]


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def run_cli(argv):
    """build_site.main() 을 조용히 실행하고 (종료코드, stdout) 을 돌려준다."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = B.main(argv)
    return rc, buf.getvalue()


class TestFixtures(unittest.TestCase):
    def test_fixtures_exist(self):
        self.assertGreaterEqual(len(valid_fixtures()), 4, "정상 fixture 가 4개 이상이어야 한다")
        for name in INVALID_FIXTURES:
            self.assertTrue((FIXTURES / name).exists(), f"{name} 이 있어야 한다")

    def test_all_valid_fixtures_pass_check(self):
        for p in valid_fixtures():
            with self.subTest(fixture=p.name):
                errors, _ = B.validate(load(p), p)
                self.assertEqual(errors, [], f"{p.name} 검증 실패: {errors}")

    def test_invalid_fixture_fails_check(self):
        p = FIXTURES / "샘플파트_샘플-오류_20260820.json"
        errors, _ = B.validate(load(p), p)
        self.assertTrue(errors, "일부러 망가뜨린 fixture 는 검증에 걸려야 한다")
        joined = " ".join(errors)
        self.assertIn("금지 키", joined)
        self.assertIn("by_hour", joined)

    def test_fixtures_have_no_forbidden_keys(self):
        for p in valid_fixtures():
            with self.subTest(fixture=p.name):
                self.assertEqual(B.scan_forbidden(load(p)), [])

    def test_markers_match_cc_usage(self):
        """화법 마커 이름이 scripts/cc_usage.py 의 MARKERS 와 정확히 같아야 한다."""
        src = CC_USAGE.read_text(encoding="utf-8")
        m = re.search(r"^MARKERS = \{(.*?)^\}", src, re.S | re.M)
        self.assertIsNotNone(m, "cc_usage.py 에서 MARKERS 블록을 찾지 못했다")
        names = re.findall(r'^\s{4}"([^"]+)":', m.group(1), re.M)
        self.assertEqual(len(names), 10, f"cc_usage.py 의 마커가 10종이 아니다: {names}")
        self.assertEqual(sorted(names), sorted(B.MARKERS),
                         "build_site.MARKERS 가 cc_usage.py 의 MARKERS 와 다르다")


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bs-check-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = FIXTURES / "샘플파트_샘플-가_20260828.json"
        self.data = load(self.src)

    def write(self, data, name="샘플파트_샘플-가_20260828.json"):
        p = self.tmp / name
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def test_nested_forbidden_key_rejected(self):
        for path in (("speech", "samples_longest"), ("cases", 0, "first_prompt"),
                     ("fun", "gender")):
            with self.subTest(path=path):
                d = json.loads(json.dumps(self.data))
                node = d
                for k in path[:-1]:
                    node = node[k]
                node[path[-1]] = "원문이 들어오면 안 된다"
                errors, _ = B.validate(d, self.write(d))
                self.assertTrue(any("금지 키" in e for e in errors),
                                f"{path} 를 걸러내지 못했다: {errors}")

    def test_part_mismatch_with_filename(self):
        d = json.loads(json.dumps(self.data))
        d["part"] = "다른파트"
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any(e.startswith("part:") for e in errors), errors)

    def test_name_mismatch_with_filename(self):
        d = json.loads(json.dumps(self.data))
        d["name"] = "다른이름"
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any(e.startswith("name:") for e in errors), errors)

    def test_date_mismatch_with_filename(self):
        d = json.loads(json.dumps(self.data))
        d["date"] = "2026-01-02"
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any(e.startswith("date:") for e in errors), errors)

    def test_bad_filename_shape(self):
        d = json.loads(json.dumps(self.data))
        errors, _ = B.validate(d, self.write(d, "언더스코어없는이름.json"))
        self.assertTrue(any("파일명" in e for e in errors), errors)

    def test_schema_version(self):
        d = json.loads(json.dumps(self.data))
        d["schema_version"] = 2
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any(e.startswith("schema_version") for e in errors), errors)

    def test_missing_narrative_fields_fail(self):
        cases = [
            ("summary.one_liner", lambda d: d["summary"].update(one_liner="")),
            ("speech.style_summary", lambda d: d["speech"].update(style_summary=["하나", "둘"])),
            ("speech.reproduced_prompts", lambda d: d["speech"].update(reproduced_prompts=[])),
            ("profile.definition", lambda d: d["profile"].update(definition="  ")),
            ("cases", lambda d: d.update(cases=d["cases"][:2])),
            ("feedback.works_well", lambda d: d["feedback"].update(works_well=[])),
            ("feedback.works_poorly", lambda d: d["feedback"].update(works_poorly=[])),
            ("feedback.blockers", lambda d: d["feedback"].update(blockers=[])),
            ("feedback.proposals", lambda d: d["feedback"].update(proposals=[""])),
        ]
        for label, mutate in cases:
            with self.subTest(field=label):
                d = json.loads(json.dumps(self.data))
                mutate(d)
                errors, _ = B.validate(d, self.write(d))
                self.assertTrue(any(label.split(".")[-1] in e or label in e for e in errors),
                                f"{label} 가 비었는데 통과했다: {errors}")

    def test_axes_must_be_int_1_to_5(self):
        for bad in (0, 6, 3.5, "4", None):
            with self.subTest(value=bad):
                d = json.loads(json.dumps(self.data))
                d["profile"]["axes"]["planning"] = bad
                errors, _ = B.validate(d, self.write(d))
                self.assertTrue(any("profile.axes.planning" in e for e in errors), errors)

    def test_markers_must_be_complete(self):
        d = json.loads(json.dumps(self.data))
        d["speech"]["markers_per_100"].pop("검증요구")
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any("markers_per_100" in e for e in errors), errors)

    def test_by_hour_length(self):
        d = json.loads(json.dumps(self.data))
        d["scale"]["by_hour"] = [0] * 23
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any("by_hour" in e for e in errors), errors)

    def test_omc_block_required(self):
        d = json.loads(json.dumps(self.data))
        d["workflow"].pop("omc")
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any("workflow.omc" in e for e in errors), errors)

    def test_expert_index_required(self):
        d = json.loads(json.dumps(self.data))
        d["expert_index"]["breakdown"].pop("omc")
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any("breakdown" in e for e in errors), errors)
        d2 = json.loads(json.dumps(self.data))
        d2["expert_index"]["score"] = 140
        errors2, _ = B.validate(d2, self.write(d2))
        self.assertTrue(any("expert_index.score" in e for e in errors2), errors2)

    def test_expert_index_block_missing_fails(self):
        """expert_index 블록이 통째로 없으면 --check 가 실패해야 한다."""
        for mutate in (lambda d: d.pop("expert_index"),
                       lambda d: d.update(expert_index=None)):
            with self.subTest(mutate=mutate):
                d = json.loads(json.dumps(self.data))
                mutate(d)
                errors, _ = B.validate(d, self.write(d))
                self.assertTrue(any(e.startswith("expert_index:") for e in errors), errors)

    def test_expert_index_required_even_when_fun_is_null(self):
        d = json.loads(json.dumps(self.data))
        d["fun"] = None
        d.pop("expert_index")
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any(e.startswith("expert_index:") for e in errors), errors)

    def test_expert_index_score_must_be_int(self):
        for bad in (63.5, "63", True, None):
            with self.subTest(value=bad):
                d = json.loads(json.dumps(self.data))
                d["expert_index"]["score"] = bad
                errors, _ = B.validate(d, self.write(d))
                self.assertTrue(any("expert_index.score" in e for e in errors), errors)

    def test_omc_required_subkeys(self):
        for key in ("commands", "omc_ratio", "prompts_with_omc", "prompts_total"):
            with self.subTest(key=key):
                d = json.loads(json.dumps(self.data))
                d["workflow"]["omc"].pop(key)
                errors, _ = B.validate(d, self.write(d))
                self.assertTrue(any(f"workflow.omc.{key}" in e for e in errors), errors)

    def test_omc_counts_must_be_consistent(self):
        d = json.loads(json.dumps(self.data))
        d["workflow"]["omc"]["prompts_with_omc"] = d["workflow"]["omc"]["prompts_total"] + 1
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any("prompts_with_omc" in e for e in errors), errors)

    def test_fun_may_be_null(self):
        d = json.loads(json.dumps(self.data))
        d["fun"] = None
        errors, _ = B.validate(d, self.write(d))
        self.assertEqual(errors, [], f"fun: null 은 허용해야 한다: {errors}")

    def test_long_string_is_warning_not_error(self):
        d = json.loads(json.dumps(self.data))
        d["summary"]["habit"] = "가" * 600
        errors, warnings = B.validate(d, self.write(d))
        self.assertEqual(errors, [])
        self.assertTrue(any("500자 초과" in w for w in warnings), warnings)

    def test_share_ratios_must_be_0_to_1(self):
        d = json.loads(json.dumps(self.data))
        d["workflow"]["models"] = [["claude-opus-5", 420]]
        errors, _ = B.validate(d, self.write(d))
        self.assertTrue(any("비중" in e for e in errors), errors)


class TestExpertIndex(unittest.TestCase):
    def test_known_input_gives_expected_score(self):
        """산식 단위 테스트 — 손으로 계산한 값과 일치해야 한다.

        sessions_long 300  → 20 × log10(301)/log10(301)      = 20.0
        automation   20.0  → 20 × (20.0 / 40)                = 10.0
        delegation   0.175 → 20 × (0.175 / 0.35)             = 10.0
        assets       6점   → 20 × (6 / 12)                   = 10.0
          asset_points = global 2 + rules 1 + agents 0 + commands 1
                       + skills 1 + hooks 1 + mcp 0 + project 0 = 6
        omc                → 20 × (0.5×0.125/0.25 + 0.5×3/6) = 10.0
        합계 60 → 🧠 전문가 (60~79)
        """
        counts = {"global_claude_md": 1, "rules": 1, "agents": 0, "commands": 1,
                  "skills": 1, "hooks": 1, "mcp_servers": 0, "project_claude_md": 0}
        self.assertEqual(B.asset_points(counts), 6)
        ei = B.expert_index(sessions_long=300, automation_depth=20.0, subagent_msg_ratio=0.175,
                            counts=counts, omc_ratio=0.125, distinct_commands=3)
        self.assertEqual(ei["score"], 60)
        self.assertEqual(ei["level"], "전문가")
        self.assertEqual(ei["emoji"], "🧠")
        self.assertEqual(ei["formula_version"], 1)
        self.assertEqual(ei["breakdown"], {"volume": 20.0, "automation": 10.0,
                                           "delegation": 10.0, "assets": 10.0, "omc": 10.0})
        self.assertEqual(ei["inputs"], {"sessions_long": 300, "automation_depth": 20.0,
                                        "subagent_msg_ratio": 0.175, "asset_points": 6,
                                        "omc_ratio": 0.125, "distinct_commands": 3})

    def test_level_boundaries(self):
        for score, level, emoji in ((0, "입문", "🌱"), (19, "입문", "🌱"), (20, "견습", "🔧"),
                                    (39, "견습", "🔧"), (40, "숙련", "⚙️"), (59, "숙련", "⚙️"),
                                    (60, "전문가", "🧠"), (79, "전문가", "🧠"),
                                    (80, "마스터", "🚀"), (100, "마스터", "🚀")):
            with self.subTest(score=score):
                self.assertEqual(B.ei_level_of(score), (level, emoji))

    def test_bounds_and_levels(self):
        zero = B.expert_index(sessions_long=0, automation_depth=0, subagent_msg_ratio=0,
                              counts={}, omc_ratio=0, distinct_commands=0)
        self.assertEqual(zero["score"], 0)
        self.assertEqual(zero["level"], "입문")
        full = B.expert_index(sessions_long=100000, automation_depth=99, subagent_msg_ratio=1,
                              counts={"global_claude_md": 1, "rules": 9, "agents": 9,
                                      "commands": 9, "skills": 9, "hooks": 9,
                                      "mcp_servers": 9, "project_claude_md": 9},
                              omc_ratio=1, distinct_commands=99)
        self.assertEqual(full["score"], 100)
        self.assertEqual(full["level"], "마스터")

    def test_breakdown_sums_to_score(self):
        for p in valid_fixtures():
            with self.subTest(fixture=p.name):
                ei = load(p)["expert_index"]
                self.assertAlmostEqual(sum(ei["breakdown"].values()), ei["score"], delta=1.0)

    def test_asset_points_capped(self):
        self.assertEqual(B.asset_points({}), 0)
        self.assertEqual(B.asset_points({"global_claude_md": 1}), 2)
        self.assertEqual(B.asset_points({"rules": 99}), 3)


class TestScaffold(unittest.TestCase):
    def test_short_project_name(self):
        self.assertEqual(B.short_project("-Users-hong-WebstormProjects-crm-api"), "crm-api")
        self.assertEqual(B.short_project("-home-hong-dev-order"), "order")
        self.assertEqual(B.short_project("crm-api"), "crm-api")
        self.assertEqual(B.short_project(""), "?")

    def test_normalize_shares_sums_to_one(self):
        out = B.normalize_shares([["a", 7], ["b", 2], ["c", 1]])
        self.assertAlmostEqual(sum(v for _, v in out), 1.0, places=6)

    def test_normalize_shares_empty(self):
        self.assertEqual(B.normalize_shares([]), [])
        self.assertEqual(B.normalize_shares([["a", 0]]), [])

    def test_normalize_dow_fills_seven_days(self):
        out = B.normalize_dow([["Wed", 5], ["Mon", 2]])
        self.assertEqual([k for k, _ in out], B.DOW_ORDER)
        self.assertEqual(dict(out)["Sun"], 0)

    def test_scaffold_from_minimal_stats(self):
        stats = {"totals": {"human_turns": 100, "tool_calls": 1200, "assistant_msgs": 900,
                            "subagent_msgs": 300, "tok_out": 500000, "thinking_tok": 1000,
                            "tok_cache_read": 900000},
                 "session_stats_longwindow": {"sessions": 40, "total_tool_calls": 3000,
                                              "sessions_by_month": [["2026-08", 40]],
                                              "first_session": "2026-08-01 10:00:00",
                                              "last_session": "2026-08-28 10:00:00"},
                 "prompts": {"natural_prompt_count": 80, "slash_top": [["/clear", 5]],
                             "by_month": [["2026-08", 80]], "by_hour": [0] * 24,
                             "by_dow": [["Mon", 80]], "len_chars": {"median": 30, "p90": 90, "max": 500},
                             "korean_prompts": 70, "non_korean_prompts": 10},
                 "speech": {"sample_size": 70, "politeness": {"존댓말": 10, "반말": 50, "중립·체언종결": 10},
                            "markers_per_100": {m: 1.0 for m in B.MARKERS},
                            "punctuation": {"물음표": 5, "느낌표": 1, "문장부호_없음": 30},
                            "sentences_per_prompt": {"avg": 2.0},
                            "inter_prompt_gap_sec": {"median": 60, "p25": 20, "p90": 300},
                            "short_followup_ratio": 0.2, "laugh_prompts": 1, "emoji_prompts": 0,
                            "english_mixed_ratio": 0.3,
                            "endings_top": [["해줘", 10]], "first_words_top": [["일단", 4]],
                            "vocab_top": [["테스트", 9]]},
                 "omc": {"commands": [["autopilot", 5]], "distinct_commands": 1,
                         "prompts_with_omc": 5, "prompts_total": 85, "omc_ratio": 0.059,
                         "slash_omc_ratio": 0.1, "keyword_ratio": 0.02,
                         "keyword_forms": [], "by_month": [["2026-08", 5]]},
                 "customization": {"global_CLAUDE_md_bytes": 100, "rules_files": ["a.md"],
                                   "global_agents": [], "global_commands": [], "global_skills": [],
                                   "hooks": [], "permissions_allow_count": 3, "statusLine": True},
                 "projects": [{"project": "-Users-x-dev-order", "sessions": 10, "active_days": 5,
                               "human_turns": 60, "top_tools": [["Bash", 100], ["Read", 50]],
                               "top_models": [["claude-opus-5", 30]],
                               "first": "2026-08-01T00:00:00Z", "last": "2026-08-28T00:00:00Z"}],
                 "tools_all": [["Bash", 700], ["Read", 500]],
                 "models_all": [["claude-opus-5", 80], ["claude-sonnet-5", 20]],
                 "effort": [["high", 10]], "permissionMode": [["auto", 5]],
                 "mcp_servers_called": [["context7", 3]], "subagent_types": [["Explore", 2]],
                 "skillUsage": [["plan", 4]], "pluginUsage": [], "project_assets": [],
                 "global": {"mcpServers_global": ["context7"]}, "mcpServers_projectScope": []}
        doc = B.build_scaffold(stats, part="샘플파트", name="샘플-라", date="2026-08-28")
        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual(doc["scale"]["sessions_long"], 40)
        self.assertEqual(doc["scale"]["natural_prompts"], 80)
        self.assertEqual(doc["scale"]["slash_prompts"], 5)
        self.assertEqual(doc["workflow"]["automation_depth"], 12.0)
        self.assertEqual(doc["projects_top"][0]["project"], "order")
        self.assertEqual(doc["projects_top"][0]["tool_calls"], 150)  # 상위 도구 합계 근사
        self.assertEqual(len(doc["scale"]["by_hour"]), 24)
        self.assertEqual(len(doc["scale"]["by_dow"]), 7)
        self.assertEqual(set(doc["speech"]["markers_per_100"]), set(B.MARKERS))
        self.assertAlmostEqual(sum(doc["speech"]["politeness"].values()), 1.0, places=6)
        self.assertEqual(doc["workflow"]["omc"]["distinct_commands"], 1)
        self.assertEqual(doc["expert_index"]["formula_version"], 1)
        self.assertEqual(B.scan_forbidden(doc), [], "스캐폴드 결과에 금지 키가 있으면 안 된다")
        # 서술 필드는 비어 있어야 한다 (사람이 채운다)
        self.assertEqual(doc["summary"]["one_liner"], "")
        self.assertEqual(doc["speech"]["reproduced_prompts"], [])
        self.assertEqual(doc["cases"], [])
        # 그러므로 방금 만든 스캐폴드는 --check 를 통과하지 못한다
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "샘플파트_샘플-라_20260828.json"
            p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            errors, _ = B.validate(doc, p)
            self.assertTrue(errors)

    def test_scaffold_cli_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            stats = Path(td) / "stats.json"
            stats.write_text("{}", encoding="utf-8")
            args = ["--scaffold", str(stats), "--part", "샘플파트", "--name", "샘플-라",
                    "--date", "2026-08-28", "--data", td]
            self.assertEqual(run_cli(args)[0], 0)
            out = Path(td) / "샘플파트_샘플-라_20260828.json"
            self.assertTrue(out.exists())
            self.assertEqual(run_cli(args)[0], 1, "--force 없이 덮어쓰면 안 된다")
            self.assertEqual(run_cli(args + ["--force"])[0], 0)

    def test_scaffold_cli_rejects_underscore_in_name(self):
        with tempfile.TemporaryDirectory() as td:
            stats = Path(td) / "stats.json"
            stats.write_text("{}", encoding="utf-8")
            rc, _ = run_cli(["--scaffold", str(stats), "--part", "샘플_파트",
                             "--name", "샘플-라", "--date", "2026-08-28", "--data", td])
            self.assertEqual(rc, 1)


class TestPersonPage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bs-person-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_person_renders_html(self):
        src = FIXTURES / "샘플파트_샘플-가_20260828.json"
        dst = self.tmp / src.name
        shutil.copyfile(src, dst)
        (self.tmp / f"{src.stem}.md").write_text("# 샘플 보고서\n", encoding="utf-8")

        rc, _ = run_cli(["--person", str(dst)])
        self.assertEqual(rc, 0)
        out = self.tmp / f"{src.stem}.html"
        self.assertTrue(out.exists())
        html = out.read_text(encoding="utf-8")

        self.assertIn("샘플-가", html)
        self.assertIn("한 번에 크게 맡기는 사람", html)          # fun.nickname
        self.assertIn("가상 프롬프트", html)                      # 재현 프롬프트 배지
        self.assertIn("실제 발화 아님", html)
        self.assertIn("사외 공유 금지", html)
        self.assertIn(f'href="{src.stem}.md"', html)             # .md 상대 링크
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<svg", html)                               # 인라인 SVG 차트
        self.assertNotIn("<script", html)                         # 인라인 JS 없음
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)                        # 외부 CDN 없음

    def test_person_refuses_invalid_json(self):
        src = FIXTURES / "샘플파트_샘플-오류_20260820.json"
        dst = self.tmp / src.name
        shutil.copyfile(src, dst)
        self.assertEqual(run_cli(["--person", str(dst)])[0], 1)
        self.assertFalse((self.tmp / f"{src.stem}.html").exists(),
                         "검증 실패 파일은 렌더하면 안 된다")

    def test_person_page_escapes_html(self):
        d = load(FIXTURES / "샘플파트_샘플-가_20260828.json")
        d["summary"]["one_liner"] = '<img src=x onerror="alert(1)">'
        p = self.tmp / "샘플파트_샘플-가_20260828.json"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        html = B.render_person(d)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)

    def test_fun_null_hides_fun_section(self):
        d = load(FIXTURES / "샘플파트_샘플-나_20260828.json")
        self.assertIsNone(d["fun"])
        html = B.render_person(d)
        self.assertNotIn('<span class="sectitle">재미 코너</span>', html)
        self.assertIn('<span class="sectitle">AI 사용 전문가 지수</span>', html)

    def test_omc_card_renders_ratio_and_forms(self):
        d = load(FIXTURES / "샘플파트_샘플-가_20260828.json")
        html = B.render_person(d)
        self.assertIn("OMC 명령어", html)
        self.assertIn("OMC 명령어 사용 비중", html)
        self.assertIn("52.0%", html)                       # omc_ratio 큰 숫자
        self.assertIn("61.0%", html)                       # slash_omc_ratio
        self.assertIn("44.0%", html)                       # keyword_ratio
        self.assertIn("자연어 매직 키워드", html)
        self.assertIn("ulw", html)                         # keyword_forms 칩
        self.assertIn("도입 추이", html)                    # by_month 소형 막대
        for cmd, _ in d["workflow"]["omc"]["commands"]:    # commands 는 전부 그린다
            self.assertIn(cmd, html)
        self.assertNotIn("Bash 명령", html)                 # bash_top 흔적 없음

    def test_expert_index_card_always_rendered(self):
        for name in ("샘플파트_샘플-가_20260828.json", "샘플파트_샘플-나_20260828.json"):
            with self.subTest(fixture=name):
                d = load(FIXTURES / name)
                html = B.render_person(d)
                self.assertIn('<span class="sectitle">AI 사용 전문가 지수</span>', html)
                self.assertIn("재미용 · 산식 공개", html)
                self.assertIn(str(d["expert_index"]["score"]), html)
                self.assertIn(d["expert_index"]["level"], html)
                for ko in B.EI_AXIS_KO.values():
                    self.assertIn(ko, html)
        # fun 이 null 이어도 전문가 지수 카드는 남고 재미 코너만 사라진다
        d = load(FIXTURES / "샘플파트_샘플-나_20260828.json")
        self.assertIsNone(d["fun"])
        self.assertNotIn('<span class="sectitle">재미 코너</span>', B.render_person(d))

    def test_small_sample_shows_warning_badge(self):
        d = load(FIXTURES / "샘플2파트_샘플-다_20260827.json")
        self.assertLess(d["coverage"]["speech_sample_size"], 100)
        self.assertIn("해석 주의", B.render_person(d))

    def test_repo_url_makes_github_md_link(self):
        src = FIXTURES / "샘플파트_샘플-가_20260828.json"
        dst = self.tmp / src.name
        shutil.copyfile(src, dst)
        rc, _ = run_cli(["--person", str(dst), "--repo-url", "https://github.com/o/r"])
        self.assertEqual(rc, 0)
        html = (self.tmp / f"{src.stem}.html").read_text(encoding="utf-8")
        self.assertIn(f"https://github.com/o/r/blob/main/data/{src.stem}.md", html)


class TestSiteBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bs-site-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = self.tmp / "_site"

    def test_demo_build(self):
        rc, _ = run_cli(["--out", str(self.out), "--demo"])
        self.assertEqual(rc, 0, "검증 실패 파일이 있어도 빌드는 성공해야 한다")
        index = self.out / "index.html"
        self.assertTrue(index.exists())
        pages = sorted(p.name for p in (self.out / "data").glob("*.html"))
        self.assertEqual(len(pages), 4, f"정상 fixture 수만큼 개인 페이지가 나와야 한다: {pages}")

        html = index.read_text(encoding="utf-8")
        for name in ("샘플-가", "샘플-나", "샘플-다"):
            self.assertIn(name, html, f"{name} 이 대시보드에 없다")
        self.assertNotIn("아직 보고서가 없습니다", html)
        # 이력: 샘플-가 의 이전 회차(2026-07-01)가 이력으로 보여야 한다
        self.assertIn("이전 회차", html)
        self.assertIn("샘플파트_샘플-가_20260701.html", html)
        # 대표는 최신 1건이므로 멤버 카드 링크는 최신 파일이어야 한다
        self.assertIn("샘플파트_샘플-가_20260828.html", html)
        # 빌드 노트: 검증 실패 파일과 이유가 보여야 한다
        self.assertIn("빌드 노트", html)
        self.assertIn("샘플파트_샘플-오류_20260820.json", html)
        self.assertIn("금지 키", html)
        # 자기완결성
        self.assertNotIn("<script", html)
        self.assertNotIn("https://", html)
        self.assertIn("사외 공유 금지", html)

    def test_dashboard_has_expert_index_ranking(self):
        rc, _ = run_cli(["--out", str(self.out), "--demo"])
        self.assertEqual(rc, 0)
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('<span class="sectitle">AI 사용 전문가 지수 순위</span>', html)
        self.assertIn("인사 평가나 줄세우기에 쓰지 마세요", html)   # 재미용 고지
        for level in ("마스터", "전문가", "견습"):                  # 레벨 배지
            self.assertIn(level, html)
        self.assertIn("rankbars", html)                            # 5축 미니 스택 바
        # 점수 내림차순인지 — 순위 이름 등장 순서로 확인
        order = [m.group(1) for m in re.finditer(r'<span class="rankname">([^<]+)<', html)]
        self.assertEqual(order, ["샘플-가", "샘플-나", "샘플-다"], f"점수 내림차순이 아니다: {order}")

    def test_dashboard_omc_replaces_bash(self):
        rc, _ = run_cli(["--out", str(self.out), "--demo"])
        self.assertEqual(rc, 0)
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("OMC 명령 Top 10 (파트 합산)", html)
        self.assertIn("OMC 명령 사용 비중", html)
        self.assertNotIn("Bash 명령", html)

    def test_empty_data_dir_shows_empty_state(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        rc, _ = run_cli(["--out", str(self.out), "--data", str(empty)])
        self.assertEqual(rc, 0)
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("아직 보고서가 없습니다", html)
        self.assertIn("진단", html)

    def test_broken_file_is_skipped_but_others_build(self):
        data = self.tmp / "data"
        data.mkdir()
        for p in valid_fixtures():
            shutil.copyfile(p, data / p.name)
        broken = data / "샘플파트_샘플-마_20260828.json"
        broken.write_text("{ this is not json", encoding="utf-8")
        rc, _ = run_cli(["--out", str(self.out), "--data", str(data)])
        self.assertEqual(rc, 0)
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("샘플파트_샘플-마_20260828.json", html)
        self.assertIn("샘플-가", html)
        self.assertEqual(len(list((self.out / "data").glob("*.html"))), len(valid_fixtures()))

    def test_md_is_copied_and_linked(self):
        data = self.tmp / "data"
        data.mkdir()
        src = FIXTURES / "샘플파트_샘플-가_20260828.json"
        shutil.copyfile(src, data / src.name)
        (data / f"{src.stem}.md").write_text("# 보고서\n", encoding="utf-8")
        run_cli(["--out", str(self.out), "--data", str(data)])
        self.assertTrue((self.out / "data" / f"{src.stem}.md").exists())
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'href="data/{src.stem}.md"', html)

    def test_repo_url_rewrites_md_links(self):
        data = self.tmp / "data"
        data.mkdir()
        src = FIXTURES / "샘플파트_샘플-가_20260828.json"
        shutil.copyfile(src, data / src.name)
        run_cli(["--out", str(self.out), "--data", str(data),
                 "--repo-url", "https://github.com/owner/repo/"])
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"https://github.com/owner/repo/blob/main/data/{src.stem}.md", html)

    def test_latest_report_is_representative(self):
        data = self.tmp / "data"
        data.mkdir()
        for name in ("샘플파트_샘플-가_20260828.json", "샘플파트_샘플-가_20260701.json"):
            shutil.copyfile(FIXTURES / name, data / name)
        run_cli(["--out", str(self.out), "--data", str(data)])
        html = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("멤버 1명", html, "같은 사람의 두 회차는 멤버 1명으로 묶여야 한다")


class TestFormatting(unittest.TestCase):
    def test_fmt_tok(self):
        self.assertEqual(B.fmt_tok(0), "0")
        self.assertEqual(B.fmt_tok(830_000), "830K")
        self.assertEqual(B.fmt_tok(1_200_000), "1.2M")
        self.assertEqual(B.fmt_tok(7_800_000_000), "7.8B")

    def test_fmt_int_has_thousand_separators(self):
        self.assertEqual(B.fmt_int(1234567), "1,234,567")

    def test_tok_html_keeps_exact_value_in_title(self):
        self.assertIn('title="1,200,000"', B.tok_html(1_200_000))

    def test_esc(self):
        self.assertEqual(B.esc('<a href="x">'), "&lt;a href=&quot;x&quot;&gt;")

    def test_parse_stem(self):
        self.assertEqual(B.parse_stem("영업1파트_홍길동_20260828"), ("영업1파트", "홍길동", "20260828"))
        self.assertIsNone(B.parse_stem("영업1파트_홍길동"))
        self.assertIsNone(B.parse_stem("영업1파트_홍_길동_20260828"))
        self.assertIsNone(B.parse_stem("영업1파트_홍길동_2026828"))


if __name__ == "__main__":
    unittest.main()
