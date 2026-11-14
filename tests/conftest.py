from collections.abc import Generator
from pathlib import Path
from typing import cast

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from valkey import Valkey

from url_shortener.cache import get_valkey
from url_shortener.database import Base, get_db
from url_shortener.main import create_app


@pytest.fixture
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    test_db_path = tmp_path / "test_shortener.db"
    engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def valkey_client() -> Generator[Valkey, None, None]:
    fake = fakeredis.FakeRedis(decode_responses=True)
    try:
        yield cast(Valkey, fake)
    finally:
        fake.flushall()
        fake.close()


@pytest.fixture
def client(db_session: Session, valkey_client: Valkey) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    def override_get_valkey() -> Valkey:
        return valkey_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_valkey] = override_get_valkey
    with TestClient(app) as test_client:
        yield test_client
