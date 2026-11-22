from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .models import LessonSpec
from .session import SessionState, TranscriptEntry

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "reports"
VALIDATION_DIR = REPORTS_DIR / "validation"

DOMAIN_NAMES = {
    "structure": "수업 구조",
    "questioning": "발문·의사소통",
    "interaction": "학생 중심 상호작용",
    "assessment": "평가·피드백",
    "conditions": "상황·조건 대응",
}
SCORED_DOMAINS = list(DOMAIN_NAMES)
VISUAL_NOT_ASSESSED = [
    "eye_contact",
    "facial_expression",
    "gesture",
    "board_writing",
    "classroom_movement",
]

TALK_MOVES = [
    "open_question",
    "closed_question",
    "revoice",
    "press_reasoning",
    "elicit_evidence",
    "link",
    "assess",
    "feedback_specific",
]


class Evidence(BaseModel):
    turn_id: int
    quote: str


class DomainScore(BaseModel):
    id: str
    name: str
    status: str = "scored"  # scored | not_assessed
    score: int | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    reason: str = ""
    improvement: str = ""


class MisconceptionCoverage(BaseModel):
    id: str
    text: str
    surfaced: bool = False
    turn_ids: list[int] = Field(default_factory=list)


class JudgeReport(BaseModel):
    session_id: str
    lesson_id: str
    topic: str
    duration_sec: float
    teacher_turns: int
    student_turns: int
    domains: list[DomainScore]
    talk_moves: dict[str, int] = Field(default_factory=dict)
    misconceptions: list[MisconceptionCoverage] = Field(default_factory=list)
    not_assessed: list[str] = Field(default_factory=list)
    summary: str = ""
    mode: str = "heuristic"
    generated_at: float = Field(default_factory=time.time)
    validation: dict[str, Any] = Field(default_factory=dict)

    @property
    def overall(self) -> float | None:
        scores = [d.score for d in self.domains if d.status == "scored" and d.score is not None]
        return round(sum(scores) / len(scores), 2) if scores else None


class HumanCoding(BaseModel):
    rater: str = "rater-1"
    scores: dict[str, int]
    notes: str = ""


class ValidationSample(BaseModel):
    session_id: str
    topic: str
    template: dict[str, int]
    report_path: str


def _teacher_entries(transcript: list[TranscriptEntry]) -> list[tuple[int, TranscriptEntry]]:
    return [(i, e) for i, e in enumerate(transcript) if e.speaker == "teacher"]


def _student_entries(transcript: list[TranscriptEntry]) -> list[tuple[int, TranscriptEntry]]:
    return [(i, e) for i, e in enumerate(transcript) if e.speaker == "student"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _clean_quote(quote: str) -> str:
    text = (quote or "").strip().strip('"').strip("“”").strip("'")
    text = re.sub(r"^\s*\[\d+\]\s*", "", text)
    text = re.sub(r"^\s*(교사|학생(?:\([^)]*\))?)\s*:\s*", "", text)
    return text.strip()


def _matched_quote(quote: str, entry: TranscriptEntry) -> str | None:
    cleaned = _clean_quote(quote)
    variants = [cleaned, re.sub(r"\s*\([^()]*\)\s*$", "", cleaned)]
    target = _norm(entry.text)
    for variant in variants:
        value = variant.strip()
        if len(_norm(value)) >= 2 and _norm(value) in target:
            return value
    return None


def _quote_in_entry(quote: str, entry: TranscriptEntry) -> bool:
    cleaned = _clean_quote(quote)
    variants = [cleaned, re.sub(r"\s*\([^()]*\)\s*$", "", cleaned)]
    target = _norm(entry.text)
    for variant in variants:
        q = _norm(variant)
        if len(q) >= 2 and q in target:
            return True
    return False


def _find_quote(
    transcript: list[TranscriptEntry], quote: str, turn_id: int | None = None
) -> int | None:
    entries = (
        [(turn_id, transcript[turn_id])]
        if turn_id is not None and 0 <= turn_id < len(transcript)
        else list(enumerate(transcript))
    )
    for idx, entry in entries:
        if _quote_in_entry(quote, entry):
            return idx
    return None


def _moves_for(text: str) -> list[str]:
    moves: list[str] = []
    t = text or ""
    has_q = "?" in t
    if has_q:
        if any(w in t for w in ("왜", "어떻게", "어떤", "무엇", "생각", "까요", "일까")):
            moves.append("open_question")
        else:
            moves.append("closed_question")
    if any(w in t for w in ("왜", "근거", "이유")):
        moves.append("press_reasoning")
    if any(w in t for w in ("어떻게 알", "어떤 근거", "확인해")):
        moves.append("elicit_evidence")
    if any(w in t for w in ("다시 말", "그러니까", "정리하면")):
        moves.append("revoice")
    if any(w in t for w in ("친구", "다른", "누가", "서로", "모둠")):
        moves.append("link")
    if any(w in t for w in ("확인", "맞나", "정리", "해볼까", "평가")):
        moves.append("assess")
    if any(w in t for w in ("좋아", "잘했", "정확", "훌륭", "멋진")):
        moves.append("feedback_specific")
    return moves


def _pick(log: list[tuple[int, TranscriptEntry]], limit: int = 3) -> list[Evidence]:
    out: list[Evidence] = []
    for idx, entry in log[:limit]:
        quote = entry.text.strip()
        if quote:
            out.append(Evidence(turn_id=idx, quote=quote[:200]))
    return out


def _heuristic_domains(
    lesson: LessonSpec,
    transcript: list[TranscriptEntry],
) -> tuple[list[DomainScore], dict[str, int], list[MisconceptionCoverage], str]:
    teacher = _teacher_entries(transcript)
    students = _student_entries(transcript)
    counts = {m: 0 for m in TALK_MOVES}
    for _, e in teacher:
        for move in _moves_for(e.text):
            counts[move] += 1

    open_count = counts["open_question"]
    press_count = counts["press_reasoning"]
    assess_count = counts["assess"] + counts["feedback_specific"]
    cond_words = ("자료", "활동지", "모둠", "짝", "준비", "조건", "환경", "친구")
    cond_entries = [(i, e) for i, e in teacher if any(w in e.text for w in cond_words)]
    phase_cov = len({e.phase_id for _, e in teacher})
    student_ids = {e.student_id or e.name for _, e in students}

    structure_score = 3 if phase_cov >= 4 else 2 if phase_cov == 3 else 1 if phase_cov >= 1 else 0
    questioning_score = 3 if open_count >= 4 else 2 if open_count >= 2 else 1 if open_count >= 1 else 0
    if press_count >= 2 and questioning_score < 3:
        questioning_score += 1
    interaction_score = 3 if len(student_ids) >= 3 else 2 if len(student_ids) == 2 else 1 if len(student_ids) == 1 else 0
    assessment_score = 3 if assess_count >= 3 else 2 if assess_count == 2 else 1 if assess_count == 1 else 0
    condition_score = 3 if len(cond_entries) >= 2 else 2 if len(cond_entries) == 1 else 0

    question_entries = [(i, e) for i, e in teacher if "?" in e.text] or [
        (i, e) for i, e in teacher if counts["press_reasoning"] > 0
    ]
    interaction_entries = [
        (i, e)
        for i, e in teacher
        if any(w in e.text for w in ("친구", "모둠", "짝", "서로"))
    ]
    if not interaction_entries and students:
        interaction_entries = [students[0]]
    assessment_entries = [
        (i, e)
        for i, e in teacher
        if any(w in e.text for w in ("확인", "맞나", "정리", "해볼까", "평가", "좋아", "잘했"))
    ]

    domains = [
        DomainScore(
            id="structure",
            name=DOMAIN_NAMES["structure"],
            score=structure_score,
            evidence=_pick(phase_cov and [(teacher[0][0], teacher[0][1]), (teacher[-1][0], teacher[-1][1])] or []),
            reason=(
                f"발문이 {phase_cov}개 단계에 나타났습니다. "
                + ("도입과 마무리 발문이 확인됩니다." if len(teacher) >= 2 else "단계별 발문이 더 필요합니다.")
            ),
            improvement="도입에서 학습 문제를 명시하고, 정리 단계에서 배운 점과 다음 차시를 1문장으로 연결하세요.",
        ),
        DomainScore(
            id="questioning",
            name=DOMAIN_NAMES["questioning"],
            score=questioning_score,
            evidence=_pick(question_entries),
            reason=f"개방형 발문 {open_count}회, 이유를 묻는 발문 {press_count}회가 확인됩니다.",
            improvement="‘왜 그렇게 생각했어요?’, ‘어떻게 알 수 있을까요?’처럼 이유와 근거를 묻는 발문을 추가하세요.",
        ),
        DomainScore(
            id="interaction",
            name=DOMAIN_NAMES["interaction"],
            score=interaction_score,
            evidence=_pick(interaction_entries),
            reason=f"{len(student_ids)}명의 학생이 응답에 참여했습니다. 특정 학생에게 이름으로 말을 거는 장면은 더 확인이 필요합니다.",
            improvement="이름을 부르며 지목하고, 조용한 학생에게 쉬운 확인 질문을 먼저 던져 참여를 넓히세요.",
        ),
        DomainScore(
            id="assessment",
            name=DOMAIN_NAMES["assessment"],
            score=assessment_score,
            evidence=_pick(assessment_entries),
            reason=f"이해 확인·피드백으로 볼 수 있는 발문이 {assess_count}회 있습니다.",
            improvement="‘잘했어요’ 대신 ‘~라고 말한 근거가 좋아요. 그럼 ~는 어때요?’처럼 구체적으로 피드백하세요.",
        ),
        DomainScore(
            id="conditions",
            name=DOMAIN_NAMES["conditions"],
            score=condition_score,
            evidence=_pick(cond_entries),
            reason=(
                f"자료·모둠·조건과 관련된 발문이 {len(cond_entries)}회 확인됩니다."
                if cond_entries
                else "수업안의 자료·조건을 직접 언급한 발문이 확인되지 않았습니다."
            ),
            improvement="수업안의 자료와 유의점을 발문에 직접 연결하고, 예상 밖 반응에는 계획을 조정하는 발언을 넣으세요.",
        ),
        DomainScore(
            id="delivery",
            name="전달 태도(음성)",
            status="not_assessed",
            score=None,
            reason="이 데모는 음성 속도·쉼·추임새 같은 음향 특징을 저장하지 않아 전달 태도를 평가하지 않습니다.",
            improvement="음성 특징을 저장한 뒤 말 속도, 질문 후 쉼, 추임새 비율로 평가하세요.",
        ),
    ]

    misconceptions: list[MisconceptionCoverage] = []
    for m in lesson.misconceptions:
        hits = [
            idx
            for idx, e in students
            if _norm(m.text)[:8] and _norm(m.text)[:8] in _norm(e.text)
        ]
        misconceptions.append(
            MisconceptionCoverage(
                id=m.id,
                text=m.text,
                surfaced=bool(hits),
                turn_ids=hits,
            )
        )

    summary = (
        f"발문 {len(teacher)}회, 학생 응답 {len(students)}회, "
        f"{phase_cov}개 단계가 기록되었습니다."
    )
    return domains, counts, misconceptions, summary


def _dialogue(transcript: list[TranscriptEntry]) -> str:
    lines = []
    for i, e in enumerate(transcript):
        who = "교사" if e.speaker == "teacher" else f"학생({e.name})"
        lines.append(f"[{i}] {who}: {e.text} ({e.phase_name})")
    return "\n".join(lines)


def _call_ollama(messages: list[dict[str, str]], timeout: float = 90.0) -> dict[str, Any]:
    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    model = os.getenv("JUDGE_MODEL") or os.getenv(
        "OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M"
    )
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 1400},
    }
    with httpx.Client(timeout=timeout) as client:
        res = client.post(url, json=payload)
        res.raise_for_status()
        content = res.json()["message"]["content"]
    return json.loads(content)


def _stage1_prompt(lesson: LessonSpec, transcript: list[TranscriptEntry]) -> list[dict[str, str]]:
    teacher_lines = "\n".join(
        f"[{i}] {e.text} ({e.phase_name})"
        for i, e in enumerate(transcript)
        if e.speaker == "teacher"
    )
    system = (
        "You code teacher talk moves in a Korean elementary lesson transcript. "
        "Return JSON only."
    )
    user = f"""Lesson: {lesson.topic}
Allowed talk moves: {", ".join(TALK_MOVES)}.

Teacher turns:
{teacher_lines}

Return exactly:
{{"turns":[{{"turn_id":0,"moves":["open_question"],"note":""}}]}}
Code every teacher turn. Do not invent turn_ids. Use [] when no move applies."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _stage2_prompt(
    lesson: LessonSpec,
    transcript: list[TranscriptEntry],
    coded: dict[str, Any],
    errors: list[str] | None = None,
) -> list[dict[str, str]]:
    phase_summary = ", ".join(f"{p.name} {p.minutes}분" for p in lesson.phases)
    system = (
        "You are an instructional coach scoring a Korean pre-service teacher's "
        "lesson demonstration. Score only what is observable in the transcript. "
        "Evidence quotes must be copied verbatim from the transcript. Return JSON only."
    )
    error_text = ""
    if errors:
        error_text = "\nPrevious output had these problems; fix them:\n- " + "\n- ".join(errors)
    user = f"""Lesson: {lesson.topic} ({lesson.subject}, grade {lesson.grade})
Planned phases: {phase_summary}
Knowledge components: {", ".join(k.name for k in lesson.knowledge_components)}
Misconceptions: {"; ".join(m.text for m in lesson.misconceptions)}

Transcript:
{_dialogue(transcript)}

Stage-1 talk-move coding:
{json.dumps(coded, ensure_ascii=False)}

Score these five domains from 0 to 3:
- structure (수업 구조): review/motivation, learning problem, phase flow, closing.
- questioning (발문·의사소통): open questions, reasoning, revoice, linking.
- interaction (학생 중심 상호작용): participation, names, group/pair, quieter students.
- assessment (평가·피드백): checks for understanding, specific feedback, adjusting.
- conditions (상황·조건 대응): lesson-plan materials/conditions, unexpected responses.

Rules:
- 0 = not observed, 1 = emerging, 2 = adequate, 3 = strong.
- Every score above 0 needs at least one evidence quote that appears verbatim in the transcript.
- Use turn_id from the transcript brackets.
- Copy only the utterance text: no speaker label, no phase name.
- Evidence for structure, questioning, assessment, and conditions must come from a teacher turn.
- Interaction may cite a teacher or student turn.
- Do not score visual behavior or audio delivery.
- Write reasons and improvements in Korean, 1-2 sentences each.

Return JSON only:
{{"domains":[{{"id":"structure","score":2,"evidence":[{{"turn_id":0,"quote":"..."}}],"reason":"...","improvement":"..."}}],"misconceptions":[{{"id":"m1","surfaced":true,"turn_ids":[1]}}],"summary":"..."}}
Include exactly the five domain ids above.{error_text}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _validate_llm_domains(
    payload: dict[str, Any],
    transcript: list[TranscriptEntry],
) -> tuple[list[DomainScore], list[str], list[str]]:
    errors: list[str] = []
    rejected: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for raw in payload.get("domains", []):
        if isinstance(raw, dict) and raw.get("id") in SCORED_DOMAINS:
            by_id[str(raw["id"])] = raw
    domains: list[DomainScore] = []
    for domain_id in SCORED_DOMAINS:
        raw = by_id.get(domain_id)
        if raw is None:
            errors.append(f"missing domain: {domain_id}")
            continue
        try:
            score = int(raw.get("score"))
        except (TypeError, ValueError):
            errors.append(f"{domain_id}: score must be an integer 0-3")
            continue
        if score < 0 or score > 3:
            errors.append(f"{domain_id}: score out of range")
            continue
        evidence: list[Evidence] = []
        for item in raw.get("evidence", []) or []:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote", "")).strip()
            turn_id = item.get("turn_id")
            if isinstance(turn_id, str) and turn_id.strip().isdigit():
                turn_id = int(turn_id.strip())
            if not isinstance(turn_id, int):
                rejected.append(quote)
                errors.append(f"{domain_id}: turn_id must be an integer")
                continue
            found = _find_quote(transcript, quote, turn_id)
            if found is None:
                rejected.append(quote)
                continue
            if domain_id != "interaction" and transcript[found].speaker != "teacher":
                rejected.append(quote)
                continue
            matched = _matched_quote(quote, transcript[found]) or _clean_quote(quote)
            evidence.append(Evidence(turn_id=found, quote=matched[:220]))
        if score > 0 and not evidence:
            errors.append(f"{domain_id}: score {score} has no valid evidence")
        domains.append(
            DomainScore(
                id=domain_id,
                name=DOMAIN_NAMES[domain_id],
                score=score if evidence or score == 0 else 0,
                evidence=evidence,
                reason=str(raw.get("reason", "")).strip()[:400],
                improvement=str(raw.get("improvement", "")).strip()[:400],
            )
        )
    return domains, errors, rejected


def _llm_report(
    session: SessionState,
) -> JudgeReport:
    transcript = session.transcript
    lesson = session.lesson
    validated: dict[str, Any] = {"retries": 0, "rejected_quotes": []}

    coded = _call_ollama(_stage1_prompt(lesson, transcript))
    coded_turns = coded.get("turns", []) if isinstance(coded, dict) else []
    counts = {m: 0 for m in TALK_MOVES}
    for row in coded_turns:
        if not isinstance(row, dict):
            continue
        for move in row.get("moves", []) or []:
            if move in counts:
                counts[move] += 1
    if not counts or sum(counts.values()) == 0:
        for _, e in _teacher_entries(transcript):
            for move in _moves_for(e.text):
                counts[move] += 1

    errors: list[str] = []
    domains: list[DomainScore] = []
    rejected: list[str] = []
    for attempt in range(2):
        payload = _call_ollama(_stage2_prompt(lesson, transcript, coded, errors or None))
        domains, errors, rejected = _validate_llm_domains(payload, transcript)
        validated["retries"] = attempt
        if not errors:
            break
    if errors:
        validated["errors"] = errors[:8]
    validated["rejected_quotes"] = rejected[:8]

    if len(domains) < len(SCORED_DOMAINS):
        raise ValueError("LLM judge did not return all scored domains")

    domains.append(
        DomainScore(
            id="delivery",
            name="전달 태도(음성)",
            status="not_assessed",
            score=None,
            reason="음성 속도·쉼·추임새는 이 데모에서 저장하지 않아 평가하지 않습니다.",
            improvement="음성 특징을 저장한 뒤 말 속도, 질문 후 쉼, 추임새 비율로 평가하세요.",
        )
    )

    misconceptions: list[MisconceptionCoverage] = []
    raw_mis = {
        str(m.get("id")): m
        for m in payload.get("misconceptions", []) or []
        if isinstance(m, dict)
    }
    for m in lesson.misconceptions:
        hit = raw_mis.get(m.id, {})
        misconceptions.append(
            MisconceptionCoverage(
                id=m.id,
                text=m.text,
                surfaced=bool(hit.get("surfaced", False)),
                turn_ids=[int(x) for x in (hit.get("turn_ids") or []) if str(x).isdigit()],
            )
        )

    return JudgeReport(
        session_id=session.id,
        lesson_id=session.lesson_id,
        topic=lesson.topic,
        duration_sec=session.elapsed(),
        teacher_turns=len(_teacher_entries(transcript)),
        student_turns=len(_student_entries(transcript)),
        domains=domains,
        talk_moves=counts,
        misconceptions=misconceptions,
        not_assessed=VISUAL_NOT_ASSESSED + ["delivery_audio_features"],
        summary=str(payload.get("summary", "")).strip()[:600],
        mode="ollama",
        validation=validated,
    )


def judge_session(session: SessionState) -> JudgeReport:
    mode = os.getenv("LLM_MODE", "mock").strip().lower()
    if mode == "ollama":
        try:
            return _llm_report(session)
        except Exception as exc:
            report = _heuristic_report(session)
            report.mode = "heuristic_fallback"
            report.validation = {"fallback_reason": str(exc)[:300]}
            return report
    return _heuristic_report(session)


def _heuristic_report(session: SessionState) -> JudgeReport:
    transcript = session.transcript
    domains, counts, misconceptions, summary = _heuristic_domains(
        session.lesson, transcript
    )
    return JudgeReport(
        session_id=session.id,
        lesson_id=session.lesson_id,
        topic=session.lesson.topic,
        duration_sec=session.elapsed(),
        teacher_turns=len(_teacher_entries(transcript)),
        student_turns=len(_student_entries(transcript)),
        domains=domains,
        talk_moves=counts,
        misconceptions=misconceptions,
        not_assessed=VISUAL_NOT_ASSESSED + ["delivery_audio_features"],
        summary=summary,
        mode="heuristic",
    )


def to_markdown(report: JudgeReport) -> str:
    lines = [
        "# SimClass 수업실연 피드백",
        "",
        f"- 세션: `{report.session_id}`",
        f"- 수업: {report.topic}",
        f"- 시간: {report.duration_sec / 60:.1f}분",
        f"- 발문: {report.teacher_turns}회 · 학생 응답: {report.student_turns}회",
        f"- 판정 모드: `{report.mode}`",
        "",
        "## 요약",
        "",
        report.summary or "요약이 생성되지 않았습니다.",
        "",
        "## 영역별 점수",
        "",
        "| 영역 | 점수 | 이유 |",
        "|---|---|---|",
    ]
    for d in report.domains:
        score = "N/A" if d.status == "not_assessed" else str(d.score)
        lines.append(f"| {d.name} | {score} | {d.reason} |")

    lines += ["", "## 증거와 개선", ""]
    for d in report.domains:
        score = "N/A" if d.status == "not_assessed" else str(d.score)
        lines += [f"### {d.name} — {score}", ""]
        if d.evidence:
            for ev in d.evidence:
                lines.append(f"- `[발화 {ev.turn_id}]` \"{ev.quote}\"")
        else:
            lines.append("- 검증된 증거 인용이 없습니다.")
        if d.reason:
            lines += ["", f"이유: {d.reason}"]
        if d.improvement:
            lines += [f"개선: {d.improvement}"]
        lines.append("")

    lines += [
        "## 발화 이동",
        "",
        "| 이동 | 횟수 |",
        "|---|---|",
    ]
    for move, count in report.talk_moves.items():
        lines.append(f"| {move} | {count} |")

    lines += ["", "## 오개념 노출", ""]
    if report.misconceptions:
        for m in report.misconceptions:
            status = "노출" if m.surfaced else "미노출"
            turns = ", ".join(str(t) for t in m.turn_ids) or "-"
            lines.append(f"- {m.text} — **{status}** (발화 {turns})")
    else:
        lines.append("- 기록 없음")

    lines += ["", "## 평가하지 않은 영역", ""]
    lines.append(", ".join(report.not_assessed) if report.not_assessed else "없음")
    lines += [
        "",
        "> 이 리포트는 공식 채점표가 아닙니다. 공개된 수업실연 평가 방향을 참고해"
        " 교사가 스스로 점검하도록 만든 보조 도구이며, 모든 점수는 대화록에 나타난"
        " 증거와 함께 공개됩니다.",
        "",
    ]
    return "\n".join(lines)


def save_report(report: JudgeReport) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"{report.session_id}.json"
    md_path = REPORTS_DIR / f"{report.session_id}.md"
    json_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return md_path, json_path


def load_report(session_id: str) -> JudgeReport | None:
    path = REPORTS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    return JudgeReport(**json.loads(path.read_text(encoding="utf-8")))


def save_human_coding(session_id: str, coding: HumanCoding) -> Path:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    path = VALIDATION_DIR / f"{session_id}.{coding.rater}.json"
    path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "rater": coding.rater,
                "scores": coding.scores,
                "notes": coding.notes,
                "saved_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def validation_sample(ratio: float = 0.25) -> list[ValidationSample]:
    if not REPORTS_DIR.exists():
        return []
    reports = sorted(REPORTS_DIR.glob("*.json"))
    if not reports:
        return []
    count = max(1, round(len(reports) * max(0.0, min(1.0, ratio))))
    step = max(1, len(reports) // count)
    chosen = reports[::step][:count]
    samples: list[ValidationSample] = []
    for path in chosen:
        try:
            report = JudgeReport(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        samples.append(
            ValidationSample(
                session_id=report.session_id,
                topic=report.topic,
                template={
                    d.id: (d.score if d.status == "scored" and d.score is not None else -1)
                    for d in report.domains
                },
                report_path=str(path),
            )
        )
    return samples


def cohen_kappa(a: list[int], b: list[int]) -> float | None:
    if not a or len(a) != len(b):
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum(
        (a.count(label) / n) * (b.count(label) / n) for label in labels
    )
    if pe >= 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 3)


def agreement() -> dict[str, Any]:
    if not VALIDATION_DIR.exists():
        return {"pairs": 0, "exact_agreement": None, "cohen_kappa": None, "domains": {}}
    pairs: list[tuple[str, int, int]] = []
    for path in sorted(VALIDATION_DIR.glob("*.json")):
        try:
            human = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        report = load_report(str(human.get("session_id", "")))
        if report is None:
            continue
        machine = {d.id: d.score for d in report.domains if d.status == "scored"}
        for domain_id, human_score in (human.get("scores") or {}).items():
            if domain_id in machine and machine[domain_id] is not None:
                pairs.append((domain_id, int(human_score), int(machine[domain_id])))
    if not pairs:
        return {"pairs": 0, "exact_agreement": None, "cohen_kappa": None, "domains": {}}
    a = [p[1] for p in pairs]
    b = [p[2] for p in pairs]
    per_domain: dict[str, Any] = {}
    for domain_id in SCORED_DOMAINS:
        da = [p[1] for p in pairs if p[0] == domain_id]
        db = [p[2] for p in pairs if p[0] == domain_id]
        if da:
            per_domain[domain_id] = {
                "pairs": len(da),
                "exact_agreement": round(
                    sum(1 for x, y in zip(da, db) if x == y) / len(da), 3
                ),
                "cohen_kappa": cohen_kappa(da, db),
            }
    return {
        "pairs": len(pairs),
        "exact_agreement": round(sum(1 for x, y in zip(a, b) if x == y) / len(a), 3),
        "cohen_kappa": cohen_kappa(a, b),
        "domains": per_domain,
    }
