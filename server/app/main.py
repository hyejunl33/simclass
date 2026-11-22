from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
LESSON_DIR = ROOT / "fixtures" / "lesson_plans"
PERSONA_DIR = ROOT / "fixtures" / "personas"

app = FastAPI(title="SimClass", version="0.1.0")


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


def load_lesson(lesson_id: str) -> dict[str, Any]:
    return load_json(LESSON_DIR / f"{lesson_id.replace('-', '_')}.json")


def load_personas(lesson_id: str) -> dict[str, Any]:
    return load_json(PERSONA_DIR / f"{lesson_id.replace('-', '_')}.json")


MOCK_LINES = {
    "harin": "국어사전에 나오는 뜻이요?",
    "junseo": "비싼 거요?",
    "minji": "친구랑 순서가 같아야 친구예요?",
}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "mode": "mock"}


@app.get("/api/lesson/{lesson_id}")
def get_lesson(lesson_id: str) -> dict[str, Any]:
    return load_lesson(lesson_id)


@app.get("/api/personas/{lesson_id}")
def get_personas(lesson_id: str) -> dict[str, Any]:
    return load_personas(lesson_id)


@app.post("/api/turn", response_model=TurnResponse)
def turn(req: TurnRequest) -> TurnResponse:
    lesson = load_lesson(req.lesson_id)
    persona_data = load_personas(req.lesson_id)
    personas = persona_data["personas"]
    if req.persona_ids:
        personas = [p for p in personas if p["id"] in req.persona_ids]
    if not personas:
        raise HTTPException(status_code=400, detail="No personas available")

    # Demo behaviour: one or two students answer, rotating by turn length.
    count = 1 if len(req.teacher_utterance) < 12 else 2
    chosen = personas[:count]
    students = [
        StudentResponse(
            id=p["id"],
            name=p["name"],
            text=MOCK_LINES.get(p["id"], "잘 모르겠어요."),
            state="thinking" if p["confidence"] != "낮음" else "confused",
            mastery=p["initial_mastery"],
        )
        for p in chosen
    ]
    kt = {p["id"]: p["initial_mastery"] for p in personas}
    return TurnResponse(students=students, kt=kt, mode="mock")
