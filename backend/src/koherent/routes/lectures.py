import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from koherent.deps import get_current_student, get_db
from koherent.models import AudioRecording, Lecture, Note, Student
from koherent.routes.access import load_lecture_for_student
from koherent.schemas import (
    AudioRecordingRead,
    LectureCreate,
    LectureRead,
    LectureStatus,
    NoteCreate,
    NoteRead,
)
from koherent.storage import save_audio

router = APIRouter(prefix="/lectures", tags=["lectures"])

_ALLOWED_AUDIO_MIME_PREFIXES = ("audio/",)


@router.post("", response_model=LectureRead, status_code=status.HTTP_201_CREATED)
def start_lecture(
    payload: LectureCreate,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> Lecture:
    lecture = Lecture(
        class_id=current.class_id,
        title=payload.title,
        created_by_student_id=current.id,
    )
    db.add(lecture)
    db.commit()
    db.refresh(lecture)
    return lecture


@router.post("/{lecture_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def append_note(
    lecture_id: uuid.UUID,
    payload: NoteCreate,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> Note:
    lecture = load_lecture_for_student(lecture_id, current, db)
    note = Note(
        lecture_id=lecture.id,
        student_id=current.id,
        content=payload.content,
        client_timestamp_ms=payload.client_timestamp_ms,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.post(
    "/{lecture_id}/audio",
    response_model=AudioRecordingRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_audio(
    lecture_id: uuid.UUID,
    file: UploadFile = File(...),
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> AudioRecording:
    lecture = load_lecture_for_student(lecture_id, current, db)

    mime = file.content_type or "application/octet-stream"
    if not any(mime.startswith(p) for p in _ALLOWED_AUDIO_MIME_PREFIXES):
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {mime}")

    content = file.file.read()
    suffix = ".webm" if "webm" in mime else ".bin"
    relative_path = save_audio(content, suffix=suffix)

    recording = AudioRecording(
        lecture_id=lecture.id,
        uploaded_by_student_id=current.id,
        file_path=relative_path,
        mime_type=mime,
        size_bytes=len(content),
    )
    db.add(recording)
    db.commit()
    db.refresh(recording)
    return recording


@router.get("/{lecture_id}", response_model=LectureStatus)
def get_lecture(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> LectureStatus:
    lecture = load_lecture_for_student(lecture_id, current, db)

    my_notes_count = db.scalar(
        select(func.count(Note.id)).where(
            Note.lecture_id == lecture.id, Note.student_id == current.id
        )
    ) or 0
    has_audio = bool(
        db.scalar(
            select(func.count(AudioRecording.id)).where(AudioRecording.lecture_id == lecture.id)
        )
    )
    return LectureStatus(
        id=lecture.id,
        class_id=lecture.class_id,
        title=lecture.title,
        started_at=lecture.started_at,
        ended_at=lecture.ended_at,
        my_notes_count=my_notes_count,
        has_audio=has_audio,
    )
