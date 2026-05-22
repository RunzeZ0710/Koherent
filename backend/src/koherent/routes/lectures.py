import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from koherent.deps import get_current_student, get_db
from koherent.models import Lecture, Note, Student
from koherent.schemas import LectureCreate, LectureRead, NoteCreate, NoteRead

router = APIRouter(prefix="/lectures", tags=["lectures"])


def _load_lecture_for_student(lecture_id: uuid.UUID, student: Student, db: Session) -> Lecture:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise HTTPException(status_code=404, detail="Lecture not found")
    if lecture.class_id != student.class_id:
        raise HTTPException(status_code=403, detail="Not a member of this lecture's class")
    return lecture


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
    lecture = _load_lecture_for_student(lecture_id, current, db)
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
