"""Shared authorization helpers for lecture- and class-scoped routes.

Membership rules live in one place so every router enforces the same
policy: 404 for resources that don't exist, 403 for resources that exist
but belong to another class (a student's view of "not yours").
"""
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from koherent.models import Lecture, Student


def load_lecture_for_student(lecture_id: uuid.UUID, student: Student, db: Session) -> Lecture:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise HTTPException(status_code=404, detail="Lecture not found")
    if lecture.class_id != student.class_id:
        raise HTTPException(status_code=403, detail="Not a member of this lecture's class")
    return lecture


def require_class_member(class_id: uuid.UUID, student: Student) -> None:
    if class_id != student.class_id:
        raise HTTPException(status_code=403, detail="Not a member of this class")
