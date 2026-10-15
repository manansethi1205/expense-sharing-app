from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def session_factory(database_url: str):
    engine = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    return engine, sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session


def get_report_session(request: Request) -> Iterator[Session]:
    """One read-only MVCC snapshot for the complete report; no accounting row locks."""
    with request.app.state.engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            with Session(bind=connection) as session:
                yield session
