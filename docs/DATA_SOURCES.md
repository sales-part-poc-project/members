# 데이터 원본과 집계 구간

`scripts/cc_usage.py` 가 읽는 곳과, 각 수치를 해석할 때의 함정을 정리한다.

---

## 원본 4종

| 원본 | 집계 구간 | 무엇을 말해주나 |
|---|---|---|
| `~/.claude/history.jsonl` | **수개월 (가장 김)** | 프롬프트 원문. 말투·슬래시 커맨드·길이·시간대 패턴 |
| `~/.claude/.session-stats.json` | **수개월** | 세션 수, 도구 호출 총량, 월별 세션 추이 |
| `~/.claude/projects/**/*.jsonl` | **약 30일 (자동 삭제)** | 토큰·모델·effort, 서브에이전트, 프로젝트별 현황, 대표 사례 원문 |
| `~/.claude.json` | **누적** | 스킬·플러그인·MCP 사용 횟수, 등록 프로젝트, 커스터마이징 자산 |

**핵심**: 구간이 서로 다르다. 트랜스크립트만 보고 "이 사람은 최근에 별로 안 썼다" 고 결론 내면 틀린다.
30일이 지나면 삭제될 뿐, 안 쓴 게 아니다. 반드시 `session_stats_longwindow` 와 `prompts.by_month` 를 함께 본다.

보고서 **0장에 각 구간의 실제 시작~종료일을 표로** 적어야 한다.

---

## 출력 JSON 블록별 해설

### `totals` · `projects`

사용 규모와 주력 프로젝트. **트랜스크립트 구간(약 30일)** 기준이다.

- `human_turns` — 사람이 직접 친 프롬프트 수
- `slash_turns` — 슬래시 커맨드 (`/clear`, `/model` 등)
- `agent_turns` — 서브에이전트·팀이 주입한 턴
- `assistant_msgs` / `subagent_msgs` — 메인 루프 / 서브에이전트 응답 수
- `tok_*` — 입력·출력·캐시·사고 토큰

### `session_stats_longwindow`

**수개월 구간**의 세션 수와 도구 호출 총량. 트랜스크립트가 삭제돼도 남는다.
"이 사람이 얼마나 오래, 얼마나 자주 썼나" 는 여기서 본다.

### `prompts`

`history.jsonl` 기반. 슬래시 비중, 프롬프트 길이 분포(p10/중앙값/p90/최장), 한/영 비율,
월별·시간대별·요일별 분포, 프로젝트별 프롬프트 수.

### `speech`

말투 지문. 자세한 해설은 [SPEECH_ANALYSIS.md](SPEECH_ANALYSIS.md).

### `tools_all` · `bash_commands_top` · `subagent_types` · `mcp_servers_called` · `skills_from_transcripts`

실제 작업 방식. `bash_commands_top` 은 실행한 명령의 **첫 토큰**만 센다 (`git`, `grep`, `poetry`, `npm` …).

> `bash_commands_top` 은 **원시 참고용이고 보고서에는 쓰지 않는다.** 어떤 bash 명령을 몇 번 썼는지는
> 사람마다 스택이 달라 비교 가치가 낮다. 4장은 대신 아래 `omc` 블록을 쓴다.

### `omc`

OMC(oh-my-claudecode) 명령어 사용량. `~/.claude/history.jsonl` 기반이므로 **장기 구간**이다.

두 가지 형태를 **모두** 센다.

- **슬래시 형태** — `/autopilot`, `/oh-my-claudecode:team` …
- **자연어 프롬프트 안의 매직 키워드** — `ulw` `ralph` `autopilot` `ralplan` `ultrathink` `deepsearch`
  `deep-interview` `cancelomc` `deslop` `ultragoal` `autoresearch` `ultrapilot` `tdd`

`ulw` 는 `ultrawork` 로 정규화해 합산한다.
슬래시 커맨드 뒤 인자에 섞인 키워드(`/commit ulw 해줘` 의 `ulw`)도 키워드로 잡는다.
`commands` 는 **언급 횟수**라 한 프롬프트에 `/autopilot` 과 `ulw` 가 함께 있으면 두 명령에 각각 1씩 더해진다.
프롬프트 단위 비중은 `prompts_with_omc` / `omc_ratio` 로 본다.

| 필드 | 뜻 |
|---|---|
| `commands` | 정규화 이름으로 합산한 `[명령, 횟수]` 전부 (슬래시 + 키워드) |
| `distinct_commands` | 사용한 명령 종류 수 |
| `slash_forms` · `keyword_forms` | 형태별 내역 |
| `prompts_with_omc` · `prompts_total` | OMC 명령이 들어간 프롬프트 수 / 전체 프롬프트 수 |
| **`omc_ratio`** | **핵심 지표** — 전체 프롬프트 중 OMC 명령이 들어간 비중 |
| `slash_omc_ratio` | 슬래시 커맨드 중 OMC 비중 |
| `keyword_ratio` | 자연어 프롬프트 중 매직 키워드 포함 비중 |
| `by_month` | 월별 사용량 |

### `models_all` · `effort` · `permissionMode`

어떤 모델을 어느 강도/권한 모드로 쓰는지.

### `customization` · `project_assets` · `skillUsage` · `pluginUsage`

전역/프로젝트별 CLAUDE.md, 커스텀 에이전트·커맨드·스킬·훅, 설치한 플러그인과 MCP.

### `top_sessions`

대표 사례 후보 15개. 사람 발화 수 × 3 + 도구 호출 ÷ 10 순으로 정렬.
각 항목에 `first_prompt`(사람이 친 첫 실제 프롬프트), `files_touched`, `skills`, `subagents` 가 들어 있다.

---

## 수치 함정

### ① 비용으로 줄세우면 안 된다

`~/.claude.json` 의 `lastCost` / `lastModelUsage` 는 **프로젝트별 "마지막 세션" 값**이다.
누적 비용이 아니다. 스크립트도 이 값을 수집하지 않는다. **비용 대신 토큰 총량**으로 보고한다.

### ② 사람 발화 수를 합치면 부풀어 오른다

`~/.claude/projects/**.jsonl` 에서 `type: "user"` 인 줄에는 다음이 전부 섞여 들어온다.

- 사람이 실제로 친 프롬프트
- 슬래시 커맨드 부기 라인 (`<command-name>/clear</command-name>` 등)
- 로컬 커맨드 출력 (`<local-command-stdout>…`)
- 훅이 주입한 `<system-reminder>` 블록
- 서브에이전트/팀메이트 메시지 (`Another Claude session sent a message: <teammate-message …>`)

전부 합치면 한 세션이 **488턴**으로 잡혔지만, 분류 후 실제 사람 발화는 **12턴**이었다.
스크립트가 `human` / `slash` / `agent` / `noise` 로 나눠 세는 이유다.
**셋을 합쳐서 "내가 보낸 메시지"라고 쓰지 마라.**

### ③ 프로젝트 폴더 안에 하위 폴더가 있다

`~/.claude/projects/<프로젝트>/subagents/*.jsonl` 처럼 하위 디렉터리가 있어서,
`f.parent.name` 으로 프로젝트를 잡으면 `subagents` 가 프로젝트명이 된다.
스크립트는 `projects/` 루트 기준 **첫 경로 조각**을 쓴다.

### ④ 자동화 심도

`tool_calls / human_turns` 는 **"한 번 지시하면 몇 번의 도구 실행으로 이어지는가"** 를 뜻한다.
보고용으로 설명력이 가장 좋은 지표이므로 4장에 반드시 계산해서 넣는다.

### ⑤ REPORT 메모리·풀 통계류는 누적치

Claude Code 가 남기는 세션 메트릭은 warm 컨테이너 누적치인 경우가 있다.
단일 실행의 사용량으로 읽지 않는다.

### ⑥ `/plan` 만 친 건 OMC 로 안 잡힌다

Claude Code 기본 명령과 이름이 겹치는 것(`plan` `review` `verify` `research` `debug` `wiki`
`remember` `skill` `release` `hud` `setup`)은 **`/oh-my-claudecode:` 접두어가 있을 때만** OMC 로 인정한다.
접두어 없이 `/plan` 만 친 사용은 기본 명령과 구별할 수 없어 `omc` 블록에 들어가지 않는다.

그래서 **`omc_ratio` 는 실제 OMC 사용량의 하한선**이다. "이 사람은 OMC 를 안 쓴다" 는 결론을 이 수치만으로 내리지 않는다.

---

## 스크립트 수정 정책

`scripts/cc_usage.py` 는 **모두가 같은 로직으로 집계해야** 비교가 성립한다.

- 개인이 로컬에서 고치지 않는다
- 고칠 일이 생기면 저장소에 반영하고 **전원이 다시 돌린다**
- 로직을 바꾸면 이전 회차 보고서와 수치가 어긋나므로, 바꾼 내용을 이 문서에 기록한다

### 변경 이력

| 날짜 | 변경 | 영향 |
|---|---|---|
| 2026-08-28 | `omc` 블록 추가 (저장소 관리자) | 이전 회차 보고서 없음 |
