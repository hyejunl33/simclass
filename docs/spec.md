# SimClass — 제품/구현 스펙

## Problem Statement

예비교사는 수업실연을 준비하면서 실제 학생의 반응을 예측하고 즉각 대응하는
경험을 충분히 쌓기 어렵다. 기존 도구는 정적 지도안, 녹화 영상, 또는 범용 LLM
챗봇에 머문다. 범용 챗봇은 학생 페르소나의 사전 지식·오개념·수업 단계·이전
대화를 일관되게 유지하지 못하고, 교사가 원하는 정답을 먼저 말해버리는 경우가
많다. 수업 후 피드백도 “좋았어요” 같은 일반론에 그쳐, 초등임용 2차 수업실연의
평가 기준과 연결되지 않는다.

## Solution

예비교사가 즐생 수업안(HWP)을 업로드하면 SimClass가 이를 `LessonSpec`으로
구조화하고, 3명의 학생 페르소나를 생성한다. 교사가 실시간 음성으로 발문하면
Whisper ASR이 텍스트로 바꾸고, 로컬 LLM이 학생 페르소나·BKT 상태·수업 단계에
맞는 응답을 생성한다. Processing 앱은 교실, 학생 상태, 대화, 교사용 KT bar를
보여준다. 40분 세션이 끝나면 LLM judge가 **초등임용 2차 수업실연 기반
루브릭**으로 점수·증거 인용·개선안을 제공한다.

**파인튜닝은 하지 않는다.** 학습 데이터와 품질 메트릭이 아직 신뢰할 수준이
아니므로, 메인 연구는 프롬프트 기반 LLM + BKT + 실시간 ASR + 증거 기반 평가로
간다.

## User Stories

1. As a pre-service teacher, I want to upload a HWP lesson plan, so that I can
   rehearse the lesson I actually wrote.
2. As a pre-service teacher, I want the system to extract the unit, topic,
   phases, activities, teacher questions, materials, and notes, so that the
   simulation follows my plan.
3. As a pre-service teacher, I want to review and correct the extracted
   `LessonSpec`, so that parsing errors do not corrupt the simulation.
4. As a pre-service teacher, I want the system to propose three student
   personas with prior knowledge, misconceptions, confidence, and speech style,
   so that the classroom feels realistic.
5. As a pre-service teacher, I want to edit each persona and misconception, so
   that I can rehearse a specific class composition.
6. As a pre-service teacher, I want to start a 40-minute simulation, so that I
   can practice the full lesson flow.
7. As a pre-service teacher, I want to see a classroom view with three students,
   so that I know who I am addressing.
8. As a pre-service teacher, I want to speak my question in real time, so that
   the interaction feels like a lesson, not a chat window.
9. As a pre-service teacher, I want my speech transcribed automatically, so that
   I do not have to type while teaching.
10. As a pre-service teacher, I want a text fallback, so that the demo still
    works if the microphone or ASR fails.
11. As a pre-service teacher, I want one or two students to respond per turn, so
    that the pace stays realistic.
12. As a pre-service teacher, I want each student to stay in character across
    turns, so that the simulation does not feel like a generic chatbot.
13. As a pre-service teacher, I want students to reveal lesson-specific
    misconceptions naturally, so that I can practice responding to them.
14. As a pre-service teacher, I want the system to update each student’s
    knowledge state after a turn, so that the class reacts to my teaching.
15. As a pre-service teacher, I want a teacher-only KT panel with numeric
    mastery bars, so that I can see who is still struggling.
16. As a pre-service teacher, I want a phase timer for 도입/개념 형성/자료
    해석/원리 적용, so that I can practice time management.
17. As a pre-service teacher, I want the app to prompt the next phase, so that I
    do not lose the lesson structure.
18. As a pre-service teacher, I want student responses read aloud via TTS, so
    that the classroom feels alive.
19. As a pre-service teacher, I want to replay the session, so that I can review
    what I said and how students reacted.
20. As a pre-service teacher, I want to end the session at any time, so that I
    can stop and reflect.
21. As a pre-service teacher, I want rubric scores after the session, so that I
    know where I stand against lesson-demonstration criteria.
22. As a pre-service teacher, I want every score backed by quoted evidence, so
    that I can trust and verify the feedback.
23. As a pre-service teacher, I want two or three concrete improvement
    suggestions with example revised questions, so that I know what to change.
24. As a pre-service teacher, I want to see which misconceptions were surfaced
    and which were missed, so that I can plan the next lesson.
25. As a pre-service teacher, I want talk-move analysis (revoicing, pressing for
    reasoning, eliciting evidence, linking, wait time), so that I can improve
    classroom discourse.
26. As a pre-service teacher, I want to export a Markdown/JSON report, so that I
    can keep a record of my practice.
27. As a pre-service teacher, I want non-observable domains marked N/A, so that
    the system does not invent feedback about eye contact or board writing.
28. As a pre-service teacher, I want to run the same lesson plan twice with the
    same personas, so that I can see my practice effect.
29. As a pre-service teacher, I want to compare the two runs, so that I can see
    whether my questioning changed.
30. As a pre-service teacher, I want all audio and logs to stay on my local
    machines, so that my practice data is private.
31. As a pre-service teacher, I want a cached/mock fallback, so that a demo does
    not collapse if the Mac mini is unavailable.
32. As an instructor, I want a transparent rubric document, so that I can audit
    how the LLM judge scores a session.
33. As an instructor, I want 20–30% of sessions double-coded by humans, so that
    I can report inter-rater reliability.
34. As a developer, I want a stable turn API/WebSocket contract, so that the
    Processing client can switch between mock, local, and Mac mini servers.
35. As a developer, I want fixture lesson plans and personas, so that I can test
    without a real classroom.

## Implementation Decisions

### Architecture

- **Processing Java `.pde`** is the final client. It owns the classroom view,
  microphone capture, dialogue rendering, phase timer, and teacher-only KT panel.
- **FastAPI server** runs on the Mac mini. It owns `LessonSpec` parsing, persona
  generation, LLM orchestration, ASR, BKT, judging, and session storage.
- **p5.js** may be used only as a disposable prototype; it is not the deliverable.
- **Ollama** serves a prompt-only Qwen2.5-3B/7B model. No fine-tuning.
- **Whisper** (MLX or whisper.cpp) runs on the Mac mini for ASR.
- **macOS `say`** provides TTS for the demo; Piper is a later option.
- **SQLite** stores sessions, transcripts, and reports locally.

### Lesson plan ingestion

- HWP is converted to text/tables with a deterministic converter; the result is
  normalized into `LessonSpec`.
- `LessonSpec` captures grade, subject, unit, topic, lesson number, pages,
  duration, phases, activities, teacher questions, expected responses,
  materials, notes, knowledge components, and misconceptions.
- An LLM may propose the JSON, but a human must be able to review and correct it.
- The first fixture is the attached 2nd-grade 즐생 lesson, “물건의 의미는
  무엇일까요?”.

### Student personas

- Three personas per session. Each has a name, prior knowledge, target
  misconception, confidence, speech style, and initial BKT state.
- Personas are generated from the lesson spec and a small template library, then
  editable by the teacher.
- One or two students respond per teacher turn, selected by phase, addressed
  student, and persona state.

### Simulation

- Default session length is 40 minutes, organized by the lesson phases.
- The app shows a phase timer and prompts transitions, but the teacher can move
  on early.
- Teacher input: real-time voice via push-to-talk; text fallback.
- Student output: text bubbles + TTS. No student avatars with facial animation
  in the demo.
- The LLM must never provide the final answer to the teacher; it only plays
  students.

### Knowledge Tracing

- Four knowledge components for the first lesson: meaning of an object,
  experience/emotion, individual differences, and generalization of meaning.
- BKT parameters: initial mastery, learn, slip, guess. Personas start at
  different mastery levels.
- State updates after each student response using a deterministic heuristic plus
  BKT update; the state is passed back into the next prompt.
- Numeric mastery bars are teacher-only. Students do not see them.

### Evaluation rubric

- Domains: lesson structure, questioning/communication, student-centered
  interaction, assessment/feedback, condition/context response, and
  audio-observable delivery.
- Each domain uses 0–3 anchors with observable behavioral descriptors.
- The judge uses two stages: per-turn coding (question type, talk move, wait
  time, assessment language) and session-level rubric aggregation.
- Every score must include `evidence` with turn IDs and exact quotes. If there is
  no evidence, the score is `N/A`.
- Visual domains (eye contact, facial expression, board writing) are `N/A` in the
  demo because the demo has no camera/board input.
- The judge outputs JSON matching the rubric schema; invalid JSON is rejected and
  retried once.
- Human validation: two raters double-code 20–30% of sessions; report Cohen’s
  kappa / ICC.

### Protocol

- The first tracer bullet uses HTTP `POST /api/turn` for simplicity.
- The production path adds WebSocket `/ws/session` for streaming audio and
  events.
- The Processing client should not know whether the server is mock, Ollama, or
  Mac mini.

### Data and privacy

- HWP files, audio, and transcripts stay local. No cloud calls in the demo.
- The repo contains only synthetic/anonymized fixtures, not the original HWP.

## Testing Decisions

A good test checks external behavior: the API contract, the lesson spec shape,
the BKT transition, the rubric aggregation, and the evidence rule. Do not test
private implementation details.

- `LessonSpec` validation: required fields, phase minutes sum, unknown keys.
- Persona generation: three personas, one target misconception each, editable.
- Turn API: request/response schema, one/two student responses, no answer
  leakage.
- BKT: mastery increases/decreases in the expected direction; bounds 0–1.
- Rubric: score aggregation, `N/A` when evidence is missing, evidence quotes must
  exist in the transcript.
- WebSocket: session start, teacher turn, student response, session end.
- Mock adapters for LLM and ASR so CI never calls the network.
- Processing UI: manual visual check + a protocol harness that replays fixture
  sessions.

## Out of Scope

- Fine-tuning or training any model.
- Production deployment, authentication, multi-user accounts, cloud hosting.
- Eye contact, facial expression, gesture, or board-writing assessment.
- More than one lesson plan or more than one subject in the demo.
- Real elementary students; elementary learning outcomes are only an expected
  effect, not a measured outcome.
- Full HWP editing; only ingestion and correction of extracted fields.
- Mobile app or web deployment.

## Further Notes

- Target demo hardware: laptop (Processing client) + Mac mini M6 32GB (FastAPI,
  Ollama, Whisper, TTS).
- The first lesson is the attached 2nd-grade 즐생 plan about the meaning of
  objects.
- The demo must be resilient: if the Mac mini is down, use cached/mock responses.
- The thesis claims simulation/practice effects for pre-service teachers, not
  model quality improvement.
