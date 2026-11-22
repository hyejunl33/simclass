from __future__ import annotations

import base64
import json
import re
import tempfile
from pathlib import Path

from hwpx import HwpxDocument

from .models import KnowledgeComponent, LessonSpec, Misconception, Phase

ROOT = Path(__file__).resolve().parents[2]
KNOWN_LESSON = ROOT / "fixtures" / "lesson_plans" / "objects_meaning.json"

PHASE_IDS = {
    "학습 문제 확인": "intro",
    "개념 형성": "concept",
    "자료 해석": "interpretation",
    "원리 적용": "application",
}


def _clean(text: str) -> str:
    if not text:
        return ""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xE000 <= code <= 0xF8FF or code >= 0xF0000:
            continue
        out.append(ch)
    return "".join(out).replace("\r", "")


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in _clean(text).split("\n") if ln.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _parse_phase_cell(cell: str) -> tuple[str, int]:
    text = _clean(cell).replace("\n", " ")
    minutes_match = re.search(r"\((\d+)\s*[′']?\)", text)
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    name = re.sub(r"\([^)]*\)", "", text)
    name = re.sub(r"[\s/]+", " ", name).strip()
    for known in PHASE_IDS:
        if known in name:
            return known, minutes
    return name, minutes


def _strip_bullet(line: str) -> str:
    return re.sub(r"^[\s◦·\-–—]+", "", line).strip()


def parse_rows(rows: list[list[str]], filename: str = "") -> LessonSpec:
    if len(rows) < 4:
        raise ValueError("Lesson plan table is too short")

    header = rows[1]
    unit = _clean(header[0]).strip()
    topic = _clean(header[2]).strip()
    lesson_no = _clean(header[3]).strip()
    pages = _clean(header[4]).strip()

    phase_order: list[str] = []
    phases: dict[str, Phase] = {}
    current_name = ""

    for row in rows[3:]:
        raw_phase = row[0] if len(row) > 0 else ""
        name, minutes = _parse_phase_cell(raw_phase)
        if name:
            current_name = name
        if not current_name:
            continue

        phase = phases.get(current_name)
        if phase is None:
            phase = Phase(
                id=PHASE_IDS.get(current_name, f"phase-{len(phases) + 1}"),
                name=current_name,
                minutes=minutes,
            )
            phases[current_name] = phase
            phase_order.append(current_name)
        elif minutes:
            phase.minutes = max(phase.minutes, minutes)

        center = _lines(row[1] if len(row) > 1 else "")
        activities = _lines(row[2] if len(row) > 2 else "")
        materials_notes = row[3] if len(row) > 3 and row[3].strip() else (
            row[4] if len(row) > 4 else ""
        )
        mn_lines = _lines(materials_notes)

        phase.activities.extend(center)
        phase.activities.extend(activities)
        phase.activities = _dedupe(phase.activities)

        for line in activities + center:
            if "?" in line:
                phase.teacher_questions.append(_strip_bullet(line))
            if line.strip().startswith("-"):
                phase.expected_responses.append(_strip_bullet(line))
        phase.teacher_questions = _dedupe(phase.teacher_questions)
        phase.expected_responses = _dedupe(phase.expected_responses)

        for line in mn_lines:
            if any(ord(ch) >= 0xF0000 for ch in line) or "□" in line:
                phase.materials.append(_strip_bullet(line))
            elif line.startswith("◦"):
                phase.notes.append(_strip_bullet(line))
        phase.materials = _dedupe(phase.materials)
        phase.notes = _dedupe(phase.notes)

    ordered = [phases[name] for name in phase_order if name in PHASE_IDS]
    ordered += [phases[name] for name in phase_order if name not in PHASE_IDS]
    duration = sum(p.minutes for p in ordered)

    kcs: list[KnowledgeComponent] = []
    misconceptions: list[Misconception] = []
    lesson_id = "lesson-" + re.sub(r"[^a-z0-9]+", "-", f"{unit}-{topic}".lower()).strip("-")
    known = False
    if "1-2-약속" in unit and ("의미" in topic or "쓰레기" in topic):
        if KNOWN_LESSON.exists():
            profile = json.loads(KNOWN_LESSON.read_text(encoding="utf-8"))
            lesson_id = profile["id"]
            topic = profile["topic"]
            kcs = [KnowledgeComponent(**kc) for kc in profile["knowledge_components"]]
            misconceptions = [Misconception(**m) for m in profile["misconceptions"]]
            known = True

    needs_review = (
        not known
        or len(ordered) < 4
        or duration < 35
        or any(p.minutes == 0 for p in ordered)
        or not kcs
        or not misconceptions
    )

    return LessonSpec(
        id=lesson_id,
        unit=unit or "미상",
        topic=topic or "미상",
        lesson_no=lesson_no,
        pages=pages,
        duration_min=duration or 40,
        phases=ordered,
        knowledge_components=kcs,
        misconceptions=misconceptions,
        needs_review=needs_review,
        source_filename=filename,
    )


def ingest_hwp(data: bytes, filename: str = "") -> LessonSpec:
    if not data:
        raise ValueError("Empty HWP file")
    if not (data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or data[:2] == b"PK"):
        raise ValueError("Unsupported file format: expected HWP/HWPX")

    suffix = ".hwpx" if data[:2] == b"PK" else ".hwp"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fp:
        fp.write(data)
        path = Path(fp.name)
    try:
        doc = HwpxDocument.open(str(path))
        if not doc.tables:
            raise ValueError("No lesson-plan table found")
        table = doc.tables[0]
        rows = [
            [table.cell(r, c).text for c in range(table.column_count)]
            for r in range(table.row_count)
        ]
        doc.close()
        return parse_rows(rows, filename=filename)
    finally:
        path.unlink(missing_ok=True)


def decode_ingest(data_base64: str, filename: str = "") -> LessonSpec:
    try:
        data = base64.b64decode(data_base64, validate=True)
    except Exception as exc:
        raise ValueError("Invalid base64 payload") from exc
    return ingest_hwp(data, filename=filename)
