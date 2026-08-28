# 요약 JSON 스키마 (`data/{파트}_{이름}_{YYYYMMDD}.json`)

보고서(`.md`)와 **같은 이름**으로 저장하는 **기계가 읽는 요약본**이다.
개인 시각화 페이지(`.html`)와 GitHub Pages 통합 대시보드는 **이 JSON만** 읽는다. `.md` 는 파싱하지 않는다.

- 만드는 사람: `진단` 절차 7단계에서 Claude 가 `.md` 를 쓴 직후 같은 수치로 채운다
- 읽는 것: `scripts/build_site.py` (개인 `.html` 렌더 + `index.html` 대시보드 생성)
- **모든 수치는 `.md` 보고서와 동일해야 한다.** JSON 만 따로 계산하지 않는다 — `.md` 에 적은 값을 그대로 옮긴다

---

## 절대 넣지 말 것

이 파일은 **커밋되고 GitHub Pages 로 공개**된다. `.md` 보다 노출 범위가 넓다.

| 금지 | 이유 |
|---|---|
| **프롬프트 원문** (`samples_*`, `first_prompt`, 5-7절 표본) | 원문은 `.md` 5-7절까지만. JSON 에는 **한 줄도** 넣지 않는다 |
| API 키·토큰·이메일·전화번호·고객사 실명 | `.md` 와 같은 마스킹 규칙 ([PRIVACY](PRIVACY.md)) |
| 성별 예상 | 9장의 성별 항목은 `.md` 에만 둔다. 대시보드는 회람 범위가 넓어 **JSON 스키마에 아예 없다** |
| 비용(`lastCost`) | 누적 비용이 아니다 ([DATA_SOURCES](DATA_SOURCES.md)) |

`build_site.py` 는 `samples_shortest` `samples_longest` `samples_spread` `first_prompt` `gender` 키가 있으면 **빌드를 거부**한다.

---

## 파일명 규칙

```
data/{파트}_{이름}_{YYYYMMDD}.md     ← 보고서 (사람이 읽음)
data/{파트}_{이름}_{YYYYMMDD}.json   ← 요약 (대시보드가 읽음)
data/{파트}_{이름}_{YYYYMMDD}.html   ← 개인 시각화 (build_site.py 가 json 으로부터 렌더)
```

- 세 파일의 **stem(확장자 앞부분)은 완전히 같아야** 한다
- 파트·이름에 **공백을 넣지 않는다** (공백은 하이픈 `-` 으로). 언더스코어 `_` 는 구분자이므로 파트·이름 안에 쓰지 않는다
- 같은 사람이 다시 뽑으면 날짜가 다른 새 파일로 남긴다. 대시보드는 **(파트, 이름) 별 최신 날짜 1건**을 대표로 쓰고 나머지는 이력으로 표시한다

---

## 스키마 (v1)

`schema_version` 은 `1` 고정. 값이 없는 항목은 키를 지우지 말고 `null` / `[]` / `0` 으로 둔다 (절 삭제 금지 규칙과 같은 이유 — 취합 시 열이 밀린다).

```jsonc
{
  "schema_version": 1,
  "part": "영업1파트",                 // 파일명의 {파트} 와 동일
  "name": "홍길동",                    // 파일명의 {이름} 과 동일
  "date": "2026-08-28",                // 작성일 (YYYY-MM-DD). 파일명의 {YYYYMMDD} 와 동일
  "role": "B2B 영업 지원 시스템 백엔드", // 0단계에서 받은 "주 담당 업무 (한 줄)"
  "highlight": "없음",                  // 0단계에서 받은 "특별히 강조하고 싶은 것"
  "env": { "claude_code": "2.1.180", "os": "Darwin 25.4.0", "python": "3.12.3" },

  // ── 0장 집계 개요 ──
  "coverage": {
    "history":       { "from": "2026-03-02", "to": "2026-08-28" },   // ~/.claude/history.jsonl
    "session_stats": { "from": "2026-03-02", "to": "2026-08-28" },   // ~/.claude/.session-stats.json
    "transcripts":   { "from": "2026-07-29", "to": "2026-08-28" },   // ~/.claude/projects/**.jsonl (약 30일)
    "speech_sample_size": 412,
    "failed_items": []                                               // 수집 실패 항목. 없으면 []
  },

  // ── 1장 한 줄 요약 ──
  "summary": {
    "one_liner": "Claude Code 를 백엔드 리팩터링 용도로, 위임형 방식으로, 주로 crm-api 에서 쓴다",
    "habit":  "가장 특징적인 습관 1가지",
    "effect": "가장 큰 효과 1가지",
    "pain":   "가장 큰 불편 1가지"
  },

  // ── 2장 사용 규모 ── (구간 표기: long = 수개월, 30d = 트랜스크립트 약 30일)
  "scale": {
    "sessions_long": 312,            // session_stats_longwindow.sessions
    "active_months": 6,              // sessions_by_month 길이
    "tool_calls_long": 18420,        // session_stats_longwindow.total_tool_calls
    "natural_prompts": 1834,         // prompts.natural_prompt_count
    "slash_prompts": 402,            // prompts.slash_top 합계
    "subagent_msgs_30d": 1210,       // totals.subagent_msgs
    "tok_out_30d": 2450000,          // totals.tok_out
    "thinking_tok_30d": 830000,      // totals.thinking_tok
    "tok_cache_read_30d": 98000000,  // totals.tok_cache_read
    "sessions_by_month": [["2026-03", 40], ["2026-04", 52]],   // session_stats_longwindow.sessions_by_month
    "prompts_by_month":  [["2026-03", 210], ["2026-04", 380]], // prompts.by_month
    "by_hour": [0,0,0,0,0,0,1,4,12,30,45,40,20,38,50,44,30,18,9,6,4,3,1,0],  // prompts.by_hour (길이 24)
    "by_dow":  [["Mon", 320], ["Tue", 350], ["Wed", 300], ["Thu", 310], ["Fri", 280], ["Sat", 40], ["Sun", 20]],
    "rhythm_note": "오전 10~11시와 오후 2~3시 두 봉우리. 주말 사용 거의 없음"   // 2장 마지막 1~2줄
  },

  // ── 3장 프로젝트별 ── (직접 프롬프트 많은 순 상위 최대 10개)
  "projects_top": [
    { "project": "crm-api", "sessions": 120, "active_days": 48, "human_turns": 640,
      "tool_calls": 7200, "main_model": "claude-opus-4-1", "period": "2026-07-29 ~ 2026-08-28" }
  ],
  "projects_other_count": 7,         // "그 외 N개"

  // ── 4장 워크플로 ──
  "workflow": {
    "automation_depth": 11.4,                          // tool_calls / human_turns (소수 1자리)
    "tools_top": [["Bash", 6100], ["Read", 4200]],     // Top 10
    "omc": {                                           // OMC(oh-my-claudecode) 명령어 사용 — cc_usage_stats.json 의 omc 블록
      "commands": [["autopilot", 240], ["ultrawork", 118], ["ralph", 64]],  // 정규화 이름, 슬래시+키워드 합산, 전부
      "distinct_commands": 9,
      "prompts_with_omc": 611, "prompts_total": 1958,
      "omc_ratio": 0.312,          // 전체 프롬프트 중 OMC 명령이 들어간 비중 ← 4장 "OMC 명령어 사용 비중"
      "slash_omc_ratio": 0.41,     // 슬래시 커맨드 중 OMC 비중
      "keyword_ratio": 0.263,      // 자연어 프롬프트 중 매직 키워드(ulw, ralph …) 포함 비중
      "keyword_forms": [["ulw", 96], ["ralph", 61]],
      "by_month": [["2026-03", 88], ["2026-04", 103]]
    },
    "subagent_types": [["Explore", 34], ["executor", 12]],
    "subagent_msg_ratio": 0.21,                        // subagent_msgs / (assistant_msgs + subagent_msgs)
    "models": [["claude-opus-4-1", 0.72], ["claude-sonnet-4-5", 0.28]],  // 비중(0~1)
    "effort": [["high", 0.8], ["medium", 0.2]],        // 없으면 []
    "permission_mode": [["acceptEdits", 0.9]],         // 없으면 []
    "mcp_servers": [["context7", 40]],                 // 실제 호출된 것만
    "skills": [["plan", 12], ["review", 8]],
    "style_note": "수치로부터 작업 방식 3~5줄을 한 문단으로"
  },

  // ── 5장 말투 ──
  "speech": {
    "politeness": { "formal": 0.12, "casual": 0.71, "noun": 0.17 },  // 존댓말/반말/체언종결 비율 (합 1.0)
    "endings_top":     [["해줘", 339], ["말야", 41]],   // Top 5
    "first_words_top": [["이어서", 24], ["일단", 19]],  // Top 5
    "vocab_top":       [["테스트", 88], ["커밋", 71]],  // Top 10
    "markers_per_100": { "불만·교정": 19.5, "완곡·탐색": 8.2, "검증요구": 14.1, "강조·단정": 5.0,
                         "칭찬·수용": 3.3, "위임·자율": 6.8, "속도·긴급": 0.9, "범위한정": 4.4,
                         "설명요구": 7.7, "사과·완충": 1.2 },   // 10종 전부. 마커 이름은 SPEECH_ANALYSIS.md 와 동일
    "len_chars": { "median": 34, "p90": 142, "max": 2210 },
    "sentences_per_prompt": 1.8,
    "gap_sec": { "median": 95, "p25": 30, "p90": 640 },
    "short_followup_ratio": 0.23,
    "laugh_prompts": 14, "emoji_prompts": 3,
    "korean_prompts": 1700, "non_korean_prompts": 134, "english_mixed_ratio": 0.41,
    "punctuation": { "question": 120, "exclaim": 8, "none_ratio": 0.62 },
    "style_summary":      ["5-5 말투 3줄 요약 1", "2", "3"],
    "reproduced_prompts": ["5-6 가상 프롬프트 1", "2", "3"]   // 실제 쓴 적 없는 문장만. 표본 복사 금지
  },

  // ── 6장 자산 ──
  "assets": {
    "counts": { "global_claude_md": 1, "rules": 3, "agents": 0, "commands": 2, "skills": 4, "hooks": 2,
                "permissions_allow": 30, "statusline": true, "mcp_servers": 5, "plugins": 2, "project_claude_md": 7 },
    "share_worthy": [ { "asset": "rules/context7.md", "reason": "SDK 문서 조회 규칙. 파트 공통으로 쓸 만함" } ]
  },

  // ── 7장 대표 사례 (3~5건) ── 프롬프트 원문 금지. 요약만
  "cases": [
    { "title": "결제 모듈 리팩터링", "project": "crm-api", "when": "2026-08-12",
      "task": "시킨 일 요약", "how": "툴·에이전트·모델", "human_turns": 9, "tool_calls": 212,
      "outcome": "변경 파일 14개 · feat/payment-v2", "saving": "약 4시간 → 40분 (근거)" }
  ],

  // ── 8장 성향 프로파일 ── 1~5 정수. 방향은 아래 표 참고
  "profile": {
    "axes": { "delegation": 4, "verification": 3, "planning": 2, "perfectionism": 4, "exploration": 3 },
    "axes_evidence": { "delegation": "위임·자율 6.8/100, 서브에이전트 비중 21%", "verification": "...",
                       "planning": "...", "perfectionism": "...", "exploration": "..." },
    "rhythm": "작업 리듬 서술", "interest": "관심 영역 서술",
    "definition": "이 사람은 큰 단위로 맡기고 결과를 테스트로 검증하는 개발자다",
    "teammate_tips": ["동료가 알아두면 좋은 것 1", "2", "3"]
  },

  // ── 9장 재미 코너 ── 본인이 9장을 지웠으면 이 블록 전체를 null 로
  "fun": {
    "mbti":       { "value": "INTJ",       "strength": "약함",       "basis": "E/I·S/N·T/F·J/P 축별 근거 한 줄" },
    "age_band":   { "value": "30대 초반",  "strength": "약함",       "basis": "ㅋㅋ 14건 · 존댓말 12% · 야간 3%" },
    "blood_type": { "value": "B형",        "strength": "없음(무작위)", "basis": "데이터 신호 0. 억지 논리 한 줄" },
    "nickname": "한 줄 별명 (호의적으로)",
    "pair_programming": "이 사람과 페어 프로그래밍 한다면 2~3줄"
  },

  // ── 9장 AI 사용 전문가 지수 ── `--scaffold` 가 산식으로 계산한다. **손으로 고치지 않는다.** fun 이 null 이어도 이 블록은 남긴다
  "expert_index": {
    "formula_version": 1,
    "score": 71,                          // 0~100 정수 (아래 산식으로 계산: 20.0+5.7+12.0+13.3+20.0 = 71.0)
    "level": "전문가", "emoji": "🧠",
    "breakdown": { "volume": 20.0, "automation": 5.7, "delegation": 12.0, "assets": 13.3, "omc": 20.0 },  // 각 0~20
    "inputs": { "sessions_long": 312, "automation_depth": 11.4, "subagent_msg_ratio": 0.21,
                "asset_points": 8, "omc_ratio": 0.312, "distinct_commands": 9 }
  },

  // ── 10장 ──
  "feedback": {
    "works_well":   ["효과가 확실한 작업 유형 1", "2", "3"],
    "works_poorly": ["잘 안 되는 작업 유형 1", "2", "3"],
    "blockers":     ["막혔던 지점 / 반복 실패 패턴"],
    "proposals":    ["파트 차원 제안 1", "2"]
  },

  // ── 11장 ──
  "script_commit": "a1b2c3d"          // 집계 스크립트 버전 (git rev-parse --short HEAD)
}
```

### `profile.axes` 방향

| 키 | 1점 | 5점 | 근거 |
|---|---|---|---|
| `delegation` | 통제형 | 위임형 | 위임·자율 마커, 서브에이전트 비중, permission mode |
| `verification` | 결과를 그대로 믿음 | 검증 집착 | 검증요구 마커, Bash 중 테스트/린트 비중 |
| `planning` | 즉흥형 | 계획형 | plan 계열 스킬·plan mode 사용 |
| `perfectionism` | 한 번에 수용 | 완성도 집착 | 불만·교정 마커, 짧은 후속 지시 비율 |
| `exploration` | 단정형 | 탐색형 | 완곡·탐색 vs 강조·단정 마커 비율 |

### `expert_index` 산식 (v1) — 재미용, 근거 강도 **중간(산식 공개)**

5축 × 20점 = 100점. `clamp(x)` 는 0~1 로 자른다. 축마다 "이 정도면 만점" 기준을 명시해 사람 간 비교가 되게 한다.

| 축 | 키 | 산식 | 만점 기준 |
|---|---|---|---|
| 규모 | `volume` | `20 × clamp(log10(1 + sessions_long) / log10(301))` | 장기 세션 300개 |
| 자동화 | `automation` | `20 × clamp(automation_depth / 40)` | 한 지시당 도구 40회 (서브에이전트 도구 호출이 포함되므로 기준을 높게 잡는다) |
| 위임 | `delegation` | `20 × clamp(subagent_msg_ratio / 0.35)` | 서브에이전트 메시지 비중 35% |
| 자산 | `assets` | `20 × clamp(asset_points / 12)` | 아래 점수 12점 |
| OMC 활용 | `omc` | `20 × clamp(0.5 × omc_ratio / 0.25 + 0.5 × distinct_commands / 6)` | 비중 25% 이고 6종 사용 |

`asset_points = (global_claude_md > 0) × 2 + min(rules, 3) + min(agents, 2) + min(commands, 2) + min(skills, 2) + min(hooks, 2) + min(mcp_servers, 2) + min(project_claude_md, 3)` (최대 18)

`score = round(다섯 축 합)`. 레벨: 0~19 🌱 입문 · 20~39 🔧 견습 · 40~59 ⚙️ 숙련 · 60~79 🧠 전문가 · 80~100 🚀 마스터.

- 9장(재미 코너)에 한 행으로 넣고, 대시보드는 이 값으로 "전문가 지수 순위" 를 그린다 — **재미용**임을 항상 함께 표기한다
- 산식을 바꾸면 `formula_version` 을 올리고 이 표를 갱신한다. 버전이 다른 보고서끼리는 점수를 비교하지 않는다

---

## 검증

`build_site.py` 는 빌드 전에 다음을 확인하고, 어긋나면 **해당 파일을 건너뛰고 이유를 출력**한다 (다른 사람 파일까지 막지 않는다).

- `schema_version == 1`
- `part` `name` `date` 가 파일명과 일치
- 금지 키(`samples_*`, `first_prompt`, `gender`) 없음
- `scale.by_hour` 길이 24, `profile.axes` 5개 키 모두 1~5 정수
- `speech.markers_per_100` 에 10종 마커 전부 존재
- `workflow.omc` 에 `commands` `omc_ratio` `prompts_with_omc` `prompts_total` 존재
- `expert_index.score` 가 0~100 정수이고 `breakdown` 에 5축 키 전부 존재

로컬에서 미리 확인:

```bash
python3 scripts/build_site.py --check data/영업1파트_홍길동_20260828.json
```

---

## 스캐폴드와 검증 명령

`scripts/build_site.py` 하나가 **뼈대 생성 · 검증 · 개인 페이지 렌더 · 대시보드 빌드**를 모두 한다.
Python 3.9+ 표준 라이브러리만 쓰고, 만들어지는 HTML 은 외부 CDN 없이 자기완결적이라 `file://` 로 열어도 그대로 보인다.

```bash
# ① 뼈대 만들기 — 수치는 자동, 서술은 빈칸
python3 scripts/build_site.py --scaffold cc_usage_stats.json \
    --part 영업1파트 --name 홍길동 --date 2026-08-28 \
    --role "B2B 영업 지원 시스템 백엔드" --highlight "없음"

# ② 다 채웠는지 확인 (통과 0 / 실패 1)
python3 scripts/build_site.py --check data/영업1파트_홍길동_20260828.json

# ③ 개인 페이지 렌더 (같은 위치에 .html)
python3 scripts/build_site.py --person data/영업1파트_홍길동_20260828.json

# ④ 통합 대시보드 빌드 (GitHub Actions 가 하는 일)
python3 scripts/build_site.py --out _site --repo-url https://github.com/owner/repo

# ⑤ 가짜 데이터로 미리보기
python3 scripts/build_site.py --out _site --demo
```

- `--scaffold` 는 파일이 이미 있으면 **덮어쓰지 않고 exit 1** 한다. 다시 뽑으려면 `--force`.
- 파트·이름에 `_` 나 공백이 있으면 `--scaffold` 가 거부한다 (파일명 구분자가 깨진다).
- `--out` 은 검증에 걸린 파일만 **건너뛰고 exit 0** 한다. 한 사람이 틀려도 나머지 페이지는 나온다.
- `--repo-url` 을 주면 `.md` 링크가 `{repo-url}/blob/main/data/{stem}.md` 로, 없으면 상대경로로 걸린다.

### `--scaffold` 가 자동으로 채우는 것

`cc_usage_stats.json` → 요약 JSON 매핑이다. **여기 있는 값은 손으로 고치지 않는다** (`.md` 와 어긋난다).

| 요약 JSON | 출처 (`cc_usage_stats.json`) |
|---|---|
| `scale.sessions_long` · `tool_calls_long` · `sessions_by_month` | `session_stats_longwindow.sessions` · `.total_tool_calls` · `.sessions_by_month` |
| `scale.active_months` | `session_stats_longwindow.sessions_by_month` 의 길이 |
| `scale.natural_prompts` · `prompts_by_month` · `by_hour` · `by_dow` | `prompts.*` (`by_dow` 는 월~일 7일로 채워 정렬) |
| `scale.slash_prompts` | `prompts.slash_top` 합계 |
| `scale.subagent_msgs_30d` · `tok_out_30d` · `thinking_tok_30d` · `tok_cache_read_30d` | `totals.*` |
| `projects_top` | `projects` 를 `human_turns` 내림차순으로 상위 10개 |
| `workflow.automation_depth` | `totals.tool_calls / totals.human_turns` (소수 1자리) |
| `workflow.subagent_msg_ratio` | `totals.subagent_msgs / (assistant_msgs + subagent_msgs)` |
| `workflow.tools_top` · `subagent_types` · `mcp_servers` | `tools_all` · `subagent_types` · `mcp_servers_called` 상위 10 |
| `workflow.omc` | `omc` 블록 그대로 (`commands` 전부, 비율은 소수 3자리) |
| `workflow.skills` | `skillUsage` (`~/.claude.json` **누적** 호출 수) 상위 10 |
| `speech.*` | `speech.*` · `prompts.len_chars` · `prompts.korean_prompts` |
| `assets.counts` | `customization` · `project_assets` · `global.mcpServers_global` |
| `expert_index` | 위 산식으로 계산 |
| `env` | `claude --version` · `platform.system()/release()` · `platform.python_version()` |
| `script_commit` | `git rev-parse --short HEAD` |

**주의할 근사·정규화 3가지**

1. `projects_top[].tool_calls` 는 **상위 도구 합계 근사**다. `projects` 행에 도구 호출 총합이 없어
   `top_tools`(상위 6개) 를 더한 값이라 **실제보다 작다**. 프로젝트 간 비교용으로만 읽는다.
2. `workflow.models` · `effort` · `permission_mode` 는 원본이 카운트라 **비중(0~1, 소수 2자리)으로 정규화**한다.
   반올림 오차는 가장 큰 항목에서 보정해 합이 1.0 이 된다. `--check` 는 이 세 항목의 값이 0~1 밖이면 실패시킨다.
3. `projects_top[].project` 는 `-Users-{사람}-WebstormProjects-crm-api` 같은 인코딩된 경로에서
   홈·상위 디렉터리를 떼어낸 **추정 이름**이다 (`crm-api`). 틀렸으면 손으로 고쳐도 된다.

**자동으로 못 채우는 것** — 스캐폴드가 `""` / `[]` / `null` 로 두고 실행 끝에 목록을 출력한다.

- `summary.*` · `scale.rhythm_note` · `workflow.style_note` · `speech.style_summary` ·
  `speech.reproduced_prompts` · `assets.share_worthy` · `cases` · `profile.*` · `fun` · `feedback.*`
- `coverage.history` — `history.jsonl` 의 실제 시작·종료일은 집계 결과에 없다. `null` 로 두거나 직접 적는다
- `env` · `script_commit` 은 수집에 실패하면 `""` 로 둔다 (`claude` 명령이 PATH 에 없거나 커밋이 없는 경우)

### `--check` 가 보는 것

**실패(exit 1)** — 위 "검증" 절 항목 전부에 더해:

- 금지 키(`samples_shortest` `samples_longest` `samples_spread` `first_prompt` `gender`)가
  **중첩 어디에 있어도** 실패한다
- 서술 필수 필드가 비어 있으면 실패한다 —
  `summary.one_liner` · `speech.style_summary` 3개 · `speech.reproduced_prompts` 3개 ·
  `profile.definition` · `profile.axes` 5축 · `cases` 3건 이상 ·
  `feedback.works_well` / `works_poorly` / `blockers` / `proposals` 각 1개 이상
- `workflow.omc.prompts_with_omc` 가 `prompts_total` 보다 큰 경우
- `expert_index.score` 가 0~100 정수가 아니거나 `breakdown` 에 5축이 없는 경우

**경고(그래도 통과)** — 고치는 편이 좋지만 빌드를 막지는 않는다:

- 문자열이 **500자를 넘음** (프롬프트 원문이 섞여 들어왔을 가능성)
- `summary.habit/effect/pain` · `scale.rhythm_note` · `workflow.style_note` · `profile.axes_evidence` 가 빔
- `speech.politeness` 세 값의 합이 1.0 에서 0.05 이상 벗어남
- `expert_index.breakdown` 합계와 `score` 가 1점 넘게 다름 (손으로 고친 흔적)
- `fun` 이 `null` 이 아닌데 값이 비어 있음 — 이때 개인 페이지는 **재미 코너 섹션 자체를 생략**한다

`fun` 은 `null` 이어도 통과한다. `expert_index` 는 `fun` 이 `null` 이어도 남긴다.

### 개인 페이지가 JSON 을 어떻게 쓰는지

- `coverage.speech_sample_size` 가 **100 미만이면** 말투 절에 "해석 주의" 배지가 붙는다
- `fun.nickname` 이 있으면 히어로 이름 옆에 별명이 붙는다
- `speech.reproduced_prompts` 는 채팅 말풍선으로 그리고 **"가상 프롬프트 · 실제 발화 아님"** 배지를 항상 함께 단다
- KPI 타일마다 **장기 / 최근 30일** 구간 라벨이 붙는다 — 이 저장소에서 구간 혼용은 가장 흔한 오독이다
- `workflow.omc` 는 4장에서 **`omc_ratio` 를 큰 숫자로** 띄우고, 보조로 `slash_omc_ratio` ·
  `keyword_ratio` 를 칩으로, `commands` 는 **전부** 가로막대로, `keyword_forms` 는 칩으로,
  `by_month` 는 도입 추이 소형 막대로 그린다 (`slash_forms` 는 스키마에 없어 쓰지 않는다)
- `expert_index` 는 **재미 코너 앞의 독립 절**로 그린다. `fun` 이 `null` 이어도 이 절은 남는다

### 대시보드가 JSON 을 어떻게 쓰는지

- (파트, 이름) 별 **최신 날짜 1건**이 멤버 카드가 되고 나머지는 "이력" 절에 링크로 남는다
- `expert_index` 로 **"AI 사용 전문가 지수 순위"** 절을 그린다 — 점수 내림차순 가로막대,
  레벨 배지, `breakdown` 5축 미니 스택 바. **재미용** 고지를 항상 함께 단다
- 비교 가로막대: 세션 수 · 도구 호출 · 직접 프롬프트 · 자동화 심도 · 프롬프트 길이 중앙값 ·
  짧은 후속 지시 비율 · **OMC 명령 사용 비중** · 서브에이전트 메시지 비중
- 파트 합산: 도구 Top 10 · **OMC 명령 Top 10** · 모델 비중. `bash_*` 는 어디에도 쓰지 않는다

### 테스트와 미리보기 데이터

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'
```

`scripts/fixtures/` 는 **명백히 가짜인** 미리보기·테스트 데이터다 (`샘플파트` / `샘플2파트`, `샘플-가` `샘플-나` `샘플-다`).
실제 사람 데이터나 프롬프트 원문은 절대 넣지 않는다.

- `샘플파트_샘플-가_20260828.json` 과 `샘플파트_샘플-가_20260701.json` — 같은 사람의 두 회차 (이력 표시 확인용)
- `샘플파트_샘플-나_20260828.json` — `fun: null` (재미 코너 생략 확인용)
- `샘플2파트_샘플-다_20260827.json` — 표본 100건 미만 (해석 주의 배지 확인용)
- `샘플파트_샘플-오류_20260820.json` — **일부러 검증에 걸리게 만든 파일**.
  `--demo` 빌드에서 대시보드 하단 "빌드 노트" 가 어떻게 보이는지 보여준다.
  테스트는 이 파일을 `INVALID_FIXTURES` 로 따로 걸러낸다

테스트는 전부 `tempfile` 을 쓰고 `data/` 에는 아무것도 쓰지 않는다.
화법 마커 10종의 이름이 `scripts/cc_usage.py` 와 어긋나면 테스트가 깨진다 (`test_markers_match_cc_usage`).
