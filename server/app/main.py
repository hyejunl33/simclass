from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .asr import transcribe_bytes
from .bkt import infer_correct, update_mastery
from .judge import (
    HumanCoding,
    JudgeReport,
    ValidationSample,
    agreement,
    judge_session,
    load_report,
    save_human_coding,
    save_report,
    to_markdown,
    validation_sample,
)
from .lesson_ingest import decode_ingest
from .llm import generate_student_responses
from .models import (
    ASRResponse,
    AudioRequest,
    GeneratePersonasRequest,
    IngestRequest,
    LessonSpec,
    PersonaSet,
    TTSRequest,
)
from .personas import generate_personas
from .session import (
    ReplayResponse,
    SessionStartRequest,
    SessionState,
    SessionStatus,
    SessionSummary,
    advance,
    end_session,
    new_session,
    record_turn,
    replay,
    status,
)
from .tts import synthesize

ROOT = Path(__file__).resolve().parents[2]
LESSON_DIR = ROOT / "fixtures" / "lesson_plans"

app = FastAPI(title="SimClass", version="0.5.0")
REVIEWED_LESSONS: dict[str, LessonSpec] = {}
PERSONA_SETS: dict[str, PersonaSet] = {}
SESSIONS: dict[str, SessionState] = {}


class TurnRequest(BaseModel):
    session_id: str = "demo-1"
    lesson_id: str = "objects-meaning"
    phase_id: str = "concept"
    teacher_utterance: str = Field(min_length=1)
    persona_ids: list[str] | None = None


class StudentResponse(BaseModel):
    id: str
    name: str
    text: str
    state: str
    mastery: dict[str, float]


class TurnResponse(BaseModel):
    students: list[StudentResponse]
    kt: dict[str, dict[str, float]]
    mode: str = "mock"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_lesson(lesson_id: str) -> LessonSpec:
    if lesson_id in REVIEWED_LESSONS:
        return REVIEWED_LESSONS[lesson_id]
    return LessonSpec(**load_json(LESSON_DIR / f"{lesson_id.replace('-', '_')}.json"))


def load_personas(lesson_id: str) -> PersonaSet:
    if lesson_id in PERSONA_SETS:
        return PERSONA_SETS[lesson_id]
    ps = generate_personas(load_lesson(lesson_id))
    PERSONA_SETS[lesson_id] = ps
    return ps


def get_session(session_id: str) -> SessionState:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "mode": "mock", "version": "0.5.0"}


@app.get("/api/lesson/{lesson_id}", response_model=LessonSpec)
def get_lesson(lesson_id: str) -> LessonSpec:
    return load_lesson(lesson_id)


@app.post("/api/lesson/ingest", response_model=LessonSpec)
def ingest_lesson(req: IngestRequest) -> LessonSpec:
    try:
        return decode_ingest(req.data_base64, filename=req.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/lesson/{lesson_id}", response_model=LessonSpec)
def review_lesson(lesson_id: str, spec: LessonSpec) -> LessonSpec:
    if spec.id != lesson_id:
        raise HTTPException(status_code=400, detail="Lesson ID mismatch")
    REVIEWED_LESSONS[lesson_id] = spec
    return spec


@app.get("/api/personas/{lesson_id}", response_model=PersonaSet)
def get_personas(lesson_id: str) -> PersonaSet:
    return load_personas(lesson_id)


@app.post("/api/personas/generate", response_model=PersonaSet)
def generate_personas_endpoint(req: GeneratePersonasRequest) -> PersonaSet:
    lesson = load_lesson(req.lesson_id)
    if not lesson.knowledge_components:
        raise HTTPException(status_code=400, detail="Lesson has no knowledge components")
    ps = generate_personas(lesson)
    PERSONA_SETS[ps.lesson_id] = ps
    return ps


@app.put("/api/personas/{lesson_id}", response_model=PersonaSet)
def review_personas(lesson_id: str, ps: PersonaSet) -> PersonaSet:
    if ps.lesson_id != lesson_id:
        raise HTTPException(status_code=400, detail="Lesson ID mismatch")
    if len(ps.personas) != 3:
        raise HTTPException(status_code=400, detail="Exactly three personas are required")
    if len({p.id for p in ps.personas}) != 3:
        raise HTTPException(status_code=400, detail="Persona IDs must be unique")
    PERSONA_SETS[lesson_id] = ps
    return ps


@app.post("/api/session/start", response_model=SessionStatus)
def start_session(req: SessionStartRequest) -> SessionStatus:
    lesson = load_lesson(req.lesson_id)
    if not lesson.phases:
        raise HTTPException(status_code=400, detail="Lesson has no phases")
    if req.session_id and req.session_id in SESSIONS:
        return status(SESSIONS[req.session_id])
    session = new_session(lesson, req.session_id)
    SESSIONS[session.id] = session
    return status(session)


@app.get("/api/session/{session_id}", response_model=SessionStatus)
def get_session_status(session_id: str) -> SessionStatus:
    return status(get_session(session_id))


@app.post("/api/session/{session_id}/advance", response_model=SessionStatus)
def advance_phase(session_id: str) -> SessionStatus:
    session = get_session(session_id)
    try:
        return advance(session)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/session/{session_id}/end", response_model=SessionSummary)
def finish_session(session_id: str) -> SessionSummary:
    return end_session(get_session(session_id))


@app.get("/api/session/{session_id}/replay", response_model=ReplayResponse)
def session_replay(session_id: str) -> ReplayResponse:
    return replay(get_session(session_id))


@app.post("/api/session/{session_id}/judge", response_model=JudgeReport)
def judge(session_id: str) -> JudgeReport:
    session = get_session(session_id)
    if not session.completed:
        raise HTTPException(status_code=409, detail="End the session before judging")
    report = judge_session(session)
    save_report(report)
    return report


@app.get("/api/session/{session_id}/report", response_model=JudgeReport)
def get_report(session_id: str) -> JudgeReport:
    report = load_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.get("/api/session/{session_id}/report.md", response_class=PlainTextResponse)
def get_report_markdown(session_id: str) -> str:
    session = get_session(session_id)
    report = load_report(session_id)
    if report is None:
        if not session.completed:
            raise HTTPException(status_code=409, detail="End the session before judging")
        report = judge_session(session)
        save_report(report)
    return to_markdown(report)


@app.get("/api/validation/sample", response_model=list[ValidationSample])
def get_validation_sample(ratio: float = 0.25) -> list[ValidationSample]:
    return validation_sample(ratio)


@app.post("/api/validation/{session_id}")
def submit_human_coding(session_id: str, coding: HumanCoding) -> dict[str, Any]:
    if load_report(session_id) is None:
        raise HTTPException(status_code=404, detail="Report not found")
    path = save_human_coding(session_id, coding)
    return {"ok": True, "path": str(path)}


@app.get("/api/validation/agreement")
def get_agreement() -> dict[str, Any]:
    return agreement()


@app.post("/api/asr", response_model=ASRResponse)
def asr(req: AudioRequest) -> ASRResponse:
    try:
        data = base64.b64decode(req.data_base64, validate=True)
        text, mode = transcribe_bytes(data)
        return ASRResponse(text=text, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ASR unavailable: {exc}") from exc


@app.post("/api/tts")
def tts(req: TTSRequest) -> Response:
    try:
        audio, _mode = synthesize(req.text, req.voice)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"TTS unavailable: {exc}") from exc
    if not audio:
        return Response(status_code=204)
    return Response(content=audio, media_type="audio/wav")


@app.post("/api/turn", response_model=TurnResponse)
def turn(req: TurnRequest) -> TurnResponse:
    lesson = load_lesson(req.lesson_id)
    session = SESSIONS.get(req.session_id)
    if session is None:
        session = new_session(lesson, req.session_id)
        SESSIONS[session.id] = session
    elif session.lesson_id != req.lesson_id:
        raise HTTPException(status_code=409, detail="Session lesson mismatch")
    if session.completed:
        raise HTTPException(status_code=409, detail="Session already ended")

    persona_set = load_personas(req.lesson_id)
    personas = [p.model_dump() for p in persona_set.personas]
    if req.persona_ids:
        personas = [p for p in personas if p["id"] in req.persona_ids]
    if not personas:
        raise HTTPException(status_code=400, detail="No personas available")

    phase_id = req.phase_id
    if not any(p.id == phase_id for p in lesson.phases):
        phase_id = session.phase.id if session.phase else phase_id
    else:
        session.phase_index = next(
            (i for i, p in enumerate(lesson.phases) if p.id == phase_id),
            session.phase_index,
        )

    result = generate_student_responses(
        lesson,
        personas,
        phase_id,
        req.teacher_utterance,
    )

    if not session.kt:
        session.kt = {
            p.id: dict(p.initial_mastery) for p in persona_set.personas
        }
    state = session.kt
    by_id = {p["id"]: p for p in personas}
    misconception_kc = {m.id: m.kc for m in lesson.misconceptions}

    for s in result["students"]:
        p = by_id.get(s["id"])
        if not p:
            continue
        kc = misconception_kc.get(p.get("misconception_id", ""))
        if not kc and lesson.knowledge_components:
            kc = lesson.knowledge_components[0].id
        if not kc:
            continue
        correct = infer_correct(s["text"], p.get("misconception", ""))
        update_mastery(state[s["id"]], kc, correct)
        s["mastery"] = dict(state[s["id"]])

    record_turn(session, req.teacher_utterance, result["students"], phase_id, state)
    students = [StudentResponse(**s) for s in result["students"]]
    kt = {pid: dict(values) for pid, values in state.items()}
    return TurnResponse(students=students, kt=kt, mode=result["mode"])
