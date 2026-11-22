# SimClass protocol

The first tracer bullet uses HTTP. The real-time path adds WebSocket.

## HTTP (MVP)

### `GET /health`

```json
{"ok": true, "mode": "mock"}
```

### `POST /api/turn`

Request:

```json
{
  "session_id": "demo-1",
  "lesson_id": "objects-meaning",
  "phase_id": "concept",
  "teacher_utterance": "물건의 의미는 무엇일까요?",
  "personas": ["harin", "junseo", "minji"]
}
```

Response:

```json
{
  "students": [
    {
      "id": "harin",
      "name": "하린",
      "text": "국어사전에 나오는 뜻이요?",
      "state": "thinking",
      "mastery": {"kc1": 0.62}
    }
  ],
  "kt": {
    "harin": {"kc1": 0.62}
  }
}
```

## WebSocket (target)

`ws://<mac-mini>:8000/ws/session`

### Client → server

```json
{"type": "session.start", "lesson_id": "objects-meaning", "personas": "fixture"}
{"type": "teacher.utterance", "text": "물건의 의미는 무엇일까요?", "turn_id": 1}
{"type": "teacher.audio", "format": "pcm16", "sample_rate": 16000, "data_base64": "..."}
{"type": "session.end"}
```

### Server → client

```json
{"type": "session.ready", "session_id": "...", "lesson": {...}, "personas": [...]}
{"type": "asr.result", "turn_id": 1, "text": "물건의 의미는 무엇일까요?"}
{"type": "student.responses", "turn_id": 1, "students": [...]}
{"type": "kt.update", "state": {...}}
{"type": "feedback.ready", "report": {...}}
{"type": "error", "code": "asr_unavailable", "message": "..."}
```

## Audio

- 16 kHz mono PCM16.
- Push-to-talk: the client sends one utterance chunk when the teacher releases
  the key. VAD is optional.
- The server returns an `asr.result` before `student.responses`.
- If ASR is unavailable, the client may send `teacher.utterance` text instead.

## Failure modes

- ASR failure → `error.asr_unavailable`; UI falls back to text.
- LLM failure → cached/mock student response; UI shows a subtle “mock” badge.
- Mac mini offline → client uses local cache; the demo must not dead-end.

## Contract tests

- Validate every message against the JSON shapes above.
- Ensure `student.responses` never contains a final answer to the lesson.
- Ensure `feedback.ready` is only emitted after `session.end`.
