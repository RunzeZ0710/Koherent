"""Lecture study artifacts: structured summaries and personalized review prompts.

The review endpoint is where the alignment layer pays off: a student's
anomalous / weakest notes — and what the transcript actually said at that
point — become the input for targeted review prompts, so the output is
personal, not generic.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.config import settings
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import LectureSummary, Note, Student, TranscriptChunk
from koherent.pipeline.prompts import (
    REVIEW_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    ReviewItem,
    build_review_prompt,
    build_summary_prompt,
)
from koherent.pipeline.report import is_anomaly
from koherent.routes.access import load_lecture_for_student
from koherent.schemas import LectureSummaryRead, ReviewResponse

router = APIRouter(prefix="/lectures", tags=["study"])

_REVIEW_FALLBACK_COUNT = 3


def _generate_or_502(ai: AIClient, system_prompt: str, user_prompt: str) -> str:
    try:
        return ai.generate(system_prompt, user_prompt)
    except Exception:
        raise HTTPException(status_code=502, detail="LLM generation failed")


@router.post("/{lecture_id}/summary", response_model=LectureSummaryRead)
def create_summary(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> LectureSummaryRead:
    lecture = load_lecture_for_student(lecture_id, current, db)
    if lecture.transcript is None:
        raise HTTPException(status_code=400, detail="Lecture has not been processed yet")
    chunks = list(
        db.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == lecture.transcript.id)
            .order_by(TranscriptChunk.chunk_index)
        )
    )
    content = _generate_or_502(
        ai, SUMMARY_SYSTEM_PROMPT, build_summary_prompt(lecture.title, [c.content for c in chunks])
    )
    summary = lecture.summary
    if summary is None:
        summary = LectureSummary(
            lecture_id=lecture.id, content=content, model=settings.nim_chat_model
        )
        db.add(summary)
    else:
        summary.content = content
        summary.model = settings.nim_chat_model
    db.commit()
    db.refresh(summary)
    return LectureSummaryRead(
        lecture_id=lecture.id,
        content=summary.content,
        model=summary.model,
        created_at=summary.created_at,
    )


@router.get("/{lecture_id}/summary", response_model=LectureSummaryRead)
def get_summary(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> LectureSummaryRead:
    lecture = load_lecture_for_student(lecture_id, current, db)
    if lecture.summary is None:
        raise HTTPException(status_code=404, detail="No summary generated yet")
    return LectureSummaryRead(
        lecture_id=lecture.id,
        content=lecture.summary.content,
        model=lecture.summary.model,
        created_at=lecture.summary.created_at,
    )


@router.post("/{lecture_id}/review", response_model=ReviewResponse)
def create_review(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> ReviewResponse:
    lecture = load_lecture_for_student(lecture_id, current, db)
    if lecture.transcript is None:
        raise HTTPException(status_code=400, detail="Lecture has not been processed yet")
    notes = list(
        db.scalars(
            select(Note).where(Note.lecture_id == lecture.id, Note.student_id == current.id)
        )
    )
    if not notes:
        raise HTTPException(status_code=400, detail="You have no notes in this lecture")

    def similarity_of(note: Note) -> float | None:
        return note.alignment.similarity if note.alignment is not None else None

    weak = [n for n in notes if is_anomaly(similarity_of(n), settings.anomaly_threshold)]
    if not weak:
        weak = sorted(notes, key=lambda n: similarity_of(n) or 0.0)[:_REVIEW_FALLBACK_COUNT]

    items = [
        ReviewItem(
            note_content=n.content,
            matched_content=n.alignment.chunk.content if n.alignment is not None else None,
            similarity=similarity_of(n),
        )
        for n in weak
    ]
    content = _generate_or_502(ai, REVIEW_SYSTEM_PROMPT, build_review_prompt(items))
    return ReviewResponse(
        lecture_id=lecture.id,
        content=content,
        weak_note_count=len(items),
        model=settings.nim_chat_model,
    )
