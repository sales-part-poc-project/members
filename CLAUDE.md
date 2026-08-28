# CLAUDE.md

파트원 각자의 **Claude Code 사용 실태를 같은 양식으로 뽑아 모으는** 저장소.

사용자가 **`진단`** 이라고만 입력하면, 아래 "진단 절차" 0~8단계를 **처음부터 끝까지** 수행한다.
중간에 사용자에게 되묻지 않는다. 이름 3줄만 물어보고 나머지는 끝까지 알아서 진행한다.

산출물은 `data/` 에 **stem 이 같은 3종** — `.md`(사람이 읽는 보고서) · `.json`(대시보드가 읽는 요약) · `.html`(개인 시각화).
커밋해서 push 하면 GitHub Pages 통합 대시보드에 전원 요약이 자동으로 반영된다.

> 이 파일은 **트리거 + 라우팅 + 위반 금지 인덱스**만 담는다. 실제 필드 해설·템플릿 전문은 `docs/` 에 있고
> **그쪽이 상세 정본**이다. 요약만 보고 판단하면 이 작업의 함정(집계 구간 혼용, 인원 카운트 오염)을 그대로 밟는다.

---

## 트리거

| 사용자 입력 | 동작 |
|---|---|
| `진단` · `/진단` · `진단해줘` · `진단 시작` | 아래 0~8단계 전부 수행 |
| `진단 재실행` | 기존 `cc_usage_stats.json` 을 무시하고 2단계 집계부터 다시 |
| `진단 요약` | 이미 만들어진 `data/` 의 최신 보고서에서 1장 · 5-5 · 5-6 만 터미널 출력 (재집계 없음) |
| `진단 말투만` | 5장(프롬프트 습관과 말투)만 뽑아서 출력 |
| `진단 대시보드` | `python3 scripts/build_site.py --out _site && open _site/index.html` — 통합 대시보드 로컬 미리보기 (재집계 없음) |

`진단` 이 단독으로 들어오면 그것만으로 충분한 지시다. "무엇을 진단할까요?" 라고 되묻지 마라.

---

## 문서 맵

| 작업 | 먼저 읽을 문서 |
|---|---|
| 데이터 원본 · 집계 구간 3종 · 수치 함정 | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) |
| 보고서 0~11장 템플릿 **정본** | [docs/REPORT_TEMPLATE.md](docs/REPORT_TEMPLATE.md) |
| 요약 JSON 스키마 **정본** · 금지 키 | [docs/SUMMARY_SCHEMA.md](docs/SUMMARY_SCHEMA.md) |
| `speech` 블록 필드 해설 · 말투 해석법 | [docs/SPEECH_ANALYSIS.md](docs/SPEECH_ANALYSIS.md) |
| 마스킹 규칙 · 공유 범위 · 재미 코너 취급 | [docs/PRIVACY.md](docs/PRIVACY.md) |
| 집계 스크립트 (수정 금지) | [scripts/cc_usage.py](scripts/cc_usage.py) |
| `.html` 렌더 · 대시보드 빌드 (수정 금지) | [scripts/build_site.py](scripts/build_site.py) |
| GitHub Pages 배포 워크플로 | [.github/workflows/pages.yml](.github/workflows/pages.yml) |
| 보고서가 모이는 곳 | [data/](data/) |

---

## 진단 절차

### 0단계 — 3줄만 묻기

`AskUserQuestion` 을 쓰지 말고 **한 번에 프롬프트로** 묻는다. 답이 오면 즉시 1단계로 간다.

```
진단을 시작합니다. 아래 3줄만 알려주세요 (한 번에 적어주시면 됩니다).
1. 이름 / 파트:
2. 주 담당 업무 (한 줄):
3. 특별히 강조하고 싶은 것 (없으면 "없음"):
```

이름을 이미 알고 있거나 사용자가 첫 메시지에 함께 적었다면 이 단계를 건너뛴다.

### 1단계 — 환경 정보 수집

```bash
claude --version; uname -s -r; python3 --version
```

### 2단계 — 집계 실행

저장소 루트에서 실행한다. 읽기 전용이고 네트워크를 쓰지 않는다. 보통 5초, 이력이 많으면 1~2분.

```bash
python3 scripts/cc_usage.py
```

- 결과는 `cc_usage_stats.json` (gitignore 됨 — 커밋하지 마라)
- 실패하면 오류 메시지를 그대로 보고하고, **실패한 항목만** `수집 실패` 로 두고 나머지로 보고서를 완성한다
- "경로가 없다" 류 오류는 그 기능을 안 쓴다는 뜻이므로 정상이다

### 3단계 — 수치 해석

`cc_usage_stats.json` 을 읽는다. **파일 전체를 출력하지 말고** 필요한 값만 인용한다.
각 블록이 무엇을 뜻하는지는 [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) 에 있다.

4장의 **OMC 명령어 사용 비중은 `omc` 블록**에서 가져온다. `bash_commands_top`(실행한 bash 명령 상세)은
원시 참고용이고 **보고서에 쓰지 않는다.**

### 4단계 — 말투 분석

`speech` 블록을 [docs/SPEECH_ANALYSIS.md](docs/SPEECH_ANALYSIS.md) 의 해설대로 읽는다.
**마지막에 반드시** 그 사람 말투를 흉내 낸 **가상의 프롬프트 3개**를 지어낸다 (실제로 쓴 적 없는 문장이어야 한다).

### 5단계 — 대표 사례 정성 분석

`top_sessions` 에서 성격이 겹치지 않는 세션을 3~5개 고른다. 필요하면 실제 트랜스크립트를 연다.

```bash
ls ~/.claude/projects/<프로젝트폴더>/<sessionId>.jsonl
```

추측으로 미담을 만들지 마라. `first_prompt` · `files_touched` · `tool_calls` 에 있는 것만 쓴다.

### 6단계 — 보고서 작성 및 저장

[docs/REPORT_TEMPLATE.md](docs/REPORT_TEMPLATE.md) 의 0~11장을 **그대로** 채워
`data/{파트}_{이름}_{YYYYMMDD}.md` 로 저장한다.

파트와 이름은 **0단계 답변의 "1. 이름 / 파트"** 에서 가져온다.
표기 규칙: **공백은 하이픈 `-` 으로 바꾸고, 언더스코어 `_` 는 구분자이므로 파트·이름 안에 쓰지 않는다**
(예: `영업1파트_홍길동_20260828.md`).

### 7단계 — 요약 JSON 과 시각화 HTML

`.md` 를 쓴 직후 같은 수치로 요약 JSON 을 만들고, 그것으로 `.html` 을 렌더한다.
**정본은 [docs/SUMMARY_SCHEMA.md](docs/SUMMARY_SCHEMA.md)** 다. 필드 이름을 추측하지 말고 그 문서를 읽어라.

1. **뼈대 생성** — 수치 필드는 자동으로 채워지고, 서술 필드는 비어 있다

   ```bash
   python3 scripts/build_site.py --scaffold cc_usage_stats.json \
     --part {파트} --name {이름} --date {YYYY-MM-DD} \
     --role "{주 담당 업무}" --highlight "{강조하고 싶은 것}"
   ```

   → `data/{파트}_{이름}_{YYYYMMDD}.json` 생성. 기존 파일은 `--force` 없이 덮어쓰지 않는다

2. **비어 있는 서술 필드를 채운다.** 값은 **`.md` 에 쓴 내용과 동일해야** 한다 — JSON 만 따로 계산하지 않는다.
   **프롬프트 원문·성별 예상·비용은 넣지 않는다** (금지 키가 있으면 빌드가 거부된다).
   본인이 9장을 뺐으면 `fun` 블록 전체를 `null` 로 둔다.
   **`expert_index` 는 스캐폴드가 계산한다 — 값을 고치지 말고 `.md` 9장에 그대로 옮긴다**
   (`fun` 이 `null` 이어도 `expert_index` 블록은 남긴다)

3. **검사** — 통과할 때까지 고친다

   ```bash
   python3 scripts/build_site.py --check data/{파트}_{이름}_{YYYYMMDD}.json
   ```

4. **개인 시각화 렌더**

   ```bash
   python3 scripts/build_site.py --person data/{파트}_{이름}_{YYYYMMDD}.json
   ```

   → `data/{파트}_{이름}_{YYYYMMDD}.html` 생성

5. 사용자에게 `open data/{파트}_{이름}_{YYYYMMDD}.html` 로 열어보라고 안내한다

**`.html` 을 직접 작성하거나 수정하지 마라.** 스크립트 산출물이다 — 사람마다 같은 비주얼이어야 비교가 된다.

### 8단계 — 마무리 안내

1. 저장된 **3개 경로**(`.md` · `.json` · `.html`)를 알려준다
2. **1장(요약)과 5-5·5-6(말투 요약·재현)만** 터미널에 출력한다
3. 아래 자체 점검을 체크리스트로 보고한다
4. 안내한다: **"9장은 재미용입니다. 빼고 보내셔도 됩니다."**
5. 커밋·푸시 방법을 안내한다 (**Claude 가 직접 실행하지 않는다. 명령만 알려준다**)

   ```bash
   git add data/{파트}_{이름}_{YYYYMMDD}.md data/{파트}_{이름}_{YYYYMMDD}.json data/{파트}_{이름}_{YYYYMMDD}.html
   git commit -m "📝 {이름} 진단 보고서 ({YYYY-MM-DD})"
   git push
   ```

   푸시하면 **약 1~2분 뒤** 통합 대시보드에 반영된다:
   <https://sales-part-poc-project.github.io/members/>

---

## 자체 점검 (8단계에서 반드시 보고)

- [ ] 모든 수치가 `cc_usage_stats.json` 에서 인용되었고 창작 수치가 없다
- [ ] 집계 구간 3종을 혼용하지 않았다
- [ ] `lastCost` 를 총비용으로 쓰지 않았다
- [ ] 비밀값·개인정보가 마스킹되었다
- [ ] 0~11장 목차가 템플릿과 동일하고 빈 절이 없다
- [ ] 대표 사례가 3건 이상이고 서로 성격이 다르다
- [ ] 8~9장의 모든 판단에 인용 수치가 붙어 있다
- [ ] 9장에 근거 강도가 표기되어 있고, 비하로 읽힐 표현이 없다
- [ ] `.json` 의 수치가 `.md` 와 동일하다 (따로 계산한 값이 없다)
- [ ] `--check` 를 통과했다
- [ ] `.html` 을 손으로 쓰지 않고 `--person` 으로 생성했다
- [ ] `.md` · `.json` · `.html` 세 파일의 stem 이 완전히 같다
- [ ] `.json` 에 프롬프트 원문·성별 예상이 없다
- [ ] 9장 전문가 지수가 `expert_index.score` 와 같다

---

## GitHub Pages 통합 대시보드

**동작 원리**

1. `data/` 에 3종 파일을 커밋하고 `main` 에 push 한다
2. GitHub Actions(`.github/workflows/pages.yml`)가 `python3 scripts/build_site.py --out _site` 로 대시보드를 빌드한다
3. 빌드 결과가 GitHub Pages 로 배포된다 — 약 1~2분

**URL**: <https://sales-part-poc-project.github.io/members/>

대시보드는 `data/**/*.json` 만 읽는다 (`.md` 는 파싱하지 않는다).
같은 사람이 여러 번 뽑았으면 **(파트, 이름) 별 최신 날짜 1건**을 대표로 쓰고 나머지는 이력으로 표시한다.

**로컬 미리보기** (push 없이 확인)

```bash
python3 scripts/build_site.py --out _site && open _site/index.html
```

**최초 1회 설정** — 저장소 관리자가 GitHub 웹에서 한 번 해야 한다

- 저장소 **Settings → Pages → Build and deployment → Source** 를 **`GitHub Actions`** 로 지정
  (워크플로가 `enablement: true` 로 자동 시도하지만, 권한에 따라 수동 지정이 필요하다)
- 이 저장소는 **public 이라 Pages 가 무료로 동작한다** (참고: private 으로 바꾸면 Pages 에 Pro / Team / Enterprise 플랜이 필요해진다)
- 배포가 안 되면 저장소 **Actions 탭**에서 실패한 워크플로 로그를 확인한다

---

## 위반 금지 인덱스

전부 **이 보고서를 실제로 뽑아보다 나온 규칙**이다. 어겨도 에러가 안 나고 **보고 내용만 조용히 틀린다.**

### 수치 정확성 — 어기면 사람마다 다른 기준으로 비교하게 된다

| 규칙 | 근거 |
|---|---|
| **집계 구간 3종을 섞지 말 것.** 트랜스크립트는 **약 30일 후 자동 삭제**되고 `history.jsonl` / `.session-stats.json` 은 수개월치다. "최근 30일"을 "전체 기간"으로 쓰면 오래 안 쓴 사람이 실제보다 훨씬 적게 잡힌다 | [DATA_SOURCES](docs/DATA_SOURCES.md) |
| **`lastCost` / `lastModelUsage` 를 누적 비용으로 인용 금지.** 프로젝트별 **마지막 세션** 값이다. 비용 대신 **토큰 총량**으로 보고한다 | [DATA_SOURCES](docs/DATA_SOURCES.md) |
| `human_turns` · `slash_turns` · `agent_turns` 를 합쳐서 "내가 보낸 메시지"라고 쓰지 말 것. 슬래시 커맨드 부기 라인과 서브에이전트 주입 턴이 user 턴으로 기록되므로, 합치면 한 세션이 488턴으로 부풀어 오른다 (실제 사람 발화는 12턴이었다) | [DATA_SOURCES](docs/DATA_SOURCES.md) |
| 수치 없이 형용사만 쓰지 말 것 — 8장의 모든 축은 **5점 척도 + 인용 수치**가 붙어야 한다. "꼼꼼한 편" 은 보고가 아니다 | [REPORT_TEMPLATE](docs/REPORT_TEMPLATE.md) |
| 데이터가 없으면 절을 **삭제하지 말고** `데이터 없음` 으로 채울 것 — 절이 사라지면 취합할 때 장 번호가 밀린다. JSON 도 같다: 키를 지우지 말고 `null` / `[]` / `0` 으로 둔다 | [REPORT_TEMPLATE](docs/REPORT_TEMPLATE.md) · [SUMMARY_SCHEMA](docs/SUMMARY_SCHEMA.md) |
| **`.json` 의 수치를 따로 계산하지 말 것.** `.md` 에 적은 값을 그대로 옮긴다. 두 파일의 값이 다르면 보고서와 대시보드가 서로 다른 말을 한다 | [SUMMARY_SCHEMA](docs/SUMMARY_SCHEMA.md) |

### 양식 — 어기면 파트원 간 비교가 불가능해진다

| 규칙 | 근거 |
|---|---|
| **0~11장 번호와 제목을 한 글자도 바꾸지 말 것.** 같은 장끼리 나란히 놓고 읽는 게 이 저장소의 존재 이유다 | [REPORT_TEMPLATE](docs/REPORT_TEMPLATE.md) |
| 저장 위치는 `data/{파트}_{이름}_{YYYYMMDD}` 고정이고 **`.md` · `.json` · `.html` 의 stem 이 완전히 같아야** 한다. 파트·이름의 공백은 하이픈 `-` 으로, 언더스코어 `_` 는 구분자이므로 쓰지 않는다. 홈 디렉터리에 만들지 말 것 | [SUMMARY_SCHEMA](docs/SUMMARY_SCHEMA.md) |
| **`.html` 을 손으로 작성·수정하지 말 것.** `build_site.py --person` 이 JSON 에서 렌더한다. 사람마다 비주얼이 다르면 나란히 놓고 볼 수가 없다 | [SUMMARY_SCHEMA](docs/SUMMARY_SCHEMA.md) |
| `cc_usage_stats.json` 을 커밋하지 말 것 — 프롬프트 원문이 통째로 들어 있다 (gitignore 되어 있음) | [PRIVACY](docs/PRIVACY.md) |

### 사람에 대한 서술 — 어기면 회람됐을 때 사고가 난다

| 규칙 | 근거 |
|---|---|
| **8장(근거 있음)과 9장(재미)을 섞지 말 것.** 8장은 인용 수치가 붙고, 9장은 근거 강도가 `약함` 이하다. 섞이면 추측이 사실처럼 회람된다 | [PRIVACY](docs/PRIVACY.md) |
| 9장 각 항목에 **근거 강도 표기 필수** — MBTI `약함`, 나이대 `약함`, 성별 `거의 없음`, 혈액형 **`없음(무작위)`**. 혈액형은 데이터 신호가 0이라는 걸 밝히고 억지 논리를 한 줄 붙이는 게 규칙이다 | [PRIVACY](docs/PRIVACY.md) |
| 성별을 **확신 표현으로 쓰지 말 것.** 팀 전체에 회람되는 문서다. 틀리면 그 자리가 어색해진다 | [PRIVACY](docs/PRIVACY.md) |
| 외모·성격 결함·업무 능력 비하로 읽힐 표현 금지. 재미 코너는 **호의적으로** 쓴다 | [PRIVACY](docs/PRIVACY.md) |
| 9장은 **본인이 회신 전 통째로 지워도 되는 장**임을 마지막에 반드시 안내할 것 | [PRIVACY](docs/PRIVACY.md) |

### 보안

| 규칙 | 근거 |
|---|---|
| **로컬 파일만 읽는다.** 외부 전송·업로드·웹 검색 금지. 데이터는 `~/.claude/` 와 `~/.claude.json` 안에만 있다 | [PRIVACY](docs/PRIVACY.md) |
| API 키·토큰·비밀번호·주민번호·고객 개인정보·고객사 실명은 `***` 마스킹 | [PRIVACY](docs/PRIVACY.md) |
| **`.json` · `.html` 은 GitHub Pages 로 공개된다 — `.md` 보다 노출 범위가 넓다.** 프롬프트 원문 · 성별 예상 · 비용을 **한 줄도** 넣지 말 것 (금지 키가 있으면 빌드가 거부된다) | [SUMMARY_SCHEMA](docs/SUMMARY_SCHEMA.md) · [PRIVACY](docs/PRIVACY.md) |
| **이 저장소는 public 이다 — `data/` 에 커밋하는 것은 `.md` 를 포함해 인터넷에 공개된다.** 마스킹을 더 엄격하게 적용하고, 애매하면 넣지 않는다 | [PRIVACY](docs/PRIVACY.md) |
| 반대로 **프로젝트명·저장소명·브랜치명·파일경로는 그대로 둔다** — 파트 내 비교에 식별이 필요하다. 다만 저장소가 public 이므로, **사내 프로젝트명이 외부에 노출되면 곤란한 경우 관리자와 상의**하도록 사용자에게 안내한다 | [PRIVACY](docs/PRIVACY.md) |
| `scripts/cc_usage.py` 를 수정하지 말 것 — 사람마다 다른 집계 로직을 쓰면 비교가 무의미해진다. 고칠 일이 있으면 저장소 관리자에게 알린다 | [DATA_SOURCES](docs/DATA_SOURCES.md) |
| `scripts/build_site.py` 를 수정하지 말 것 — **같은 이유다.** 사람마다 다른 렌더러를 쓰면 대시보드가 서로 다른 것을 보여준다 | [SUMMARY_SCHEMA](docs/SUMMARY_SCHEMA.md) |
