from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from koherent.config import settings
from koherent.db import Base
from koherent.deps import get_db  # created in Task 5
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
    connection = _engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, autoflush=False, autocommit=False, future=True)
    session = TestSession()
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
