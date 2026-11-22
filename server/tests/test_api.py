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
