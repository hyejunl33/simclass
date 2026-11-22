from __future__ import annotations

from pydantic import BaseModel, Field


class Phase(BaseModel):
    id: str
    name: str
    minutes: int = 0
    activities: list[str] = Field(default_factory=list)
    teacher_questions: list[str] = Field(default_factory=list)
    expected_responses: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class KnowledgeComponent(BaseModel):
    id: str
    name: str
    description: str


class Misconception(BaseModel):
    id: str
    kc: str
    text: str


class LessonSpec(BaseModel):
    id: str
    grade: str = "2"
    subject: str = "즐거운 생활"
    unit: str
    topic: str
    lesson_no: str = ""
    pages: str = ""
    duration_min: int = 40
    phases: list[Phase] = Field(default_factory=list)
    knowledge_components: list[KnowledgeComponent] = Field(default_factory=list)
    misconceptions: list[Misconception] = Field(default_factory=list)
    needs_review: bool = False
    source_filename: str = ""


class IngestRequest(BaseModel):
    filename: str
    data_base64: str


class Persona(BaseModel):
    id: str
    name: str
    prior_knowledge: str = "중간"
    misconception_id: str = ""
    misconception: str = ""
    confidence: str = "중간"
    speech_style: str = ""
    initial_mastery: dict[str, float] = {}


class PersonaSet(BaseModel):
    lesson_id: str
    personas: list[Persona]


class GeneratePersonasRequest(BaseModel):
    lesson_id: str = "objects-meaning"


class AudioRequest(BaseModel):
    filename: str = "audio.wav"
    data_base64: str


class ASRResponse(BaseModel):
    text: str
    mode: str


class TTSRequest(BaseModel):
    text: str
    voice: str = "Yuna"
