from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .models import LessonSpec, Persona

MOCK_LINES = {
    "harin": "국어사전에 나오는 뜻이요?",
    "junseo": "비싼 거요?",
    "minji": "친구랑 순서가 같아야 친구예요?",
}


def _mock(personas: list[dict[str, Any]], teacher_utterance: str, fallback: bool = False) -> dict[str, Any]:
    count = 1 if len(teacher_utterance) < 12 else 2
    chosen = personas[:count]
    students = [
        {
            "id": p["id"],
            "name": p["name"],
            "text": MOCK_LINES.get(p["id"], "잘 모르겠어요."),
            "state": "thinking" if p["confidence"] != "낮음" else "confused",
            "mastery": p["initial_mastery"],
        }
        for p in chosen
    ]
    return {"students": students, "mode": "mock" if not fallback else "mock_fallback"}


def build_prompt(
    lesson: LessonSpec,
    personas: list[dict[str, Any]],
    phase_id: str,
    teacher_utterance: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    phase = next((p for p in lesson.phases if p.id == phase_id), lesson.phases[0] if lesson.phases else None)
    phase_text = f"{phase.name} ({phase.minutes}분)" if phase else phase_id
    persona_text = json.dumps(personas, ensure_ascii=False)
    history_text = "\n".join(
        f"{h.get('role', '?')}: {h.get('text', '')}" for h in (history or [])
    )
    system = (
        "You are simulating three Korean 2nd-grade students in a 즐거운 생활 lesson. "
        "Stay in character. Use short, age-appropriate Korean. "
        "Students may hold misconceptions and may be wrong. "
        "NEVER state the lesson's final answer or give a complete solution. "
        "Return ONLY JSON with one or two students: "
        '{"students":[{"id":"...","name":"...","text":"...","state":"thinking|confused|confident"}]}.'
    )
    user = f"""Lesson: {lesson.topic}
Unit: {lesson.unit}
Phase: {phase_text}
Teacher utterance: {teacher_utterance}
Personas: {persona_text}
Recent dialogue:
{history_text}

Choose one or two students who would respond now. Keep each response to 1-2 sentences.
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_student_responses(
    lesson: LessonSpec,
    personas: list[dict[str, Any]],
    phase_id: str,
    teacher_utterance: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    mode = os.getenv("LLM_MODE", "mock").strip().lower()
    if mode != "ollama" or not personas:
        return _mock(personas, teacher_utterance)

    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M")
    payload = {
        "model": model,
        "messages": build_prompt(lesson, personas, phase_id, teacher_utterance, history),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.7, "num_predict": 220},
    }
    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.post(url, json=payload)
            res.raise_for_status()
            content = res.json()["message"]["content"]
        data = json.loads(content)
        students = data.get("students", [])
        valid = []
        by_id = {p["id"]: p for p in personas}
        for s in students[:2]:
            if s.get("id") not in by_id:
                continue
            p = by_id[s["id"]]
            valid.append(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "text": str(s.get("text", "")).strip()[:300],
                    "state": s.get("state", "thinking"),
                    "mastery": p["initial_mastery"],
                }
            )
        if not valid:
            return _mock(personas, teacher_utterance, fallback=True)
        return {"students": valid, "mode": "ollama"}
    except Exception:
        return _mock(personas, teacher_utterance, fallback=True)
