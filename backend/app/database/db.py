from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    from app.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "courses" not in table_names:
        return
    course_columns = {column["name"] for column in inspector.get_columns("courses")}
    if "folder_id" not in course_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE courses ADD COLUMN folder_id INTEGER"))

    if "generation_steps" in table_names:
        step_columns = {column["name"] for column in inspector.get_columns("generation_steps")}
        with engine.begin() as connection:
            if "input_tokens" not in step_columns:
                connection.execute(text("ALTER TABLE generation_steps ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0"))
            if "output_tokens" not in step_columns:
                connection.execute(text("ALTER TABLE generation_steps ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0"))

    if "feedback" in table_names:
        feedback_columns = {column["name"] for column in inspector.get_columns("feedback")}
        if "target_content" not in feedback_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE feedback ADD COLUMN target_content TEXT"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
