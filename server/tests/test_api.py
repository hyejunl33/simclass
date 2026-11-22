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


def test_asr_mock_returns_text():
    import base64

    r = client.post(
        "/api/asr",
        json={"filename": "a.wav", "data_base64": base64.b64encode(b"RIFF0000WAVE").decode()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "mock"
    assert "의미" in r.json()["text"]


def test_tts_mock_returns_no_content():
    r = client.post("/api/tts", json={"text": "국어사전에 나오는 뜻이요?"})
    assert r.status_code == 204


def test_session_flow_advance_end_replay():
    sid = "session-flow-test"
    start = client.post(
        "/api/session/start",
        json={"lesson_id": "objects-meaning", "session_id": sid},
    )
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["phase_id"] == "intro"
    assert body["total_planned_sec"] == 2400

    first = client.post(
        "/api/turn",
        json={
            "session_id": sid,
            "lesson_id": "objects-meaning",
            "phase_id": "intro",
            "teacher_utterance": "지난 시간에 무엇을 배웠나요?",
        },
    )
    assert first.status_code == 200, first.text
    assert 1 <= len(first.json()["students"]) <= 2

    advanced = client.post(f"/api/session/{sid}/advance")
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["phase_id"] == "concept"

    second = client.post(
        "/api/turn",
        json={
            "session_id": sid,
            "lesson_id": "objects-meaning",
            "phase_id": "concept",
            "teacher_utterance": "물건의 의미는 무엇일까요?",
        },
    )
    assert second.status_code == 200, second.text

    ended = client.post(f"/api/session/{sid}/end")
    assert ended.status_code == 200, ended.text
    assert ended.json()["completed"] is True
    assert ended.json()["turns"] == 2

    replay = client.get(f"/api/session/{sid}/replay")
    assert replay.status_code == 200, replay.text
    data = replay.json()
    assert data["completed"] is True
    assert len(data["phases"]) == 4
    assert data["phases"][0]["planned_min"] == 5
    assert sum(t["entries"] for t in data["phases"]) == len(data["transcript"])
    speakers = {e["speaker"] for e in data["transcript"]}
    assert speakers == {"teacher", "student"}
    assert len(data["kt_timeline"]) == 2
    assert set(data["final_kt"]) == {"harin", "junseo", "minji"}

    again = client.post(f"/api/session/{sid}/advance")
    assert again.status_code == 409


def test_unknown_session_is_404():
    assert client.get("/api/session/nope/replay").status_code == 404
    assert client.post("/api/session/nope/end").status_code == 404


def test_replay_unvisited_phases_have_zero_actual_time():
    sid = "session-unvisited-test"
    client.post("/api/session/start", json={"lesson_id": "objects-meaning", "session_id": sid})
    client.post(
        "/api/turn",
        json={
            "session_id": sid,
            "lesson_id": "objects-meaning",
            "phase_id": "intro",
            "teacher_utterance": "지난 시간에 무엇을 배웠나요?",
        },
    )
    client.post(f"/api/session/{sid}/end")
    phases = client.get(f"/api/session/{sid}/replay").json()["phases"]
    assert phases[0]["actual_sec"] >= 0
    assert phases[2]["actual_sec"] == 0
    assert phases[3]["actual_sec"] == 0


def _run_judged_session(session_id: str):
    client.post(
        "/api/session/start",
        json={"lesson_id": "objects-meaning", "session_id": session_id},
    )
    exchanges = [
        ("intro", "지난 시간에 무엇을 배웠나요?"),
        ("concept", "왜 그렇게 생각했어요? 어떻게 알 수 있을까요?"),
        ("concept", "친구의 생각과 비교해 볼까요?"),
        ("interpretation", "여러분의 경험과 연결해 볼까요?"),
    ]
    for phase_id, utterance in exchanges:
        if phase_id != "intro":
            client.post(f"/api/session/{session_id}/advance")
        client.post(
            "/api/turn",
            json={
                "session_id": session_id,
                "lesson_id": "objects-meaning",
                "phase_id": phase_id,
                "teacher_utterance": utterance,
            },
        )
    client.post(f"/api/session/{session_id}/end")


def test_judge_report_has_valid_evidence_and_markdown(tmp_path, monkeypatch):
    import app.judge as judge_mod

    monkeypatch.setattr(judge_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(judge_mod, "VALIDATION_DIR", tmp_path / "validation")

    sid = "judge-report-test"
    _run_judged_session(sid)

    r = client.post(f"/api/session/{sid}/judge")
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["mode"] == "heuristic"
    assert report["teacher_turns"] == 4
    domains = {d["id"]: d for d in report["domains"]}
    assert set(domains) == {
        "structure", "questioning", "interaction", "assessment", "conditions", "delivery"
    }
    assert domains["delivery"]["status"] == "not_assessed"
    assert domains["delivery"]["score"] is None

    transcript = client.get(f"/api/session/{sid}/replay").json()["transcript"]
    texts = ["".join(e["text"].split()) for e in transcript]
    for d in report["domains"]:
        if d["status"] != "scored" or not d["score"]:
            continue
        assert d["evidence"], d["id"]
        for ev in d["evidence"]:
            quote = "".join(ev["quote"].split())
            assert quote in texts[ev["turn_id"]], (d["id"], ev)

    md = client.get(f"/api/session/{sid}/report.md")
    assert md.status_code == 200, md.text
    assert "# SimClass 수업실연 피드백" in md.text
    assert "N/A" in md.text
    assert "공식 채점표가 아닙니다" in md.text
    assert (tmp_path / f"{sid}.json").exists()
    assert (tmp_path / f"{sid}.md").exists()


def test_judge_rejects_invalid_evidence_quotes():
    from app.judge import _validate_llm_domains
    from app.session import TranscriptEntry

    transcript = [
        TranscriptEntry(
            t=10, phase_id="concept", phase_name="개념 형성",
            speaker="teacher", name="교사", text="왜 그렇게 생각했어요?",
        ),
        TranscriptEntry(
            t=11, phase_id="concept", phase_name="개념 형성",
            speaker="student", name="하린", text="경험 때문이에요.", student_id="harin",
        ),
    ]
    payload = {
        "domains": [
            {
                "id": "questioning",
                "score": 3,
                "evidence": [{"turn_id": 0, "quote": "왜 그렇게 생각했어요?"}],
                "reason": "좋은 발문", "improvement": "유지",
            },
            {
                "id": "structure",
                "score": 2,
                "evidence": [{"turn_id": 0, "quote": "대화록에 없는 문장"}],
                "reason": "구조", "improvement": "정리",
            },
        ]
    }
    domains, errors, rejected = _validate_llm_domains(payload, transcript)
    by_id = {d.id: d for d in domains}
    assert by_id["questioning"].score == 3
    assert "대화록에 없는 문장" in rejected
    assert by_id["structure"].score == 0
    assert any("not found" in e for e in errors)


def test_human_validation_agreement(tmp_path, monkeypatch):
    import app.judge as judge_mod

    monkeypatch.setattr(judge_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(judge_mod, "VALIDATION_DIR", tmp_path / "validation")

    sid = "judge-validation-test"
    _run_judged_session(sid)
    report = client.post(f"/api/session/{sid}/judge").json()
    scores = {
        d["id"]: d["score"]
        for d in report["domains"]
        if d["status"] == "scored"
    }
    r = client.post(
        f"/api/validation/{sid}",
        json={"rater": "human-1", "scores": scores, "notes": "double coded"},
    )
    assert r.status_code == 200, r.text

    sample = client.get("/api/validation/sample?ratio=1.0")
    assert sample.status_code == 200, sample.text
    assert any(s["session_id"] == sid for s in sample.json())

    agreement = client.get("/api/validation/agreement")
    assert agreement.status_code == 200, agreement.text
    body = agreement.json()
    assert body["pairs"] == len(scores)
    assert body["exact_agreement"] == 1.0
    assert body["cohen_kappa"] == 1.0


def test_judge_accepts_speaker_prefixed_quotes():
    from app.judge import _find_quote
    from app.session import TranscriptEntry

    transcript = [
        TranscriptEntry(
            t=0, phase_id="intro", phase_name="학습 문제 확인",
            speaker="teacher", name="교사", text="지난 시간에 무엇을 배웠나요?",
        )
    ]
    assert _find_quote(transcript, "교사: 지난 시간에 무엇을 배웠나요?", 0) == 0
    assert _find_quote(transcript, "[0] 교사: 지난 시간에 무엇을 배웠나요?", 0) == 0
    assert _find_quote(transcript, "학생(하린): 다른 말", 0) is None


def test_judge_rejects_student_evidence_for_teacher_domains():
    from app.judge import _validate_llm_domains
    from app.session import TranscriptEntry

    transcript = [
        TranscriptEntry(
            t=0, phase_id="concept", phase_name="개념 형성",
            speaker="teacher", name="교사", text="왜 그렇게 생각했어요?",
        ),
        TranscriptEntry(
            t=1, phase_id="concept", phase_name="개념 형성",
            speaker="student", name="하린", text="경험 때문이에요.", student_id="harin",
        ),
    ]
    payload = {
        "domains": [
            {
                "id": "structure",
                "score": 2,
                "evidence": [{"turn_id": 1, "quote": "경험 때문이에요."}],
                "reason": "구조", "improvement": "정리",
            },
            {
                "id": "interaction",
                "score": 2,
                "evidence": [{"turn_id": 1, "quote": "경험 때문이에요."}],
                "reason": "상호작용", "improvement": "이름 부르기",
            },
        ]
    }
    domains, errors, rejected = _validate_llm_domains(payload, transcript)
    by_id = {d.id: d for d in domains}
    assert by_id["structure"].score == 0
    assert by_id["interaction"].score == 2
    assert "경험 때문이에요." in rejected
    assert any("teacher turn" in e for e in errors)


def test_judge_accepts_quotes_with_phase_suffix():
    from app.judge import _find_quote
    from app.session import TranscriptEntry

    transcript = [
        TranscriptEntry(
            t=0, phase_id="intro", phase_name="학습 문제 확인",
            speaker="teacher", name="교사", text="지난 시간에 무엇을 배웠나요?",
        )
    ]
    assert _find_quote(transcript, "교사: 지난 시간에 무엇을 배웠나요? (학습 문제 확인)", 0) == 0
