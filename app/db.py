from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def session_factory(database_url: str):
    engine = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    return engine, sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session
