import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from koherent.deps import get_db
from koherent.models import Class, Student
from koherent.schemas import ClassCreate, ClassCreated, JoinRequest, StudentSession

router = APIRouter(prefix="/classes", tags=["classes"])

_JOIN_CODE_ALPHABET = string.ascii_uppercase + string.digits
SESSION_COOKIE_NAME = "koherent_session"


def _generate_join_code() -> str:
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(6))


@router.post("", response_model=ClassCreated, status_code=status.HTTP_201_CREATED)
def create_class(payload: ClassCreate, db: Session = Depends(get_db)) -> Class:
    for _ in range(10):
        candidate = _generate_join_code()
        klass = Class(
            name=payload.name,
            join_code=candidate,
            owner_token=secrets.token_urlsafe(32),
        )
        db.add(klass)
        try:
            db.flush()
            db.commit()
            db.refresh(klass)
            return klass
        except IntegrityError:
            db.rollback()
            continue
    raise RuntimeError("Could not allocate a unique join code after 10 attempts")


@router.post("/join", response_model=StudentSession, status_code=status.HTTP_201_CREATED)
def join_class(
    payload: JoinRequest, response: Response, db: Session = Depends(get_db)
) -> StudentSession:
    klass = db.scalar(select(Class).where(Class.join_code == payload.join_code.upper()))
    if klass is None:
        raise HTTPException(status_code=404, detail="Join code not found")

    existing = db.scalar(
        select(Student).where(
            Student.class_id == klass.id, Student.display_name == payload.display_name
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Display name already taken in this class")

    student = Student(
        class_id=klass.id,
        display_name=payload.display_name,
        session_token=secrets.token_urlsafe(32),
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    response.set_cookie(
        SESSION_COOKIE_NAME,
        student.session_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return StudentSession(
        student_id=student.id,
        class_id=student.class_id,
        display_name=student.display_name,
        session_token=student.session_token,
    )
