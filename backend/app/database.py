# database.py
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

DATABASE_URL = "sqlite:///./local_database.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _record):
    """Per-connection SQLite settings (they are not stored in the file).

    The journal mode is deliberately NOT changed here: switching to WAL rewrites
    the database header, so it is done once, with a backup, by
    tools/fix_01_enable_wal.py. Once the file is in WAL mode,
    synchronous=NORMAL (the recommended, crash-safe setting for WAL) is applied;
    in rollback-journal mode the default FULL is kept. busy_timeout makes a
    contended write wait instead of failing at once with "database is locked".
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA busy_timeout=5000")
    journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()[0]
    if str(journal_mode).lower() == "wal":
        cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
