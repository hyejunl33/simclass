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

## Quick start (MVP, mock LLM)

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `app/processing/SimClass/SimClass.pde` in Processing and run it. Type a
teacher question and press Enter. The mock server returns three student
responses so the UI loop can be tested without a model. Use the "HWP 수업안
불러오기" button to upload a lesson plan and see the parsed summary. The mock
server returns a `LessonSpec`; the UI shows the topic, phase count, duration, and
whether review is needed.

## Local LLM (Ollama)

The server uses a prompt-only small model; no fine-tuning.

```bash
# Mac mini
ollama pull qwen2.5:3b-instruct-q4_K_M
LLM_MODE=ollama OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If Ollama is unavailable, the server returns cached mock responses and the UI
shows a fallback mode. The prompt explicitly forbids giving the lesson's final
answer.

## Docs

- [`docs/spec.md`](docs/spec.md) — product and implementation spec
- [`docs/rubric.md`](docs/rubric.md) — lesson-demonstration rubric and evidence rules
- [`docs/ws_protocol.md`](docs/ws_protocol.md) — message contract
- [`fixtures/lesson_plans/objects_meaning.json`](fixtures/lesson_plans/objects_meaning.json) — 즐생 lesson fixture
- [`fixtures/personas/objects_meaning.json`](fixtures/personas/objects_meaning.json) — three persona fixture

## Status

Tickets 01–05 are implemented: end-to-end mock loop, HWP ingest, persona
generation/editing, local Ollama adapter with fallback, and BKT mastery.
Next slices are real-time voice (issue #7) and TTS (issue #8); both need the
Mac mini Whisper/`say` runtime for end-to-end verification.
