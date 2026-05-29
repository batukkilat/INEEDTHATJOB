from sqlmodel import SQLModel, create_engine, Session
from config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def run_migrations() -> None:
    """Add columns missing from pre-existing databases (no Alembic)."""
    import sqlite3
    conn = sqlite3.connect(settings.db_path)
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(application)")}
    if "recipient_email" not in existing:
        cur.execute("ALTER TABLE application ADD COLUMN recipient_email TEXT")
    conn.commit()
    conn.close()


def get_session():
    with Session(engine) as session:
        yield session
