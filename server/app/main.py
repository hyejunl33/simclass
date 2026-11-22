from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import base64

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .asr import transcribe_bytes
from .bkt import infer_correct, update_mastery
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
from .tts import synthesize
from .personas import generate_personas

ROOT = Path(__file__).resolve().parents[2]
LESSON_DIR = ROOT / "fixtures" / "lesson_plans"

app = FastAPI(title="SimClass", version="0.3.0")
REVIEWED_LESSONS: dict[str, LessonSpec] = {}
PERSONA_SETS: dict[str, PersonaSet] = {}
SESSION_MASTERY: dict[str, dict[str, dict[str, float]]] = {}


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


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "mode": "mock", "version": "0.3.0"}


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
    load_lesson(req.lesson_id)
    persona_set = load_personas(req.lesson_id)
    personas = [p.model_dump() for p in persona_set.personas]
    if req.persona_ids:
        personas = [p for p in personas if p["id"] in req.persona_ids]
    if not personas:
        raise HTTPException(status_code=400, detail="No personas available")

    lesson = load_lesson(req.lesson_id)
    result = generate_student_responses(
        lesson,
        personas,
        req.phase_id,
        req.teacher_utterance,
    )

    if req.session_id not in SESSION_MASTERY:
        SESSION_MASTERY[req.session_id] = {
            p["id"]: dict(p["initial_mastery"]) for p in personas
        }
    state = SESSION_MASTERY[req.session_id]
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

    students = [StudentResponse(**s) for s in result["students"]]
    kt = {pid: dict(values) for pid, values in state.items()}
    return TurnResponse(students=students, kt=kt, mode=result["mode"])
