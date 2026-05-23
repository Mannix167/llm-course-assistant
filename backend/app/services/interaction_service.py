from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import Chapter, ChatMessage, Course, Feedback, Page, Report
from app.services.llm_service import LLMService
from app.utils.prompt_loader import load_prompt


@dataclass(slots=True)
class InteractionContext:
    scope: str
    scope_label: str
    related_pages: list[int]
    related_chapter_id: int | None
    text: str
    image_path: str | None = None


class InteractionService:
    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm_service = llm_service or LLMService()

    def list_chat_messages(self, db: Session, report_id: int) -> list[dict[str, Any]]:
        report = self._get_report(db, report_id)
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.report_id == report.id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        return [self._chat_payload(message) for message in messages]

    def ask_question(
        self,
        db: Session,
        report_id: int,
        question: str,
        mode: str = "normal",
        scope: str = "report",
        chapter_id: int | None = None,
        page_number: int | None = None,
        image_name: str | None = None,
    ) -> dict[str, Any]:
        report = self._get_report(db, report_id)
        course = self._get_course(db, report.course_id)
        normalized_mode = self._normalize_chat_mode(mode)
        context = self._build_context(
            db=db,
            course=course,
            report=report,
            scope=scope,
            chapter_id=chapter_id,
            page_number=page_number,
            image_name=image_name,
        )

        user_message = ChatMessage(
            course_id=course.id,
            report_id=report.id,
            role="user",
            content=question.strip(),
            scope=context.scope,
            related_pages=context.related_pages,
            related_chapter_id=context.related_chapter_id,
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)

        prompt = load_prompt(
            "chat.md",
            course_title=course.title,
            chat_mode="高级追问" if normalized_mode == "advanced" else "普通追问",
            scope_label=context.scope_label,
            question=question.strip(),
            context=context.text,
        )
        purpose = "advanced_chat" if normalized_mode == "advanced" else "chat"
        messages = [
            {"role": "system", "content": "你是严谨的中文课程学习助手。请基于给定上下文回答。"},
            {"role": "user", "content": prompt},
        ]
        if context.image_path and normalized_mode == "advanced":
            answer = self.llm_service.vision_chat_for_purpose(
                purpose=purpose,
                messages=messages,
                images=[context.image_path],
                temperature=0.2,
                max_tokens=4096,
            )
        else:
            answer = self.llm_service.chat_for_purpose(
                purpose=purpose,
                messages=messages,
                temperature=0.2,
                max_tokens=4096 if normalized_mode == "advanced" else 2048,
            )

        assistant_message = ChatMessage(
            course_id=course.id,
            report_id=report.id,
            role="assistant",
            content=answer.strip(),
            scope=context.scope,
            related_pages=context.related_pages,
            related_chapter_id=context.related_chapter_id,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)

        return {
            "question": self._chat_payload(user_message),
            "answer": self._chat_payload(assistant_message),
            "context_preview": context.text[:1200],
        }

    def list_feedback(self, db: Session, report_id: int) -> list[dict[str, Any]]:
        report = self._get_report(db, report_id)
        items = (
            db.query(Feedback)
            .filter(Feedback.report_id == report.id)
            .order_by(Feedback.id.asc())
            .all()
        )
        return [self._feedback_payload(item) for item in items]

    def rewrite_feedback(
        self,
        db: Session,
        report_id: int,
        feedback_text: str,
        target_content: str,
        scope: str = "report",
        chapter_id: int | None = None,
        page_number: int | None = None,
        image_name: str | None = None,
    ) -> dict[str, Any]:
        report = self._get_report(db, report_id)
        course = self._get_course(db, report.course_id)
        context = self._build_context(
            db=db,
            course=course,
            report=report,
            scope=scope,
            chapter_id=chapter_id,
            page_number=page_number,
            image_name=image_name,
        )

        item = Feedback(
            course_id=course.id,
            report_id=report.id,
            target_type=context.scope,
            target_id=context.related_chapter_id or page_number,
            feedback_text=feedback_text.strip(),
            target_content=target_content.strip(),
            status="running",
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        prompt = load_prompt(
            "feedback_rewrite.md",
            course_title=course.title,
            scope_label=context.scope_label,
            feedback_text=feedback_text.strip(),
            target_content=target_content.strip(),
            context=context.text,
        )
        try:
            rewritten = self.llm_service.chat_for_purpose(
                purpose="chat",
                messages=[
                    {"role": "system", "content": "你是中文课程报告局部改写助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.25,
                max_tokens=3072,
            )
            item.result_content = rewritten.strip()
            item.status = "completed"
        except Exception:
            item.status = "failed"
            db.commit()
            raise

        db.commit()
        db.refresh(item)
        return self._feedback_payload(item)

    def apply_feedback(self, db: Session, feedback_id: int) -> dict[str, Any]:
        item = db.get(Feedback, feedback_id)
        if item is None:
            raise ValueError(f"Feedback {feedback_id} not found.")
        if item.status != "completed" or not item.result_content:
            raise ValueError("Only completed feedback with rewrite result can be applied.")
        report = self._get_report(db, item.report_id)
        original = report.final_markdown or report.content_markdown or ""
        if not original:
            raise ValueError("Report has no markdown content to update.")

        target = (item.target_content or "").strip()
        rewritten = item.result_content.strip()
        if target and target in original:
            updated = original.replace(target, rewritten, 1)
        else:
            updated = original.rstrip() + "\n\n## 反馈改写应用\n\n" + rewritten + "\n"

        report.final_markdown = updated
        item.status = "applied"
        if report.report_path:
            Path(report.report_path).write_text(updated, encoding="utf-8")
        db.commit()
        db.refresh(item)
        return self._feedback_payload(item)

    def _build_context(
        self,
        db: Session,
        course: Course,
        report: Report,
        scope: str,
        chapter_id: int | None,
        page_number: int | None,
        image_name: str | None = None,
    ) -> InteractionContext:
        normalized_scope = scope.strip().lower()
        if normalized_scope not in {"report", "chapter", "page", "image"}:
            raise ValueError("scope must be one of: report, chapter, page, image.")

        if normalized_scope == "image":
            image_page = self._page_number_from_image_name(image_name) or page_number
            if image_page is None:
                raise ValueError("page_number or image_name is required when scope is image.")
            page = self._get_page(db, course.id, image_page)
            resolved_image_name = image_name or f"page_{image_page:03d}.png"
            image_path = self._absolute_image_path(course, resolved_image_name)
            return InteractionContext(
                scope="image",
                scope_label=f"第 {page.page_number} 页插图",
                related_pages=[page.page_number],
                related_chapter_id=None,
                text=self._page_context(page) + f"\n\n### 插图文件\n\n{Path(image_path).name}",
                image_path=image_path,
            )

        if normalized_scope == "page":
            if page_number is None:
                raise ValueError("page_number is required when scope is page.")
            page = self._get_page(db, course.id, page_number)
            return InteractionContext(
                scope="page",
                scope_label=f"第 {page.page_number} 页",
                related_pages=[page.page_number],
                related_chapter_id=None,
                text=self._page_context(page),
            )

        if normalized_scope == "chapter":
            if chapter_id is None:
                raise ValueError("chapter_id is required when scope is chapter.")
            chapter = self._get_chapter(db, course.id, chapter_id)
            pages = self._get_pages_in_range(db, course.id, chapter.start_page, chapter.end_page)
            return InteractionContext(
                scope="chapter",
                scope_label=f"{chapter.title}（第 {chapter.start_page}-{chapter.end_page} 页）",
                related_pages=[page.page_number for page in pages],
                related_chapter_id=chapter.id,
                text=self._chapter_context(chapter, pages, report),
            )

        pages = self._get_pages_in_range(db, course.id, 1, min(course.page_count or 9999, 12))
        return InteractionContext(
            scope="report",
            scope_label="整份报告",
            related_pages=[page.page_number for page in pages],
            related_chapter_id=None,
            text=self._report_context(report, pages),
        )

    def _report_context(self, report: Report, pages: list[Page]) -> str:
        sections = [
            "## 已生成报告内容",
            self._clip(report.final_markdown or report.content_markdown or report.summary_markdown or "", 9000),
            "## 课件前若干页原文",
            "\n\n".join(self._page_context(page) for page in pages),
        ]
        return "\n\n".join(section for section in sections if section)

    def _chapter_context(self, chapter: Chapter, pages: list[Page], report: Report) -> str:
        sections = [
            "## 章节信息",
            f"- 标题：{chapter.title}\n- 页码范围：{chapter.start_page}-{chapter.end_page}\n- 知识点：{', '.join(chapter.key_points or [])}",
            "## 相关课件页内容",
            "\n\n".join(self._page_context(page) for page in pages),
            "## 已生成报告节选",
            self._clip(report.final_markdown or report.content_markdown or "", 6000),
        ]
        return "\n\n".join(section for section in sections if section)

    def _page_context(self, page: Page) -> str:
        text = page.analysis_text or page.text or ""
        return f"### 第 {page.page_number} 页\n\n{text.strip() or '本页没有解析到文字内容。'}"

    def _get_report(self, db: Session, report_id: int | None) -> Report:
        if report_id is None:
            raise ValueError("Report id is required.")
        report = db.get(Report, report_id)
        if report is None:
            raise ValueError(f"Report {report_id} not found.")
        return report

    def _get_course(self, db: Session, course_id: int) -> Course:
        course = db.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course {course_id} not found.")
        return course

    def _get_page(self, db: Session, course_id: int, page_number: int) -> Page:
        page = db.query(Page).filter(Page.course_id == course_id, Page.page_number == page_number).one_or_none()
        if page is None:
            raise ValueError(f"Page {page_number} not found.")
        return page

    def _get_chapter(self, db: Session, course_id: int, chapter_id: int) -> Chapter:
        chapter = db.query(Chapter).filter(Chapter.course_id == course_id, Chapter.id == chapter_id).one_or_none()
        if chapter is None:
            raise ValueError(f"Chapter {chapter_id} not found.")
        return chapter

    def _get_pages_in_range(self, db: Session, course_id: int, start_page: int, end_page: int) -> list[Page]:
        return (
            db.query(Page)
            .filter(Page.course_id == course_id, Page.page_number >= start_page, Page.page_number <= end_page)
            .order_by(Page.page_number.asc())
            .all()
        )

    def _normalize_chat_mode(self, mode: str) -> str:
        normalized = mode.strip().lower()
        if normalized not in {"normal", "advanced"}:
            raise ValueError("mode must be normal or advanced.")
        return normalized

    def _chat_payload(self, message: ChatMessage) -> dict[str, Any]:
        return {
            "message_id": message.id,
            "course_id": message.course_id,
            "report_id": message.report_id,
            "role": message.role,
            "content": message.content,
            "scope": message.scope,
            "related_pages": message.related_pages or [],
            "related_chapter_id": message.related_chapter_id,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    def _feedback_payload(self, item: Feedback) -> dict[str, Any]:
        return {
            "feedback_id": item.id,
            "course_id": item.course_id,
            "report_id": item.report_id,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "feedback_text": item.feedback_text,
            "target_content": item.target_content,
            "status": item.status,
            "result_content": item.result_content,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def _page_number_from_image_name(self, image_name: str | None) -> int | None:
        if not image_name:
            return None
        import re

        match = re.search(r"page_(\d{3})\.png", image_name, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _absolute_image_path(self, course: Course, image_name: str) -> str:
        safe_name = Path(image_name).name
        if safe_name != image_name or not safe_name.lower().endswith(".png"):
            raise ValueError("Invalid image name.")
        course_root = Path(course.pages_json_path).resolve().parent if course.pages_json_path else Path(course.file_path).resolve().parent
        image_path = (course_root / "images" / safe_name).resolve()
        image_root = (course_root / "images").resolve()
        if image_root not in image_path.parents or not image_path.exists():
            raise ValueError(f"Image {safe_name} not found.")
        return str(image_path)

    def _clip(self, text: str, max_chars: int) -> str:
        return text if len(text) <= max_chars else text[:max_chars] + "\n\n[内容过长，已截断]"
