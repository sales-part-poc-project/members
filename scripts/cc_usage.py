#!/usr/bin/env python3
"""Claude Code 로컬 사용 이력 집계 — 읽기 전용, 네트워크 미사용.

사용법:
    python3 scripts/cc_usage.py [출력경로]      # 기본: ./cc_usage_stats.json

읽는 곳은 ~/.claude/ 와 ~/.claude.json 뿐이다. 아무것도 쓰지 않고, 아무 데도 보내지 않는다.
표준 라이브러리만 쓰므로 설치할 것이 없다 (Python 3.9+).
"""
import collections, datetime, json, re, sys
from pathlib import Path

HOME, CC = Path.home(), Path.home() / ".claude"
PROJ = CC / "projects"
O, C = {}, collections.Counter


def jload(p, d=None):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return d


def names(p, pat="*"):
    return sorted(x.name for x in p.glob(pat)) if p.exists() else []


NOISE = ("<local-command-stdout>", "<local-command-caveat>", "<system-reminder>", "Caveat:",
         "<user-prompt-submit-hook>", "<bash-input>", "<bash-stdout>", "<bash-stderr>",
         "[Request interrupted", "API Error")
AGENT = ("Another Claude session sent a message", "<teammate-message", "<task-notification",
         "<agent-message", "Tool ran without output")


def kind_of(t):
    """사람이 실제로 친 프롬프트만 human 으로 분류한다."""
    t = (t or "").strip()
    if not t or t.startswith(NOISE):
        return "noise", ""
    if t.startswith(("<command-name>", "<command-message>")):
        return "slash", t
    if t.startswith(AGENT):
        return "agent", t
    return "human", t


# ── 1. 전역 설정 / 사용 카운터 ────────────────────────────────────────────────
cfg = jload(HOME / ".claude.json", {}) or {}
O["global"] = {k: cfg.get(k) for k in
               ("installMethod", "numStartups", "firstStartTime", "claudeCodeFirstTokenDate",
                "promptQueueUseCount")}
O["global"]["registeredProjects"] = len(cfg.get("projects") or {})
O["global"]["mcpServers_global"] = sorted((cfg.get("mcpServers") or {}).keys())
for key in ("skillUsage", "toolUsage", "pluginUsage"):
    O[key] = sorted(((k, v.get("usageCount", 0)) for k, v in (cfg.get(key) or {}).items()),
                    key=lambda x: -x[1])[:40]
pm = C()
for v in (cfg.get("projects") or {}).values():
    for n in list((v.get("mcpServers") or {})) + list(v.get("enabledMcpjsonServers") or []):
        pm[n] += 1
O["mcpServers_projectScope"] = pm.most_common()

# ── 2. 트랜스크립트 (최근 약 30일: 자동 정리됨) ───────────────────────────────
def newP():
    return {"sessions": set(), "human": 0, "slash": 0, "agent": 0, "asst": 0, "sub": 0,
            "tools": C(), "models": C(), "days": set(), "branches": set(),
            "ti": 0, "to": 0, "cr": 0, "cc": 0, "th": 0, "first": None, "last": None}


def newS():
    return {"proj": None, "f": None, "l": None, "human": 0, "slash": 0, "agent": 0, "prompt": None,
            "tools": C(), "files": C(), "skills": C(), "models": C(), "subs": C(), "to": 0,
            "branches": set()}


P, S = collections.defaultdict(newP), collections.defaultdict(newS)
tools, models, skills, plugins = C(), C(), C(), C()
effort, permmode, versions, entry = C(), C(), C(), C()
bash, subtypes, mcpcalls = C(), C(), C()
files = sorted(PROJ.rglob("*.jsonl")) if PROJ.exists() else []
bad = 0

for f in files:
    try:
        proj = f.relative_to(PROJ).parts[0]
    except ValueError:
        proj = f.parent.name
    p = P[proj]
    try:
        fh = f.open(encoding="utf-8", errors="replace")
    except Exception:
        continue
    with fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                bad += 1
                continue
            sid = d.get("sessionId")
            s = S[sid] if sid else None
            if s is not None:
                p["sessions"].add(sid)
                s["proj"] = s["proj"] or proj
            ts = d.get("timestamp")
            if ts:
                p["first"] = min(p["first"] or ts, ts); p["last"] = max(p["last"] or ts, ts)
                p["days"].add(ts[:10])
                if s is not None:
                    s["f"] = min(s["f"] or ts, ts); s["l"] = max(s["l"] or ts, ts)
            for src, dst in (("version", versions), ("entrypoint", entry),
                             ("effort", effort), ("permissionMode", permmode),
                             ("attributionPlugin", plugins)):
                if d.get(src):
                    dst[d[src]] += 1
            if d.get("gitBranch"):
                p["branches"].add(d["gitBranch"])
                if s is not None:
                    s["branches"].add(d["gitBranch"])
            if d.get("attributionSkill"):
                skills[d["attributionSkill"]] += 1
                if s is not None:
                    s["skills"][d["attributionSkill"]] += 1
            m = d.get("message") if isinstance(d.get("message"), dict) else {}
            t, side = d.get("type"), bool(d.get("isSidechain"))
            if t == "user" and not side and not d.get("isMeta"):
                c = m.get("content")
                if isinstance(c, list):
                    c = " ".join(b.get("text", "") for b in c
                                 if isinstance(b, dict) and b.get("type") == "text")
                k, txt = kind_of(c if isinstance(c, str) else "")
                if k in ("human", "slash", "agent"):
                    p[k] += 1
                    if s is not None:
                        s[k] += 1
                        if k == "human" and s["prompt"] is None:
                            s["prompt"] = " ".join(txt.split())[:400]
            elif t == "assistant":
                p["sub" if side else "asst"] += 1
                mod = m.get("model")
                if mod:
                    p["models"][mod] += 1; models[mod] += 1
                    if s is not None:
                        s["models"][mod] += 1
                u = m.get("usage") or {}
                for k, fld in (("ti", "input_tokens"), ("to", "output_tokens"),
                               ("cr", "cache_read_input_tokens"), ("cc", "cache_creation_input_tokens")):
                    p[k] += u.get(fld, 0) or 0
                p["th"] += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
                if s is not None:
                    s["to"] += u.get("output_tokens", 0) or 0
                for b in (m.get("content") if isinstance(m.get("content"), list) else []):
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    n, inp = b.get("name") or "?", (b.get("input") or {})
                    p["tools"][n] += 1; tools[n] += 1
                    if s is not None:
                        s["tools"][n] += 1
                    if n.startswith("mcp__"):
                        mcpcalls[n.split("__")[1] if "__" in n else n] += 1
                    if n == "Bash" and isinstance(inp.get("command"), str):
                        h = inp["command"].strip().split()
                        if h:
                            bash[h[0].split("/")[-1]] += 1
                    if isinstance(inp.get("subagent_type"), str):
                        subtypes[inp["subagent_type"]] += 1
                        if s is not None:
                            s["subs"][inp["subagent_type"]] += 1
                    if n in ("Edit", "Write", "NotebookEdit") and isinstance(inp.get("file_path"), str):
                        if s is not None:
                            s["files"][inp["file_path"]] += 1

O.update(transcript_files=len(files), parse_errors=bad, versions=versions.most_common(10),
         entrypoints=entry.most_common(), effort=effort.most_common(),
         permissionMode=permmode.most_common(), tools_all=tools.most_common(40),
         models_all=models.most_common(), skills_from_transcripts=skills.most_common(30),
         plugins_from_transcripts=plugins.most_common(20), bash_commands_top=bash.most_common(30),
         subagent_types=subtypes.most_common(20), mcp_servers_called=mcpcalls.most_common(20))

rows = [{"project": k, "sessions": len(v["sessions"]), "active_days": len(v["days"]),
         "human_turns": v["human"], "slash_turns": v["slash"], "agent_turns": v["agent"],
         "assistant_msgs": v["asst"], "subagent_msgs": v["sub"], "branches": len(v["branches"]),
         "first": v["first"], "last": v["last"], "top_models": v["models"].most_common(3),
         "top_tools": v["tools"].most_common(6), "tok_in": v["ti"], "tok_out": v["to"],
         "tok_cache_read": v["cr"], "tok_cache_create": v["cc"], "thinking_tok": v["th"]}
        for k, v in P.items()]
rows.sort(key=lambda r: -(r["human_turns"] + r["slash_turns"]))
O["projects"] = rows
O["totals"] = {"projects_with_transcripts": len(rows),
               "active_days": len({d for v in P.values() for d in v["days"]}),
               "tool_calls": sum(tools.values()),
               **{k: sum(r[k] for r in rows) for k in
                  ("sessions", "human_turns", "slash_turns", "agent_turns", "assistant_msgs",
                   "subagent_msgs", "tok_in", "tok_out", "tok_cache_read", "tok_cache_create",
                   "thinking_tok")}}

sess = [{"sessionId": k, "project": v["proj"], "start": (v["f"] or "")[:16], "end": (v["l"] or "")[:16],
         "human_turns": v["human"], "slash_turns": v["slash"], "agent_turns": v["agent"],
         "tool_calls": sum(v["tools"].values()), "tok_out": v["to"],
         "branches": sorted(v["branches"])[:3], "top_tools": v["tools"].most_common(5),
         "skills": v["skills"].most_common(3), "subagents": v["subs"].most_common(5),
         "models": v["models"].most_common(2), "files_touched_n": len(v["files"]),
         "files_touched": v["files"].most_common(10), "first_prompt": v["prompt"]}
        for k, v in S.items() if v["human"]]
sess.sort(key=lambda r: -(r["human_turns"] * 3 + r["tool_calls"] / 10))
O["top_sessions"], O["sessions_with_human_turns"] = sess[:15], len(sess)

# ── 3. 장기 세션 통계 (.session-stats.json — 트랜스크립트 정리 후에도 남음) ──
ss = (jload(CC / ".session-stats.json", {}) or {}).get("sessions") or {}
st, mon, lo, hi, calls = C(), C(), None, None, 0
for sid, v in ss.items():
    if sid == "unknown":
        continue
    for k, n in (v.get("tool_counts") or {}).items():
        if k:
            st[k] += n
    calls += v.get("total_calls", 0) or 0
    if (t := v.get("started_at")):
        lo, hi = min(lo or t, t), max(hi or t, t)
        mon[datetime.datetime.fromtimestamp(t).strftime("%Y-%m")] += 1
O["session_stats_longwindow"] = {
    "sessions": len([k for k in ss if k != "unknown"]), "total_tool_calls": calls,
    "first_session": str(datetime.datetime.fromtimestamp(lo)) if lo else None,
    "last_session": str(datetime.datetime.fromtimestamp(hi)) if hi else None,
    "sessions_by_month": sorted(mon.items()), "tools": st.most_common(40)}

# ── 4. 프롬프트 습관 (history.jsonl — 가장 긴 구간) ──────────────────────────
slash, lens, ko, en, tot = C(), [], 0, 0, 0
month, hour, dow, hproj = C(), C(), C(), C()
KO, hist = re.compile(r"[가-힣]"), CC / "history.jsonl"
for line in (hist.read_text(encoding="utf-8", errors="replace").splitlines() if hist.exists() else []):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if not (s0 := (d.get("display") or "").strip()):
        continue
    tot += 1
    hproj[d.get("project") or "?"] += 1
    if (t := d.get("timestamp")):
        dt = datetime.datetime.fromtimestamp(t / 1000)
        month[dt.strftime("%Y-%m")] += 1; hour[dt.hour] += 1; dow[dt.strftime("%a")] += 1
    if s0.startswith("/"):
        slash[s0.split()[0]] += 1
    else:
        lens.append(len(s0))
        ko, en = (ko + 1, en) if KO.search(s0) else (ko, en + 1)
lens.sort()
q = lambda r: lens[min(len(lens) - 1, int(len(lens) * r))] if lens else 0
O["prompts"] = {"total_history_entries": tot,
                "slash_ratio": round(sum(slash.values()) / tot, 3) if tot else 0,
                "slash_top": slash.most_common(25), "natural_prompt_count": len(lens),
                "len_chars": {"p10": q(.1), "median": q(.5), "p90": q(.9),
                              "max": lens[-1] if lens else 0,
                              "avg": round(sum(lens) / len(lens), 1) if lens else 0},
                "korean_prompts": ko, "non_korean_prompts": en,
                "by_month": sorted(month.items()), "by_hour": [hour.get(h, 0) for h in range(24)],
                "by_dow": dow.most_common(), "top_projects_by_prompt": hproj.most_common(15)}

# ── 4b. OMC(oh-my-claudecode) 명령어 사용 (history.jsonl) ─────────────────────
# 슬래시 형태(/autopilot, /oh-my-claudecode:team …)와 자연어 프롬프트 안의 매직 키워드(ulw, ralph …)를 모두 센다.
# Claude Code 기본 명령과 이름이 겹치는 것(plan, review, verify …)은 /oh-my-claudecode: 접두어가 있을 때만 OMC 로 인정한다.
OMC_ONLY = {"autopilot", "ultrawork", "ralph", "ralplan", "team", "execute", "analyze", "ultrapilot",
            "ultraqa", "ultragoal", "autoresearch", "cancel", "ask", "trace", "deepinit", "skillify",
            "omc-setup", "omc-doctor", "mcp-setup", "self-improve", "external-context", "ai-slop-cleaner",
            "deep-interview", "configure-notifications", "project-session-manager", "visual-verdict",
            "swarm", "pipeline", "merge-readiness", "deep-dive", "sciomc", "ccg", "omc-teams",
            "learner", "writer-memory", "deslop", "ultrathink", "deepsearch", "tdd"}
OMC_KW = {"ulw": "ultrawork", "ultrawork": "ultrawork", "autopilot": "autopilot", "ralph": "ralph",
          "ralplan": "ralplan", "ultrathink": "ultrathink", "deepsearch": "deepsearch",
          "deep-interview": "deep-interview", "cancelomc": "cancel", "deslop": "ai-slop-cleaner",
          "deep-analyze": "analyze", "ultragoal": "ultragoal", "autoresearch": "autoresearch",
          "ultrapilot": "ultrapilot", "tdd": "tdd"}
OMC_PREFIX = re.compile(r"oh-my-claudecode:([a-z][a-z0-9-]*)")
OMC_KW_RE = re.compile(r"(?<![A-Za-z0-9])(deep[\s-]+interview|"
                       + "|".join(sorted((re.escape(k) for k in OMC_KW if k != "deep-interview"), key=len, reverse=True))
                       + r")(?![A-Za-z0-9])", re.I)
omc_cmd, omc_slash_raw, omc_kw_raw, omc_month = C(), C(), C(), C()
omc_prompts = omc_slash_n = omc_nat_n = 0
for line in (hist.read_text(encoding="utf-8", errors="replace").splitlines() if hist.exists() else []):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if not (s0 := (d.get("display") or "").strip()):
        continue
    hit = set()
    if s0.startswith("/"):
        tok = s0.split()[0]
        m = OMC_PREFIX.search(tok)
        name = m.group(1).lower() if m else tok.lstrip("/").lower()
        if m or name in OMC_ONLY:
            hit.add(name); omc_slash_raw[tok] += 1; omc_slash_n += 1
        for k in OMC_KW_RE.findall(s0[len(tok):]):   # 슬래시 뒤 인자에 섞인 키워드 (/commit ulw 해줘)
            k = re.sub(r"[\s-]+", "-", k.lower())
            hit.add(OMC_KW.get(k, k)); omc_kw_raw[k] += 1
    else:
        for k in OMC_KW_RE.findall(s0):
            k = re.sub(r"[\s-]+", "-", k.lower())
            hit.add(OMC_KW.get(k, k)); omc_kw_raw[k] += 1
        if hit:
            omc_nat_n += 1
    if hit:
        omc_prompts += 1
        for h in hit:
            omc_cmd[h] += 1
        if (t := d.get("timestamp")):
            omc_month[datetime.datetime.fromtimestamp(t / 1000).strftime("%Y-%m")] += 1
n_slash_all = sum(slash.values())
O["omc"] = {"commands": omc_cmd.most_common(),            # 정규화된 명령 이름 (슬래시 + 키워드 합산)
            "distinct_commands": len(omc_cmd),
            "slash_forms": omc_slash_raw.most_common(30),  # 실제 입력한 슬래시 원형
            "keyword_forms": omc_kw_raw.most_common(),     # 자연어 프롬프트 안의 매직 키워드 원형
            "prompts_with_omc": omc_prompts, "prompts_total": tot,
            "omc_ratio": round(omc_prompts / tot, 3) if tot else 0,                 # 전체 프롬프트 중 OMC 명령이 들어간 비중
            "slash_omc": omc_slash_n, "slash_total": n_slash_all,
            "slash_omc_ratio": round(omc_slash_n / n_slash_all, 3) if n_slash_all else 0,
            "natural_with_keyword": omc_nat_n, "natural_total": len(lens),
            "keyword_ratio": round(omc_nat_n / len(lens), 3) if lens else 0,
            "by_month": sorted(omc_month.items())}

# ── 6. 말투 · 업무 성향 신호 (history.jsonl 자연어 프롬프트 대상) ─────────────
HANGUL = re.compile(r"[가-힣]")
WORD = re.compile(r"[가-힣]{2,}")
ENG = re.compile(r"[A-Za-z]{3,}")
SENT_SPLIT = re.compile(r"[.!?\n]+|(?<=다)\s+(?=그리고|그런데|근데|또)")
STOP = {"그리고", "그래서", "그런데", "하지만", "이렇게", "그렇게", "저렇게", "때문에",
        "있는", "없는", "하는", "되는", "같은", "위해", "대해", "이거", "그거", "저거",
        "여기", "거기", "우리", "에서", "으로", "에게", "한테", "부터", "까지", "보다",
        "이나", "라도", "든지", "처럼", "만큼", "대로", "하고", "이랑"}
JOSA = re.compile(r"(으로써|으로서|에서는|에게서|으로|에서|에게|한테|부터|까지|보다|"
                  r"이나|라도|든지|처럼|만큼|대로|이랑|와의|과의|은|는|이|가|을|를|에|의|도|만|와|과|랑)$")


def normalize(w):
    """조사를 떼어 어휘 지문을 명사 중심으로 만든다 (3자 이상일 때만)."""
    if len(w) >= 3:
        c = JOSA.sub("", w)
        if len(c) >= 2:
            return c
    return w

MARKERS = {
    "강조·단정": r"반드시|절대|무조건|꼭 |전부|모두|싹 |한번에",
    "완곡·탐색": r"혹시|일단|우선|아마|같아|것 ?같|어때|괜찮|어떨까|해볼까",
    "불만·교정": r"아니 |아직|왜 |틀렸|잘못|안 ?되|안돼|이상해|다시 |또 |여전히",
    "칭찬·수용": r"좋아|좋네|굿|완벽|맞아|오케이|오키|고마워|감사|훌륭",
    "속도·긴급": r"빨리|급해|지금 ?바로|당장|서둘",
    "위임·자율": r"알아서|네가 |니가 |판단해|자유롭게|맡길|편한대로|적당히",
    "검증요구": r"확인|검증|테스트|체크|점검|맞는지|제대로|정말",
    "범위한정": r"이것만|여기만|일부만|그것만|우선순위|나머지는|먼저|우선 ",
    "사과·완충": r"미안|죄송|부탁|혹시 몰라|참고로",
    "설명요구": r"설명|왜 그런|이유|근거|알려줘|가르쳐",
}
LAUGH = re.compile(r"[ㅋㅎ]{2,}|[ㅠㅜ]{2,}")
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")

sp_end_word, sp_end_tail, sp_first, sp_vocab = C(), C(), C(), C()
sp_marker = {k: 0 for k in MARKERS}
sp_pol = {"존댓말": 0, "반말": 0, "중립·체언종결": 0}
sp_punct = {"물음표": 0, "느낌표": 0, "마침표": 0, "말줄임": 0, "문장부호_없음": 0}
sp_sent_counts, sp_gaps, sp_short_follow, sp_pairs = [], [], 0, 0
sp_laugh = sp_emoji = sp_eng_mixed = 0
sp_texts = []
POLITE = re.compile(r"(요|니다|세요|십시오|시죠|셔요|까요|시오)$")
BANMAL = re.compile(r"(줘|봐|해|자|라|야|어|지|네|군|까|래|니|걸|데|아|고|음|셈)$")


def politeness_of(sents):
    """마지막 문장의 종결 토큰으로 판정. 체언 종결은 별도 분류."""
    for sent in reversed(sents):
        toks = sent.split()
        if not toks:
            continue
        last = toks[-1].strip("\"'`)]},.…~! ")
        if not HANGUL.search(last):
            continue
        if POLITE.search(last):
            return "존댓말"
        if BANMAL.search(last):
            return "반말"
        return "중립·체언종결"
    return "중립·체언종결"

prev_by_session = {}
for line in (hist.read_text(encoding="utf-8", errors="replace").splitlines() if hist.exists() else []):
    try:
        d = json.loads(line)
    except Exception:
        continue
    txt = (d.get("display") or "").strip()
    if not txt or txt.startswith("/") or not HANGUL.search(txt):
        continue
    sp_texts.append(txt)
    # 세션 내 프롬프트 간격 / 짧은 후속 지시
    sid, tms = d.get("sessionId"), d.get("timestamp")
    if sid and tms:
        prev = prev_by_session.get(sid)
        if prev is not None:
            gap = (tms - prev) / 1000.0
            if 0 < gap < 3600:
                sp_gaps.append(gap)
                sp_pairs += 1
                if len(txt) <= 20:
                    sp_short_follow += 1
        prev_by_session[sid] = tms
    # 문장 단위
    sents = [x.strip() for x in SENT_SPLIT.split(txt) if x.strip()]
    sp_sent_counts.append(max(1, len(sents)))
    for sent in sents:
        toks = sent.split()
        if not toks:
            continue
        last = toks[-1].strip("\"'`)]},.…~ ")
        if HANGUL.search(last):
            sp_end_word[last[-6:]] += 1
            sp_end_tail[last[-2:]] += 1
    sp_pol[politeness_of(sents)] += 1
    # 문장부호
    sp_punct["물음표"] += txt.count("?")
    sp_punct["느낌표"] += txt.count("!")
    sp_punct["마침표"] += txt.count(".")
    sp_punct["말줄임"] += txt.count("...") + txt.count("…")
    if not re.search(r"[.!?]$", txt):
        sp_punct["문장부호_없음"] += 1
    # 첫 단어 / 어휘
    ft = txt.split()
    if ft and HANGUL.search(ft[0]):
        sp_first[ft[0].strip("\"'`,.")] += 1
    for w in WORD.findall(txt):
        w = normalize(w)
        if w not in STOP and 2 <= len(w) <= 8:
            sp_vocab[w] += 1
    # 마커
    for k, pat in MARKERS.items():
        sp_marker[k] += len(re.findall(pat, txt))
    if LAUGH.search(txt):
        sp_laugh += 1
    if EMOJI.search(txt):
        sp_emoji += 1
    if ENG.search(txt):
        sp_eng_mixed += 1

sp_gaps.sort()
gq = lambda r: round(sp_gaps[min(len(sp_gaps) - 1, int(len(sp_gaps) * r))], 1) if sp_gaps else 0
n_sp = len(sp_texts) or 1
by_len = sorted(sp_texts, key=len)
O["speech"] = {
    "sample_size": len(sp_texts),
    "politeness": sp_pol,
    "endings_top": sp_end_word.most_common(30),
    "ending_tails_top": sp_end_tail.most_common(20),
    "first_words_top": sp_first.most_common(25),
    "vocab_top": sp_vocab.most_common(40),
    "markers": dict(sorted(sp_marker.items(), key=lambda x: -x[1])),
    "markers_per_100": {k: round(v * 100 / n_sp, 1) for k, v in
                        sorted(sp_marker.items(), key=lambda x: -x[1])},
    "punctuation": sp_punct,
    "sentences_per_prompt": {
        "avg": round(sum(sp_sent_counts) / len(sp_sent_counts), 2) if sp_sent_counts else 0,
        "one_sentence_ratio": round(sum(1 for x in sp_sent_counts if x == 1) / len(sp_sent_counts), 3)
                              if sp_sent_counts else 0},
    "inter_prompt_gap_sec": {"median": gq(.5), "p25": gq(.25), "p90": gq(.9), "pairs": sp_pairs},
    "short_followup_ratio": round(sp_short_follow / sp_pairs, 3) if sp_pairs else 0,
    "laugh_prompts": sp_laugh, "emoji_prompts": sp_emoji,
    "english_mixed_prompts": sp_eng_mixed,
    "english_mixed_ratio": round(sp_eng_mixed / n_sp, 3),
    "samples_shortest": by_len[:8],
    "samples_longest": [t[:300] for t in by_len[-4:]],
    "samples_spread": [by_len[int(len(by_len) * r)][:220]
                       for r in (.2, .35, .5, .65, .8)] if len(by_len) > 5 else [],
}

# ── 5. 커스터마이징 자산 ──────────────────────────────────────────────────────
st_json = jload(CC / "settings.json", {}) or {}
O["customization"] = {
    "global_CLAUDE_md_bytes": (CC / "CLAUDE.md").stat().st_size if (CC / "CLAUDE.md").exists() else 0,
    "rules_files": names(CC / "rules", "*.md"), "global_agents": names(CC / "agents", "*.md"),
    "global_commands": names(CC / "commands"), "global_skills": names(CC / "skills"),
    "installed_marketplaces": names(CC / "plugins" / "marketplaces"),
    "settings_keys": sorted(st_json.keys()), "hooks": sorted((st_json.get("hooks") or {}).keys()),
    "permissions_allow_count": len(((st_json.get("permissions") or {}).get("allow")) or []),
    "statusLine": bool(st_json.get("statusLine")), "model_default": st_json.get("model"),
    "env_keys": sorted((st_json.get("env") or {}).keys())}
assets = []
for path in (cfg.get("projects") or {}):
    d0 = Path(path)
    if not d0.exists():
        continue
    it = {"path": path,
          "CLAUDE_md": (d0 / "CLAUDE.md").stat().st_size if (d0 / "CLAUDE.md").exists() else 0,
          "agents": names(d0 / ".claude" / "agents", "*.md"),
          "commands": names(d0 / ".claude" / "commands"),
          "skills": names(d0 / ".claude" / "skills"),
          "settings": (d0 / ".claude" / "settings.json").exists(),
          "mcp_json": (d0 / ".mcp.json").exists()}
    if any((it["CLAUDE_md"], it["agents"], it["commands"], it["skills"], it["settings"], it["mcp_json"])):
        assets.append(it)
O["project_assets"] = assets

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "cc_usage_stats.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(O, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(f"OK -> {out}  ({out.stat().st_size:,} bytes)")
print(json.dumps(O["totals"], ensure_ascii=False))
print(json.dumps(O["session_stats_longwindow"], ensure_ascii=False)[:400])
print("speech sample:", O["speech"]["sample_size"], "| 존대/반말:", O["speech"]["politeness"])
print("omc:", O["omc"]["prompts_with_omc"], "/", O["omc"]["prompts_total"], "=", O["omc"]["omc_ratio"], "|", O["omc"]["commands"][:5])
