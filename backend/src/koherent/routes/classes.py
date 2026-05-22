import secrets
import string

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from koherent.deps import get_db
from koherent.models import Class
from koherent.schemas import ClassCreate, ClassCreated

router = APIRouter(prefix="/classes", tags=["classes"])

_JOIN_CODE_ALPHABET = string.ascii_uppercase + string.digits


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
