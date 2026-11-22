# SimClass project conventions

## Product

SimClass is a **Processing-based classroom rehearsal simulator** for pre-service
teachers. A teacher uploads a Korean elementary lesson plan (HWP), the system
extracts a `LessonSpec`, creates three student personas with misconceptions, and
runs a real-time 40-minute lesson simulation. Afterward an LLM judge produces
rubric scores with evidence quotes.

## Hard constraints

- **Processing is the app.** The final artifact is a Processing Java `.pde`
  sketch. p5.js may be used only for a disposable UX prototype.
- **No fine-tuning in the main study.** The local LLM is prompt-only. BKT and
  ASR are the ML components.
- **The demo must run locally** on a laptop + Mac mini M6 32GB. No deployment,
  auth, cloud, or multi-user requirements.
- **Never let the AI give the final answer to the student.** The simulator
  generates student personas and teacher feedback; it does not solve the lesson
  for the pre-service teacher.
- **Evidence or N/A.** The judge may only cite actual transcript/audio evidence.
  Visual domains (eye contact, board writing) are out of scope for the demo.

## Architecture seams

- `server/` — FastAPI orchestration, ASR/LLM adapters, BKT, judge, session store.
- `app/processing/SimClass/` — Processing client and classroom view.
- `fixtures/` — lesson-plan and persona fixtures used by tests and the demo.
- `docs/` — spec, rubric, protocol.

Keep the HTTP/WebSocket contract stable. The Processing client should be able to
switch between a mock server, a local Ollama server, and the Mac mini without
changing the UI code.

## Testing

- Unit tests for `LessonSpec` validation, BKT updates, rubric aggregation, and
  evidence validation.
- Contract tests for the turn API / WebSocket messages.
- Mock ASR and LLM in tests; no network in CI.
- Processing UI is verified manually and through a protocol harness.

## Code style

- Python: standard library + FastAPI/Pydantic; type hints where practical.
- Processing: Java syntax, clear `setup`/`draw`, small helper classes.
- Korean user-facing strings; English identifiers.

## Issue workflow

Tickets are tracer-bullet vertical slices. Work blockers first. Each ticket must
be demoable on its own.
