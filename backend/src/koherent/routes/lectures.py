from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from koherent.deps import get_current_student, get_db
from koherent.models import Lecture, Student
from koherent.schemas import LectureCreate, LectureRead

router = APIRouter(prefix="/lectures", tags=["lectures"])


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
