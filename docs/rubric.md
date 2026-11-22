# Lesson-demonstration rubric (초등임용 2차 수업실연 기반)

This rubric is **informed by** the public direction of the elementary teacher
employment exam (수업실연은 “교사로서의 학습지도 능력과 의사소통 능력”을
평가) and by widely used lesson-demonstration checklists. It is **not** an
official scoring sheet; official detailed criteria vary by year and region and
are not fully public. The rubric is intentionally transparent so a pre-service
teacher can audit every score.

## Scoring scale

- **3 — Strong**: the behavior is present, consistent, and clearly supported by
  evidence.
- **2 — Adequate**: present but uneven, brief, or only partially connected.
- **1 — Emerging**: attempted but vague, teacher-centered, or inconsistent.
- **0 — Not observed**: no evidence in the transcript/audio.
- **N/A — Not assessable**: the modality is not captured (e.g., eye contact).

## Domains

### 1. Lesson structure (수업 구조)

Observable indicators:

- Opens with review/motivation and states the learning problem.
- Phases (도입–전개–정리) are distinguishable and time is roughly balanced.
- Activities connect to the stated learning goal.
- The lesson closes with summary, assessment, and next-lesson notice.
- The lesson-plan conditions are reflected.

Evidence: phase transitions, teacher utterances that state goals/agenda, closing
moves.

### 2. Questioning and communication (발문·의사소통)

Observable indicators:

- Uses open questions (“왜 그렇게 생각했어요?”, “어떻게 알 수 있을까요?”).
- Presses for reasoning and evidence.
- Revoices or clarifies student ideas.
- Connects one student’s idea to another.
- Leaves wait time after a question.
- Uses age-appropriate, respectful language.

Evidence: teacher turns tagged with question type, talk move, wait time.

### 3. Student-centered interaction (학생 중심 상호작용)

Observable indicators:

- Addresses students by name and invites participation.
- Uses individual, pair, group, and whole-class structures appropriately.
- Circulates and supports individuals during activities (궤간순시).
- Responds to a specific student’s misconception.
- Involves quieter or struggling students.

Evidence: teacher turns + student responses; distribution of names; follow-up
moves.

### 4. Assessment and feedback (평가·피드백)

Observable indicators:

- States process-oriented assessment language.
- Checks understanding during the lesson.
- Gives specific, actionable feedback rather than “잘했어요”.
- Uses student responses to adjust the next move.

Evidence: assessment utterances, follow-ups, checks for understanding.

### 5. Condition and context response (상황·조건 대응)

Observable indicators:

- Addresses the lesson-plan conditions (materials, grouping, student needs).
- Responds to unexpected student answers or off-task behavior.
- Considers struggling, special-education, or multicultural students when
  relevant.

Evidence: teacher turns that mention conditions or adapt the plan.

### 6. Audio-observable delivery (전달 태도)

Observable indicators:

- Speech rate is comprehensible.
- Pauses after questions (wait time).
- Fillers/hesitations do not dominate.
- Polite/appropriate register.

Evidence: audio features + transcript timestamps.

**Not assessed in the demo**: eye contact, facial expression, gesture, board
writing, classroom movement. These require camera/video or manual observation and
must be marked `N/A`.

## Talk-move coding

Per teacher turn:

- `open_question`: why/how/what-if.
- `closed_question`: yes/no or single answer.
- `revoice`: restates a student idea.
- `press_reasoning`: asks for justification.
- `elicit_evidence`: asks how they know.
- `link`: connects two student ideas.
- `assess`: checks understanding.
- `feedback_specific`: concrete feedback.
- `wait_time`: seconds of silence after a question (audio).

## Judge output contract

```json
{
  "session_id": "string",
  "domains": [
    {
      "id": "questioning",
      "score": 2,
      "evidence": [
        {"turn_id": 4, "quote": "왜 그렇게 생각했어요?"}
      ],
      "reason": "2문장 이내, 증거와 점수 연결",
      "improvement": "다음 수업에서 쓸 수 있는 구체적 발문 예시"
    }
  ],
  "talk_moves": {"open_question": 5, "revoice": 2},
  "misconceptions": [
    {"id": "m1", "surfaced": true, "turn_ids": [3]}
  ],
  "not_assessed": ["eye_contact", "board_writing"]
}
```

Rules:

- The quote must appear in the transcript. A quote mismatch invalidates the
  evidence.
- No evidence → `score: 0` or `N/A`, never a guessed score.
- The judge may not infer visual behavior from text.
- The judge must not give the teacher the lesson’s final answer; feedback is about
  teaching moves.

## Implementation

The judge lives in `server/app/judge.py`; the API and validation harness are
documented in [`judge.md`](judge.md). `delivery` is scored from ASR speech
duration when voice input exists; visual domains remain `N/A`.

## Human validation

- Two raters independently code 20–30% of sessions.
- Report Cohen’s kappa for categorical talk moves and ICC for rubric scores.
- If agreement is low, revise the rubric anchors or the judge prompt; do not
  silently keep the score.
