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
