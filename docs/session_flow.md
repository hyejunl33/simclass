# 40-minute session flow and replay

The demo runs a full 40-minute 즐거운 생활 lesson with the phase structure from
the lesson plan:

| Phase | Planned |
|---|---|
| 학습 문제 확인 | 5 min |
| 개념 형성 | 17 min |
| 자료 해석 | 12 min |
| 원리 적용 | 6 min |

The timer is real time. The teacher can advance a phase manually from the UI,
or the client advances automatically when the current phase runs out. The last
phase ends the session automatically.

## Server API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/session/start` | Create a session; returns the current phase and remaining time |
| GET | `/api/session/{id}` | Current phase, elapsed time, remaining time |
| POST | `/api/session/{id}/advance` | Move to the next phase |
| POST | `/api/session/{id}/end` | End the session and return a summary |
| GET | `/api/session/{id}/replay` | Transcript, KT timeline, and phase timings |

`POST /api/turn` records the teacher utterance and each student response into the
session transcript and appends a KT snapshot after the BKT update.

Example:

```bash
curl -X POST http://127.0.0.1:8010/api/session/start \
  -H 'Content-Type: application/json' \
  -d '{"lesson_id":"objects-meaning","session_id":"demo-1"}'

curl -X POST http://127.0.0.1:8010/api/turn \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","lesson_id":"objects-meaning","phase_id":"intro","teacher_utterance":"지난 시간에 무엇을 배웠나요?"}'

curl -X POST http://127.0.0.1:8010/api/session/demo-1/advance
curl -X POST http://127.0.0.1:8010/api/session/demo-1/end
curl http://127.0.0.1:8010/api/session/demo-1/replay
```

The replay payload contains:

- `transcript`: timestamped teacher/student turns with the phase and KT snapshot
- `phases`: planned minutes, actual seconds, and utterance count per phase
- `kt_timeline`: KT snapshots over time
- `final_kt`: final mastery per persona and knowledge component

## Processing controls

| Control | Action |
|---|---|
| 수업 시작 / 새 세션 | Start a session; after it ends, start a second run with the same lesson and personas |
| 다음 단계 | Advance immediately (practice/demo) |
| 수업 종료 | End and load the replay |
| 리플레이 | End (if needed) and open the transcript + KT timeline |
| 대화로 | Return from replay to the live transcript |
| Click a student card | Cycle the selected misconception and persist the persona |
| Hold 음성 입력 | Record a teacher utterance, run ASR, and send the turn |

Running the same lesson plan with the same personas twice is interpreted as a
**practice effect**, not transfer.
