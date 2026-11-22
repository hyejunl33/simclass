# SimClass

Processing-based classroom rehearsal simulator for pre-service teachers.

SimClass takes a Korean elementary lesson plan, turns it into a structured
`LessonSpec`, generates three student personas with realistic misconceptions, and
runs a real-time classroom simulation. The teacher speaks; Whisper transcribes;
a local LLM plays the students; BKT tracks knowledge state; after the session an
LLM judge produces rubric-based feedback with evidence quotes.

> **Demo first, deployment later.** The target is a local demo on a laptop +
> Mac mini M6 32GB. No cloud, auth, or multi-tenant deployment in scope.

## Why this is not a vibe-coded HTML app

- The app has a **stateful classroom model**: personas, lesson phase, dialogue,
  and BKT mastery, not a single chat prompt.
- **Real-time voice** is part of the interaction loop, not a text box afterthought.
- Feedback is **evidence-grounded** against a transparent rubric informed by
  elementary teacher employment exam (초등임용 2차) lesson-demonstration criteria.
- **No fine-tuning** in the main study: data and quality metrics are not yet
  reliable. The ML contribution is BKT + ASR + structured LLM judging.

## Architecture

```text
[Laptop / Linux]
  Processing .pde app
  - classroom view, 3 students, dialogue, KT panel
  - microphone capture
  - HTTP/WebSocket client
        |
        v
[Mac mini M6 32GB]
  FastAPI server
  - Whisper ASR (MLX / whisper.cpp)
  - Ollama Qwen2.5-3B/7B
  - BKT
  - rubric judge
  - macOS `say` TTS
```

## Lesson ingest

`POST /api/lesson/ingest` accepts a base64-encoded HWP/HWPX file and returns a
`LessonSpec` with phases, activities, teacher questions, expected responses,
materials, notes, knowledge components, and misconceptions. The attached 즐생
lesson is the first fixture. Use `PUT /api/lesson/{id}` to save a reviewed spec.

`POST /api/personas/generate` creates three personas from the lesson;
`PUT /api/personas/{id}` saves edits. In the Processing demo, load an HWP, then
click a student card to cycle its misconception and persist the change.

## Quick start

```bash
git clone https://github.com/hyejunl33/simclass.git
cd simclass

# laptop-only demo with cached responses
SIMCLASS_MODE=mock scripts/start_server.sh

# or on the Mac mini with Ollama + MLX Whisper + say
SIMCLASS_MODE=full scripts/start_server.sh
```

Point `app/processing/SimClass/data/server.txt` at the server, then:

```bash
scripts/run_processing.sh run
```

Full instructions: [`docs/runbook.md`](docs/runbook.md). If the server is
unreachable, the Processing app automatically switches to cached lesson,
personas, and student turns, so the classroom flow still runs.

Manual server start:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

## 40-minute session + replay

`POST /api/session/start` creates a timed session from the lesson phases
(5/17/12/6 minutes). `POST /api/turn` records teacher and student turns plus a KT
snapshot. `POST /api/session/{id}/advance` and `/end` move through the lesson,
and `GET /api/session/{id}/replay` returns the transcript, KT timeline, and
planned-vs-actual phase timings.

In the Processing app, use **수업 시작 → 발문/음성 입력 → 다음 단계 → 수업 종료 →
리플레이**. After a session ends, **새 세션** runs the same lesson and personas
again for the practice-effect comparison. See
[`docs/session_flow.md`](docs/session_flow.md).

## Rubric feedback

After the session ends, **피드백** runs a two-stage judge (talk-move coding, then
rubric scoring). Every score has evidence quotes that are checked against the
transcript; invalid quotes are rejected and the judge retries. Visual behaviors
are `N/A`, and audio delivery is scored from ASR speech duration when voice input
was used.

- `POST /api/session/{id}/judge/start` + `GET /api/judge/{job_id}` — async judge
- `GET /api/session/{id}/report.md` — Markdown report
- `GET /api/validation/sample?ratio=0.25` — human double-coding sample
- `GET /api/validation/agreement` — exact agreement + Cohen's kappa

Reports are written to `reports/` on the server. See
[`docs/judge.md`](docs/judge.md).

## Local LLM (Ollama)

The server uses a prompt-only small model; no fine-tuning.

```bash
# Mac mini
ollama pull qwen2.5:3b-instruct-q4_K_M
LLM_MODE=ollama \
OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M \
JUDGE_MODEL=qwen2.5:7b-instruct-q4_K_M \
ASR_MODE=mlx TTS_MODE=say TTS_VOICE=Yuna \
  uvicorn app.main:app --host 0.0.0.0 --port 8010
```

If Ollama is unavailable, the server returns cached mock responses and the UI
shows a fallback mode. The prompt explicitly forbids giving the lesson's final
answer.

ASR and TTS are optional adapters:

- `ASR_MODE=mock|mlx_whisper|http`
- `TTS_MODE=mock|say|http`
- On the Mac mini: `ASR_MODE=mlx TTS_MODE=say`

See [docs/mac_mini_setup.md](docs/mac_mini_setup.md) and
`scripts/connect_mac_mini.sh`.

## Docs

- [`docs/runbook.md`](docs/runbook.md) — clean-checkout demo runbook
- [`docs/spec.md`](docs/spec.md) — product and implementation spec
- [`docs/rubric.md`](docs/rubric.md) — lesson-demonstration rubric and evidence rules
- [`docs/ws_protocol.md`](docs/ws_protocol.md) — message contract
- [`docs/mac_mini_setup.md`](docs/mac_mini_setup.md) — Mac mini runtime + laptop connection
- [`docs/session_flow.md`](docs/session_flow.md) — 40-minute phases, session API, replay
- [`docs/judge.md`](docs/judge.md) — two-stage rubric judge, evidence rules, human validation
- [`docs/validation_checklist.md`](docs/validation_checklist.md) — two-rater checklist and kappa
- [`fixtures/lesson_plans/objects_meaning.json`](fixtures/lesson_plans/objects_meaning.json) — 즐생 lesson fixture
- [`fixtures/personas/objects_meaning.json`](fixtures/personas/objects_meaning.json) — three persona fixture
- [`fixtures/sessions/`](fixtures/sessions) — sample 40-minute session, report JSON, and Markdown

## Status

Tickets 01–10 are implemented: end-to-end loop, HWP ingest, persona
generation/editing, Ollama fallback, BKT mastery, real-time voice (MLX Whisper),
macOS TTS, the 40-minute phase flow + replay, the evidence-grounded rubric judge,
and demo hardening (runbook, scripts, cached offline mode, sample session,
validation checklist). See [`docs/runbook.md`](docs/runbook.md).

Known limitations: sessions are in-memory on one server; visual teaching
behaviors are `N/A`; the rubric is informed by public 초등임용 2차 direction but
is not an official scoring sheet; the 3B turn model can repeat a student; no
cloud, auth, multi-user, or fine-tuning in this demo.
