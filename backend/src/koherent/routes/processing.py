import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Student
from koherent.pipeline.process import NoAudioError, process_lecture
from koherent.schemas import ProcessResult

router = APIRouter(prefix="/lectures", tags=["processing"])


@router.post("/{lecture_id}/process", response_model=ProcessResult)
def process(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> ProcessResult:
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
