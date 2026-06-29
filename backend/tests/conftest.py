from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from koherent.config import settings
from koherent.db import Base
from koherent.deps import get_db
from koherent.main import app


@pytest.fixture(scope="session")
def _engine():
    engine = create_engine(settings.test_database_url, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db(_engine) -> Generator[Session, None, None]:
    """Per-test isolated session.

    Uses the SQLAlchemy "join an external transaction" pattern: the outer
    transaction is rolled back at teardown, and any `session.commit()` inside
    a route handler releases a SAVEPOINT (started by `begin_nested`) rather
    than committing to the test DB.
    """
    connection = _engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, autocommit=False, future=True)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if trans.nested and not trans._parent.nested:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db) -> Generator[TestClient, None, None]:
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
