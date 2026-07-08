import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.config import settings
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Note, Student
from koherent.pipeline.process import NoAudioError, process_lecture
from koherent.pipeline.report import is_anomaly
from koherent.routes.access import load_lecture_for_student
from koherent.schemas import LectureReport, NoteReportItem, ProcessResult

router = APIRouter(prefix="/lectures", tags=["processing"])


@router.post("/{lecture_id}/process", response_model=ProcessResult)
def process(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> ProcessResult:
    load_lecture_for_student(lecture_id, current, db)
    try:
        summary = process_lecture(lecture_id, db, ai)
    except LookupError:
        raise HTTPException(status_code=404, detail="Lecture not found")
    except NoAudioError:
        raise HTTPException(status_code=400, detail="Lecture has no audio to process")
    return ProcessResult(
        transcript_id=summary.transcript_id,
        chunk_count=summary.chunk_count,
        note_count=summary.note_count,
        alignment_count=summary.alignment_count,
    )


@router.get("/{lecture_id}/report", response_model=LectureReport)
def report(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> LectureReport:
    load_lecture_for_student(lecture_id, current, db)

    notes = list(
        db.scalars(
            select(Note).where(Note.lecture_id == lecture_id, Note.student_id == current.id)
        )
    )
    items: list[NoteReportItem] = []
    for note in notes:
        alignment = note.alignment
        chunk = alignment.chunk if alignment is not None else None
        similarity = alignment.similarity if alignment is not None else None
        items.append(
            NoteReportItem(
                note_id=note.id,
                student_id=note.student_id,
                note_content=note.content,
                client_timestamp_ms=note.client_timestamp_ms,
                matched_chunk_index=chunk.chunk_index if chunk is not None else None,
                matched_content=chunk.content if chunk is not None else None,
                matched_start_ms=chunk.start_ms if chunk is not None else None,
                matched_end_ms=chunk.end_ms if chunk is not None else None,
                similarity=similarity,
                anomaly=is_anomaly(similarity, settings.anomaly_threshold),
            )
        )
    return LectureReport(
        lecture_id=lecture_id, threshold=settings.anomaly_threshold, items=items
    )
