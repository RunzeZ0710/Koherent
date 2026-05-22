from collections.abc import Generator

from sqlalchemy.orm import Session

from koherent.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
