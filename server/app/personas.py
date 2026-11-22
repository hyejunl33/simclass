from __future__ import annotations

import json
from pathlib import Path

from .models import LessonSpec, Persona, PersonaSet

ROOT = Path(__file__).resolve().parents[2]
PERSONA_FIXTURE = ROOT / "fixtures" / "personas" / "objects_meaning.json"

TEMPLATES = [
    {
        "id": "harin",
        "name": "하린",
        "prior_knowledge": "높음",
        "confidence": "높음",
        "speech_style": "또박또박, 논리적으로 말함",
    },
    {
        "id": "junseo",
        "name": "준서",
        "prior_knowledge": "중간",
        "confidence": "높음",
        "speech_style": "자신 있게 말하지만 근거는 짧음",
    },
    {
        "id": "minji",
        "name": "민지",
        "prior_knowledge": "낮음",
        "confidence": "낮음",
        "speech_style": "조용하고 짧게 말함",
    },
]


def _mastery(lesson: LessonSpec, confidence: str) -> dict[str, float]:
    base = 0.55 if confidence == "높음" else 0.35 if confidence == "중간" else 0.2
    return {kc.id: round(max(0.05, base - i * 0.08), 2) for i, kc in enumerate(lesson.knowledge_components)}


def generate_personas(lesson: LessonSpec) -> PersonaSet:
    if lesson.id == "objects-meaning" and PERSONA_FIXTURE.exists():
        raw = json.loads(PERSONA_FIXTURE.read_text(encoding="utf-8"))
        by_id = {m.id: m for m in lesson.misconceptions}
        personas = []
        for p in raw["personas"]:
            m = by_id.get(p["misconception_id"])
            data = {k: v for k, v in p.items() if k != "initial_mastery"}
            personas.append(
                Persona(
                    **data,
                    misconception=m.text if m else "",
                    initial_mastery=p.get("initial_mastery") or _mastery(lesson, p["confidence"]),
                )
            )
        return PersonaSet(lesson_id=lesson.id, personas=personas)

    personas: list[Persona] = []
    for i, tmpl in enumerate(TEMPLATES):
        m = lesson.misconceptions[i % len(lesson.misconceptions)] if lesson.misconceptions else None
        personas.append(
            Persona(
                **tmpl,
                misconception_id=m.id if m else "",
                misconception=m.text if m else "",
                initial_mastery=_mastery(lesson, tmpl["confidence"]),
            )
        )
    return PersonaSet(lesson_id=lesson.id, personas=personas)
