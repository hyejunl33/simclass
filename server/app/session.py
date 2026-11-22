from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from .models import LessonSpec, Phase


class TranscriptEntry(BaseModel):
    t: float
    phase_id: str
    phase_name: str
    speaker: str
    name: str = ""
    text: str
    student_id: str = ""
    state: str = ""
    audio_sec: float = 0.0
    kt: dict[str, dict[str, float]] = Field(default_factory=dict)


class KTSnapshot(BaseModel):
    t: float
    phase_id: str
    kt: dict[str, dict[str, float]]


class PhaseEvent(BaseModel):
    phase_id: str
    phase_name: str
    at: float


class PhaseTiming(BaseModel):
    id: str
    name: str
    planned_min: int
    actual_sec: float
    entries: int


class SessionState(BaseModel):
    id: str
    lesson_id: str
    lesson: LessonSpec
    started_at: float
    ended_at: float | None = None
    phase_index: int = 0
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    kt_timeline: list[KTSnapshot] = Field(default_factory=list)
    phase_events: list[PhaseEvent] = Field(default_factory=list)
    kt: dict[str, dict[str, float]] = Field(default_factory=dict)

    @property
    def phase(self) -> Phase | None:
        if not self.lesson.phases:
            return None
        idx = max(0, min(self.phase_index, len(self.lesson.phases) - 1))
        return self.lesson.phases[idx]

    @property
    def completed(self) -> bool:
        return self.ended_at is not None

    def elapsed(self, now: float | None = None) -> float:
        now = time.time() if now is None else now
        end = self.ended_at or now
        return round(max(0.0, end - self.started_at), 1)


class SessionStartRequest(BaseModel):
    lesson_id: str = "objects-meaning"
    session_id: str | None = None


class SessionStatus(BaseModel):
    id: str
    lesson_id: str
    phase_index: int
    phase_id: str
    phase_name: str
    phase_planned_min: int
    phase_elapsed_sec: float
    phase_remaining_sec: float
    elapsed_sec: float
    total_planned_sec: int
    session_remaining_sec: float
    completed: bool


class SessionSummary(BaseModel):
    id: str
    lesson_id: str
    elapsed_sec: float
    turns: int
    student_turns: int
    phases_completed: int
    completed: bool


class ReplayResponse(BaseModel):
    id: str
    lesson_id: str
    topic: str
    duration_sec: float
    planned_sec: int
    completed: bool
    phases: list[PhaseTiming]
    transcript: list[TranscriptEntry]
    kt_timeline: list[KTSnapshot]
    final_kt: dict[str, dict[str, float]]


def new_session(lesson: LessonSpec, session_id: str | None = None) -> SessionState:
    started = time.time()
    sid = session_id or f"session-{int(started * 1000)}"
    session = SessionState(
        id=sid,
        lesson_id=lesson.id,
        lesson=lesson,
        started_at=started,
    )
    phase = session.phase
    if phase:
        session.phase_events.append(
            PhaseEvent(phase_id=phase.id, phase_name=phase.name, at=0.0)
        )
    return session


def status(session: SessionState) -> SessionStatus:
    elapsed = session.elapsed()
    phase = session.phase
    phase_started = 0.0
    if session.phase_events:
        phase_started = session.phase_events[-1].at
    phase_elapsed = round(max(0.0, elapsed - phase_started), 1)
    planned = phase.minutes * 60 if phase else 0
    total_planned = sum(p.minutes for p in session.lesson.phases) * 60 or 2400
    return SessionStatus(
        id=session.id,
        lesson_id=session.lesson_id,
        phase_index=session.phase_index,
        phase_id=phase.id if phase else "",
        phase_name=phase.name if phase else "",
        phase_planned_min=phase.minutes if phase else 0,
        phase_elapsed_sec=phase_elapsed,
        phase_remaining_sec=round(max(0.0, planned - phase_elapsed), 1),
        elapsed_sec=elapsed,
        total_planned_sec=total_planned,
        session_remaining_sec=round(max(0.0, total_planned - elapsed), 1),
        completed=session.completed,
    )


def advance(session: SessionState) -> SessionStatus:
    if session.completed:
        raise ValueError("Session already ended")
    if session.phase_index + 1 < len(session.lesson.phases):
        session.phase_index += 1
        phase = session.phase
        if phase:
            session.phase_events.append(
                PhaseEvent(
                    phase_id=phase.id,
                    phase_name=phase.name,
                    at=session.elapsed(),
                )
            )
    return status(session)


def end_session(session: SessionState) -> SessionSummary:
    if session.ended_at is None:
        session.ended_at = time.time()
    teacher_turns = sum(1 for e in session.transcript if e.speaker == "teacher")
    student_turns = sum(1 for e in session.transcript if e.speaker == "student")
    return SessionSummary(
        id=session.id,
        lesson_id=session.lesson_id,
        elapsed_sec=session.elapsed(),
        turns=teacher_turns,
        student_turns=student_turns,
        phases_completed=len(session.phase_events),
        completed=True,
    )


def replay(session: SessionState) -> ReplayResponse:
    duration = session.elapsed()
    events = session.phase_events or []
    phases: list[PhaseTiming] = []
    for i, phase in enumerate(session.lesson.phases):
        if i >= len(events):
            actual = 0.0
        else:
            start = events[i].at
            end = events[i + 1].at if i + 1 < len(events) else duration
            actual = round(max(0.0, end - start), 1)
        phases.append(
            PhaseTiming(
                id=phase.id,
                name=phase.name,
                planned_min=phase.minutes,
                actual_sec=actual,
                entries=sum(1 for e in session.transcript if e.phase_id == phase.id),
            )
        )
    planned = sum(p.minutes for p in session.lesson.phases) * 60 or 2400
    return ReplayResponse(
        id=session.id,
        lesson_id=session.lesson_id,
        topic=session.lesson.topic,
        duration_sec=duration,
        planned_sec=planned,
        completed=session.completed,
        phases=phases,
        transcript=session.transcript,
        kt_timeline=session.kt_timeline,
        final_kt=session.kt,
    )


def record_turn(
    session: SessionState,
    teacher_text: str,
    students: list[dict[str, Any]],
    phase_id: str,
    kt: dict[str, dict[str, float]],
    audio_sec: float = 0.0,
) -> None:
    phase = next(
        (p for p in session.lesson.phases if p.id == phase_id),
        session.phase,
    )
    phase_name = phase.name if phase else phase_id
    t = session.elapsed()
    session.transcript.append(
        TranscriptEntry(
            t=t,
            phase_id=phase_id,
            phase_name=phase_name,
            speaker="teacher",
            name="교사",
            text=teacher_text,
            audio_sec=audio_sec,
            kt=_copy_kt(kt),
        )
    )
    for s in students:
        session.transcript.append(
            TranscriptEntry(
                t=t,
                phase_id=phase_id,
                phase_name=phase_name,
                speaker="student",
                name=str(s.get("name", "")),
                text=str(s.get("text", "")),
                student_id=str(s.get("id", "")),
                state=str(s.get("state", "")),
                kt=_copy_kt(kt),
            )
        )
    session.kt_timeline.append(
        KTSnapshot(t=t, phase_id=phase_id, kt=_copy_kt(kt))
    )


def _copy_kt(kt: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {pid: dict(values) for pid, values in kt.items()}
