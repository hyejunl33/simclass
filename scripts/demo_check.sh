#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
JUDGE="${1:-}"

python3 - "$BASE_URL" "$JUDGE" <<'PY'
import json
import sys
import time
import urllib.request

base = sys.argv[1].rstrip("/")
run_judge = sys.argv[2] == "--judge"
errors = []


def call(path, method="GET", body=None, timeout=120, tries=4):
    last = None
    for attempt in range(tries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(
                base + path,
                data=data,
                method=method,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as res:
                raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
        except Exception as exc:
            last = exc
            time.sleep(1.0 + attempt)
    raise last


def check(name, fn):
    try:
        fn()
        print(f"PASS  {name}")
    except Exception as exc:
        errors.append(f"{name}: {exc}")
        print(f"FAIL  {name}: {exc}")


def health():
    body = call("/health")
    assert body["ok"] is True, body
    assert body["version"].startswith("0."), body


def lesson():
    body = call("/api/lesson/objects-meaning")
    assert len(body["phases"]) == 4, body
    assert body["duration_min"] == 40, body


def personas():
    body = call("/api/personas/objects-meaning")
    assert len(body["personas"]) == 3, body


def audio_adapters():
    import base64

    try:
        asr = call(
            "/api/asr",
            "POST",
            {"filename": "smoke.wav", "data_base64": base64.b64encode(b"RIFF0000WAVE").decode()},
        )
        print(f"      ASR mode: {asr.get('mode')} · text: {asr.get('text', '')[:40]}")
    except Exception as exc:
        print(f"      ASR unavailable (allowed in mock): {exc}")
    try:
        req = urllib.request.Request(
            base + "/api/tts",
            data=json.dumps({"text": "안녕하세요"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            print(f"      TTS HTTP {res.status}, {res.headers.get('content-type')}")
    except Exception as exc:
        print(f"      TTS unavailable (allowed in mock): {exc}")


def sample():
    replay = call("/api/sample/replay")
    assert replay["completed"] is True, replay
    assert len(replay["transcript"]) >= 8, replay
    md = urllib.request.urlopen(base + "/api/sample/report.md", timeout=30).read().decode()
    assert "공식 채점표가 아닙니다" in md


def session_flow():
    sid = f"smoke-{int(time.time())}"
    start = call("/api/session/start", "POST", {"lesson_id": "objects-meaning", "session_id": sid})
    assert start["phase_id"] == "intro", start
    turn = call(
        "/api/turn",
        "POST",
        {
            "session_id": sid,
            "lesson_id": "objects-meaning",
            "phase_id": "intro",
            "teacher_utterance": "지난 시간에 무엇을 배웠나요?",
            "audio_sec": 2.5,
        },
        timeout=180,
    )
    assert 1 <= len(turn["students"]) <= 2, turn
    call(f"/api/session/{sid}/advance", "POST", {})
    call(f"/api/session/{sid}/end", "POST", {})
    replay = call(f"/api/session/{sid}/replay")
    assert replay["completed"] is True, replay
    assert replay["transcript"], replay
    print(f"      session: {sid} · turns: {len(replay['transcript'])}")


def judge():
    sid = f"judge-smoke-{int(time.time())}"
    call("/api/session/start", "POST", {"lesson_id": "objects-meaning", "session_id": sid})
    call(
        "/api/turn",
        "POST",
        {
            "session_id": sid,
            "lesson_id": "objects-meaning",
            "phase_id": "intro",
            "teacher_utterance": "지난 시간에 무엇을 배웠는지 말해볼까요?",
            "audio_sec": 3.0,
        },
        timeout=180,
    )
    call(f"/api/session/{sid}/end", "POST", {})
    job = call(f"/api/session/{sid}/judge/start", "POST", {})
    report = None
    for _ in range(300):
        time.sleep(2)
        current = call(f"/api/judge/{job['job_id']}", timeout=30)
        if current["status"] == "done":
            report = current["report"]
            break
        if current["status"] == "error":
            raise RuntimeError(current.get("error", "judge failed"))
    assert report is not None, "judge timed out"
    assert report["mode"] in {"ollama", "heuristic", "heuristic_fallback"}, report
    scored = [d for d in report["domains"] if d["status"] == "scored"]
    assert len(scored) >= 5, report
    for domain in scored:
        if domain["score"]:
            assert domain["evidence"], domain
    print(f"      judge mode: {report['mode']} · scores: "
          f"{[(d['id'], d['score']) for d in report['domains']]}")


print(f"SimClass demo check: {base}")
check("health", health)
check("lesson spec", lesson)
check("personas", personas)
check("audio adapters", audio_adapters)
check("sample session", sample)
check("session start/turn/advance/end/replay", session_flow)
if run_judge:
    check("rubric judge", judge)

print()
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
PY
