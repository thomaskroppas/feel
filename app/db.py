"""Подключение к SQLite в режиме WAL."""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=15000")
        # Удалённые записи затираются нулями, а не остаются в свободных страницах файла.
        cur.execute("PRAGMA secure_delete=ON")
        cur.close()

    return eng


engine: Engine = None  # type: ignore[assignment]
SessionLocal: sessionmaker = None  # type: ignore[assignment]


def init_engine(url: str = None) -> Engine:
    """Создаёт движок заново (нужно тестам, чтобы подменить путь к базе)."""
    global engine, SessionLocal
    if url is None:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        url = settings.database_url
    if engine is not None:
        engine.dispose()
    engine = make_engine(url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine


init_engine()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
