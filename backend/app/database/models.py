from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("course_folders.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False, default="pdf")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="uploaded")
    scanned_like: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pages_json_path: Mapped[str] = mapped_column(Text, nullable=True)

    folder: Mapped["CourseFolder"] = relationship(back_populates="courses")
    pages: Mapped[list["Page"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Page.page_number",
    )
    chapters: Mapped[list["Chapter"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    feedback_items: Mapped[list["Feedback"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class CourseFolder(TimestampMixin, Base):
    __tablename__ = "course_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    courses: Mapped[list["Course"]] = relationship(back_populates="folder")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    analysis_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    text_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analysis_text_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    height: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    need_ocr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_type: Mapped[str] = mapped_column(String(64), nullable=False, default="text")
    candidate_for_visual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclude_text_from_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_review_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candidate_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    layout_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    features: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    course: Mapped["Course"] = relationship(back_populates="pages")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    key_points: Mapped[list[str]] = mapped_column(JSON, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(64), nullable=True)
    need_visual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visual_reason: Mapped[str] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    course: Mapped["Course"] = relationship(back_populates="chapters")


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    outline_markdown: Mapped[str] = mapped_column(Text, nullable=True)
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=True)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=True)
    final_markdown: Mapped[str] = mapped_column(Text, nullable=True)
    review_result: Mapped[str] = mapped_column(Text, nullable=True)
    report_path: Mapped[str] = mapped_column(Text, nullable=True)

    course: Mapped["Course"] = relationship(back_populates="reports")
    generation_steps: Mapped[list["GenerationStep"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    feedback_items: Mapped[list["Feedback"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class GenerationStep(Base):
    __tablename__ = "generation_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=True, index=True)
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    input_preview: Mapped[str] = mapped_column(Text, nullable=True)
    output_content: Mapped[str] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped["Report"] = relationship(back_populates="generation_steps")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    related_pages: Mapped[list[int]] = mapped_column(JSON, nullable=True)
    related_chapter_id: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    course: Mapped["Course"] = relationship(back_populates="chat_messages")
    report: Mapped["Report"] = relationship(back_populates="chat_messages")


class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=True)
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_content: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    result_content: Mapped[str] = mapped_column(Text, nullable=True)

    course: Mapped["Course"] = relationship(back_populates="feedback_items")
    report: Mapped["Report"] = relationship(back_populates="feedback_items")


__all__ = [
    "Base",
    "Course",
    "CourseFolder",
    "Page",
    "Chapter",
    "Report",
    "GenerationStep",
    "ChatMessage",
    "Feedback",
]
