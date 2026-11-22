from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_lesson_fixture_has_phases_and_misconceptions():
    r = client.get("/api/lesson/objects-meaning")
    assert r.status_code == 200
    lesson = r.json()
    assert lesson["topic"] == "물건의 의미는 무엇일까요?"
    assert len(lesson["phases"]) == 4
    assert len(lesson["misconceptions"]) == 4


def test_three_personas():
    r = client.get("/api/personas/objects-meaning")
    assert r.status_code == 200
    personas = r.json()["personas"]
    assert len(personas) == 3
    assert {p["id"] for p in personas} == {"harin", "junseo", "minji"}


def test_turn_returns_students_and_kt():
    r = client.post(
        "/api/turn",
        json={
            "session_id": "demo-1",
            "lesson_id": "objects-meaning",
            "phase_id": "concept",
            "teacher_utterance": "물건의 의미는 무엇일까요?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert 1 <= len(body["students"]) <= 2
    assert body["mode"] == "mock"
    assert "harin" in body["kt"]


def test_unknown_lesson_is_404():
    r = client.get("/api/lesson/does-not-exist")
    assert r.status_code == 404


import base64
from pathlib import Path

import pytest

LOCAL_LESSON = Path("/home/hy3jun/문서/카카오톡 받은 파일/지도안 2차 러프 초안.hwp")


@pytest.mark.skipif(not LOCAL_LESSON.exists(), reason="local lesson plan fixture not present")
def test_ingest_attached_lesson_plan():
    raw = LOCAL_LESSON.read_bytes()
    r = client.post(
        "/api/lesson/ingest",
        json={
            "filename": LOCAL_LESSON.name,
            "data_base64": base64.b64encode(raw).decode("ascii"),
        },
    )
    assert r.status_code == 200, r.text
    lesson = r.json()
    assert lesson["unit"] == "1-2-약속"
    assert "의미" in lesson["topic"]
    assert len(lesson["phases"]) == 4
    assert sum(p["minutes"] for p in lesson["phases"]) == 40
    assert len(lesson["knowledge_components"]) == 4
    assert len(lesson["misconceptions"]) >= 3
    assert lesson["needs_review"] is False


def test_ingest_rejects_garbage():
    r = client.post(
        "/api/lesson/ingest",
        json={"filename": "x.hwp", "data_base64": "aGVsbG8="},
    )
    assert r.status_code == 400


def test_review_lesson_roundtrip():
    lesson = client.get("/api/lesson/objects-meaning").json()
    lesson["topic"] = "수정된 주제"
    r = client.put("/api/lesson/objects-meaning", json=lesson)
    assert r.status_code == 200, r.text
    assert r.json()["topic"] == "수정된 주제"
    assert client.get("/api/lesson/objects-meaning").json()["topic"] == "수정된 주제"


def test_generate_personas_for_lesson():
    r = client.post("/api/personas/generate", json={"lesson_id": "objects-meaning"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["personas"]) == 3
    assert all(p["misconception"] for p in body["personas"])
    assert {p["id"] for p in body["personas"]} == {"harin", "junseo", "minji"}


def test_review_personas_roundtrip():
    body = client.post("/api/personas/generate", json={"lesson_id": "objects-meaning"}).json()
    body["personas"][0]["misconception"] = "의미는 그냥 사전 뜻이다."
    r = client.put("/api/personas/objects-meaning", json=body)
    assert r.status_code == 200, r.text
    saved = client.get("/api/personas/objects-meaning").json()
    assert saved["personas"][0]["misconception"] == "의미는 그냥 사전 뜻이다."


def test_prompt_forbids_giving_the_answer():
    from app.lesson_ingest import ingest_hwp
    from app.llm import build_prompt

    lesson = client.get("/api/lesson/objects-meaning").json()
    from app.models import LessonSpec

    spec = LessonSpec(**lesson)
    personas = client.get("/api/personas/objects-meaning").json()["personas"]
    prompt = build_prompt(spec, personas, "concept", "물건의 의미는 무엇일까요?")
    joined = "\n".join(p["content"] for p in prompt)
    assert "NEVER state the lesson's final answer" in joined


def test_llm_falls_back_when_ollama_is_unavailable(monkeypatch):
    from app.lesson_ingest import ingest_hwp
    from app.llm import generate_student_responses
    from app.models import LessonSpec

    lesson = LessonSpec(**client.get("/api/lesson/objects-meaning").json())
    personas = client.get("/api/personas/objects-meaning").json()["personas"]
    monkeypatch.setenv("LLM_MODE", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1/api/chat")
    result = generate_student_responses(lesson, personas, "concept", "물건의 의미는 무엇일까요?")
    assert result["mode"] == "mock_fallback"
    assert 1 <= len(result["students"]) <= 2


def test_bkt_moves_in_the_expected_direction():
    from app.bkt import update_mastery

    state = {"kc1": 0.4}
    update_mastery(state, "kc1", True)
    assert state["kc1"] > 0.4
    update_mastery(state, "kc1", False)
    assert 0.01 <= state["kc1"] <= 0.99
    assert state["kc1"] < 0.99


def test_turn_updates_kt_across_turns():
    session = "bkt-test"
    first = client.post(
        "/api/turn",
        json={
            "session_id": session,
            "lesson_id": "objects-meaning",
            "phase_id": "concept",
            "teacher_utterance": "물건의 의미는 무엇일까요?",
        },
    ).json()
    first_kt = first["kt"]
    second = client.post(
        "/api/turn",
        json={
            "session_id": session,
            "lesson_id": "objects-meaning",
            "phase_id": "concept",
            "teacher_utterance": "왜 그렇게 생각했나요?",
        },
    ).json()
    second_kt = second["kt"]
    assert first_kt and second_kt
    assert any(
        second_kt[pid][kc] != first_kt[pid][kc]
        for pid in first_kt
        for kc in first_kt[pid]
    )
