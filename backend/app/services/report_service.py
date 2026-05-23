from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy.orm import Session

from app.config import resolve_project_path, settings
from app.database.db import SessionLocal
from app.database.models import Chapter, Course, GenerationStep, Page, Report
from app.services.llm_service import LLMService
from app.utils.file_utils import ensure_dir
from app.utils.markdown_utils import join_markdown_sections
from app.utils.prompt_loader import load_prompt


@dataclass(slots=True)
class PlannedChapter:
    title: str
    start_page: int
    end_page: int
    content_summary: str
    key_points: list[str]


@dataclass(slots=True)
class OutlinePlan:
    chapters: list[PlannedChapter]
    outline_markdown: str
    overall_summary_markdown: str


@dataclass(slots=True)
class ChapterGeneration:
    plan: PlannedChapter
    markdown: str


@dataclass(slots=True)
class PageContext:
    page_number: int
    text: str
    analysis_text: str
    image_path: str
    text_length: int
    analysis_text_length: int
    image_count: int
    page_type: str
    candidate_for_visual: bool
    candidate_reasons: list[str]
    layout_flags: list[str]
    features: dict[str, Any]


class ReportCancelled(Exception):
    pass


class ReportService:
    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm_service = llm_service or LLMService()

    def create_report(self, db: Session, course_id: int, mode: str) -> Report:
        normalized_mode = self._normalize_mode(mode)

        course = db.get(Course, course_id)
        self._validate_course_for_report(course, course_id)

        report = Report(course_id=course.id, mode=normalized_mode, status="pending")
        db.add(report)
        db.commit()
        db.refresh(report)

        try:
            self._generate_report(db=db, course=course, report=report)
        except ReportCancelled:
            report.status = "cancelled"
            db.commit()
        except Exception as exc:
            report.status = "failed"
            db.commit()
            raise exc

        db.refresh(report)
        return report

    def create_report_record(self, db: Session, course_id: int, mode: str) -> Report:
        normalized_mode = self._normalize_mode(mode)
        course = db.get(Course, course_id)
        self._validate_course_for_report(course, course_id)

        report = Report(course_id=course.id, mode=normalized_mode, status="pending")
        db.add(report)
        db.commit()
        db.refresh(report)
        return report

    def generate_existing_report(self, db: Session, report_id: int) -> Report:
        report = db.get(Report, report_id)
        if report is None:
            raise ValueError(f"Report {report_id} not found.")
        course = db.get(Course, report.course_id)
        self._validate_course_for_report(course, report.course_id)

        try:
            self._generate_report(db=db, course=course, report=report)
        except Exception as exc:
            report.status = "failed"
            db.commit()
            raise exc

        db.refresh(report)
        return report

    def _normalize_mode(self, mode: str) -> str:
        normalized_mode = mode.strip().lower()
        if normalized_mode == "visual":
            raise ValueError("视觉增强模式已经合并到标准模式，请使用 standard。")
        if normalized_mode not in {"standard", "advanced", "extended"}:
            raise ValueError("当前只支持 standard、advanced、extended 三种模式。")
        return normalized_mode

    def _validate_course_for_report(self, course: Course | None, course_id: int) -> None:
        if course is None:
            raise ValueError(f"课程 {course_id} 不存在。")
        if course.status != "parsed":
            raise ValueError(f"课程 {course_id} 需要先完成 PDF 解析，当前状态为 {course.status}。")

    def get_report_detail(self, db: Session, report_id: int) -> dict | None:
        report = db.get(Report, report_id)
        if report is None:
            return None
        return {
            "report_id": report.id,
            "course_id": report.course_id,
            "mode": report.mode,
            "status": report.status,
            "outline_markdown": report.outline_markdown,
            "summary_markdown": report.summary_markdown,
            "content_markdown": report.content_markdown,
            "final_markdown": report.final_markdown,
            "review_result": report.review_result,
            "report_path": report.report_path,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        }

    def request_stop_report_generation(self, db: Session, report_id: int) -> Report:
        report = db.get(Report, report_id)
        if report is None:
            raise ValueError(f"Report {report_id} not found.")
        if report.status in {"completed", "failed", "cancelled"}:
            return report
        report.status = "cancel_requested"
        db.commit()
        db.refresh(report)
        return report

    def update_report_markdown(self, db: Session, report_id: int, markdown: str) -> Report:
        report = db.get(Report, report_id)
        if report is None:
            raise ValueError(f"Report {report_id} not found.")
        report.final_markdown = markdown
        if report.report_path:
            Path(report.report_path).write_text(markdown, encoding="utf-8")
        else:
            report.report_path = self._write_report_file(report.course_id, report.id, report.mode, markdown)
        db.commit()
        db.refresh(report)
        return report

    def list_report_steps(self, db: Session, report_id: int) -> list[dict]:
        steps = (
            db.query(GenerationStep)
            .filter(GenerationStep.report_id == report_id)
            .order_by(GenerationStep.id.asc())
            .all()
        )
        return [
            {
                "step_id": step.id,
                "course_id": step.course_id,
                "report_id": step.report_id,
                "step_name": step.step_name,
                "status": step.status,
                "input_preview": step.input_preview,
                "output_content": step.output_content,
                "input_tokens": step.input_tokens,
                "output_tokens": step.output_tokens,
                "error_message": step.error_message,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "finished_at": step.finished_at.isoformat() if step.finished_at else None,
            }
            for step in steps
        ]

    def _generate_report(self, db: Session, course: Course, report: Report) -> None:
        pages = self._get_course_pages(db, course.id)
        if not pages:
            raise ValueError(f"Course {course.id} has no parsed pages.")

        self._ensure_not_cancelled(db, report)
        report.status = "generating_outline"
        db.commit()

        cached_outline_plan = self._load_cached_outline_plan(db, course.id)
        if cached_outline_plan is not None:
            outline_plan = cached_outline_plan
            self._record_completed_step(
                db=db,
                course_id=course.id,
                report_id=report.id,
                step_name="generate_outline",
                input_preview="Reuse cached course outline and summary from an existing report.",
                output_content=self._json_dump(
                    {
                        "reused": True,
                        "outline_markdown": outline_plan.outline_markdown,
                        "overall_summary_markdown": outline_plan.overall_summary_markdown,
                    }
                ),
            )
        else:
            course_text = self._build_outline_context(pages)
            outline_prompt = load_prompt(
                "outline.md",
                course_title=course.title,
                page_count=course.page_count,
                course_text=course_text,
            )
            outline_payload = self._run_text_step(
                db=db,
                course_id=course.id,
                report_id=report.id,
                step_name="generate_outline",
                input_preview=self._preview(outline_prompt),
                messages=[
                    {"role": "system", "content": "你是严谨的中文课件结构分析助手，只输出用户要求的内容。"},
                    {"role": "user", "content": outline_prompt},
                ],
                expect_json=True,
            )
            outline_plan = self._normalize_outline_payload(outline_payload)

        planned_chapters = self._validate_planned_chapters(
            db=db,
            course=course,
            report=report,
            pages=pages,
            chapters=outline_plan.chapters,
        )
        outline_plan = OutlinePlan(
            chapters=planned_chapters,
            outline_markdown=self._build_outline_markdown(planned_chapters),
            overall_summary_markdown=outline_plan.overall_summary_markdown,
        )
        self._save_planned_chapters(db, course.id, planned_chapters)

        self._ensure_not_cancelled(db, report)
        report.outline_markdown = outline_plan.outline_markdown
        report.summary_markdown = outline_plan.overall_summary_markdown
        report.status = "generating_chapters"
        db.commit()

        if report.mode == "advanced":
            chapter_generations = self._generate_advanced_chapters(
                db=db,
                course=course,
                report=report,
                pages=pages,
                planned_chapters=planned_chapters,
            )
            image_insert_plan = self._build_advanced_image_plan(chapter_generations)
        elif report.mode == "extended":
            chapter_generations = self._generate_extended_chapters(
                db=db,
                course=course,
                report=report,
                pages=pages,
                planned_chapters=planned_chapters,
            )
            image_insert_plan = None
        else:
            chapter_generations = self._generate_standard_text_chapters(
                db=db,
                course=course,
                report=report,
                pages=pages,
                planned_chapters=planned_chapters,
            )
            report.status = "inserting_images"
            db.commit()
            chapter_generations, image_insert_plan = self._insert_images_for_standard_mode(
                db=db,
                course=course,
                report=report,
                pages=pages,
                chapter_generations=chapter_generations,
            )

        content_markdown = join_markdown_sections([chapter.markdown for chapter in chapter_generations])
        final_markdown = join_markdown_sections(
            [
                f"# {course.title} {self._mode_label(report.mode)}学习报告",
                outline_plan.outline_markdown,
                report.summary_markdown or "",
                "## 分章节详细讲解\n\n" + content_markdown,
            ]
        )

        self._ensure_not_cancelled(db, report)
        quality_checks = self._run_final_quality_checks(final_markdown, course, pages)
        report.content_markdown = content_markdown
        report.final_markdown = final_markdown
        if image_insert_plan is not None:
            report.review_result = self._json_dump({"image_insert_plan": image_insert_plan, "quality_checks": quality_checks})
            self._write_image_insert_plan(course.id, report.id, report.mode, image_insert_plan)
        else:
            report.review_result = self._json_dump({"quality_checks": quality_checks})
        report.report_path = self._write_report_file(course.id, report.id, report.mode, final_markdown)
        report.status = "completed"
        self._record_completed_step(
            db=db,
            course_id=course.id,
            report_id=report.id,
            step_name="quality_check_report",
            input_preview="Run rule-based checks on final report structure, page refs, image links, and markdown artifacts.",
            output_content=self._json_dump(quality_checks),
        )
        self._record_completed_step(
            db=db,
            course_id=course.id,
            report_id=report.id,
            step_name="build_final_report",
            input_preview="Combine outline, summary, and generated chapter explanations.",
            output_content=final_markdown,
        )
        db.commit()

    def _ensure_not_cancelled(self, db: Session, report: Report) -> None:
        db.refresh(report)
        if report.status == "cancel_requested":
            report.status = "cancelled"
            self._record_completed_step(
                db=db,
                course_id=report.course_id,
                report_id=report.id,
                step_name="cancel_generation",
                input_preview="User requested to stop report generation.",
                output_content="报告生成已停止。",
            )
            db.commit()
            raise ReportCancelled()

    def _run_chapter_jobs_parallel(self, db: Session, report: Report, chapters: list[PlannedChapter], job: Any) -> list[ChapterGeneration]:
        if not chapters:
            return []
        max_workers = min(3, len(chapters))
        if max_workers <= 1:
            return [job(db, index, chapter) for index, chapter in enumerate(chapters, start=1)]

        self._record_completed_step(
            db=db,
            course_id=report.course_id,
            report_id=report.id,
            step_name="parallel_chapter_generation_plan",
            input_preview=f"Schedule {len(chapters)} chapter jobs with max_workers={max_workers}.",
            output_content=self._json_dump(
                {
                    "chapter_count": len(chapters),
                    "max_workers": max_workers,
                    "chapters": [
                        {"index": index, "title": chapter.title, "pages": f"{chapter.start_page}-{chapter.end_page}"}
                        for index, chapter in enumerate(chapters, start=1)
                    ],
                }
            ),
        )
        db.commit()

        results: dict[int, ChapterGeneration] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {}
            for index, chapter in enumerate(chapters, start=1):
                self._ensure_not_cancelled(db, report)
                future = executor.submit(self._run_chapter_job_with_session, report.id, job, index, chapter)
                future_map[future] = index
            for future in as_completed(future_map):
                self._ensure_not_cancelled(db, report)
                index = future_map[future]
                results[index] = future.result()
        return [results[index] for index in sorted(results)]

    def _run_chapter_job_with_session(self, report_id: int, job: Any, index: int, chapter: PlannedChapter) -> ChapterGeneration:
        worker_db = SessionLocal()
        try:
            worker_report = worker_db.get(Report, report_id)
            if worker_report is None:
                raise ValueError(f"Report {report_id} not found.")
            self._ensure_not_cancelled(worker_db, worker_report)
            return job(worker_db, index, chapter)
        finally:
            worker_db.close()

    def _generate_standard_text_chapters(
        self,
        db: Session,
        course: Course,
        report: Report,
        pages: list[Page],
        planned_chapters: list[PlannedChapter],
    ) -> list[ChapterGeneration]:
        contexts = self._page_contexts(pages)
        return self._run_chapter_jobs_parallel(
            db=db,
            report=report,
            chapters=planned_chapters,
            job=lambda worker_db, index, chapter: self._generate_standard_chapter_job(
                db=worker_db,
                course_id=course.id,
                course_title=course.title,
                report_id=report.id,
                chapter_index=index,
                chapter=chapter,
                pages=contexts,
            ),
        )

    def _generate_standard_chapter_job(
        self,
        db: Session,
        course_id: int,
        course_title: str,
        report_id: int,
        chapter_index: int,
        chapter: PlannedChapter,
        pages: list[PageContext],
    ) -> ChapterGeneration:
        chapter_text = self._build_pages_text(
            [page for page in pages if chapter.start_page <= page.page_number <= chapter.end_page]
        )
        chapter_prompt = load_prompt(
            "chapter.md",
            course_title=course_title,
            chapter_title=chapter.title,
            start_page=chapter.start_page,
            end_page=chapter.end_page,
            chapter_summary=chapter.content_summary,
            chapter_text=chapter_text,
        )
        chapter_markdown = self._run_text_step(
            db=db,
            course_id=course_id,
            report_id=report_id,
            step_name=f"generate_chapter_{chapter_index}",
            input_preview=self._preview(chapter_prompt),
            messages=[
                {"role": "system", "content": "你是善于把课件讲清楚的中文课程讲解助手。"},
                {"role": "user", "content": chapter_prompt},
            ],
            expect_json=False,
        )
        return ChapterGeneration(plan=chapter, markdown=str(chapter_markdown).strip())

    def _generate_advanced_chapters(
        self,
        db: Session,
        course: Course,
        report: Report,
        pages: list[Page],
        planned_chapters: list[PlannedChapter],
    ) -> list[ChapterGeneration]:
        contexts = self._page_contexts(pages)
        course_root = Path(course.pages_json_path).resolve().parent if course.pages_json_path else Path(course.file_path).resolve().parent
        report_dir = self._report_dir(course.id, report.id, report.mode)
        return self._run_chapter_jobs_parallel(
            db=db,
            report=report,
            chapters=planned_chapters,
            job=lambda worker_db, index, chapter: self._generate_advanced_chapter_job(
                db=worker_db,
                course_id=course.id,
                course_title=course.title,
                report_id=report.id,
                chapter_index=index,
                chapter=chapter,
                pages=contexts,
                course_root=course_root,
                report_dir=report_dir,
            ),
        )

    def _generate_advanced_chapter_job(
        self,
        db: Session,
        course_id: int,
        course_title: str,
        report_id: int,
        chapter_index: int,
        chapter: PlannedChapter,
        pages: list[PageContext],
        course_root: Path,
        report_dir: Path,
    ) -> ChapterGeneration:
        chapter_pages = [page for page in pages if chapter.start_page <= page.page_number <= chapter.end_page]
        chapter_text = self._build_pages_text(chapter_pages)
        candidates = self._select_visual_candidate_pages(
            pages=pages,
            start_page=chapter.start_page,
            end_page=chapter.end_page,
            max_pages=3,
        )
        prompt = load_prompt(
            "advanced_report.md",
            course_title=course_title,
            chapter_title=chapter.title,
            start_page=chapter.start_page,
            end_page=chapter.end_page,
            chapter_summary=chapter.content_summary,
            chapter_text=chapter_text,
            candidate_pages=self._json_dump(
                [
                    self._candidate_page_payload(
                        page,
                        markdown_image=self._relative_image_path_for_report(report_dir, page.page_number),
                    )
                    for page in candidates
                ]
            ),
            max_insertions=2,
        )
        image_paths = [self._absolute_page_image_path_from_context(course_root, page) for page in candidates]
        if image_paths:
            chapter_markdown = self._run_vision_text_step(
                db=db,
                course_id=course_id,
                report_id=report_id,
                step_name=f"generate_advanced_chapter_{chapter_index}",
                input_preview=self._preview(prompt),
                messages=[
                    {"role": "system", "content": "你是中文课件图文讲解专家。请基于文字和截图生成准确、克制、结构清晰的 Markdown。"},
                    {"role": "user", "content": prompt},
                ],
                images=image_paths,
                purpose="advanced",
                max_tokens=3200,
            )
        else:
            chapter_markdown = self._run_text_step(
                db=db,
                course_id=course_id,
                report_id=report_id,
                step_name=f"generate_advanced_chapter_{chapter_index}",
                input_preview=self._preview(prompt),
                messages=[
                    {"role": "system", "content": "你是中文课件讲解专家。请生成准确、克制、结构清晰的 Markdown。"},
                    {"role": "user", "content": prompt},
                ],
                expect_json=False,
                purpose="advanced",
                max_tokens=3200,
            )
        return ChapterGeneration(plan=chapter, markdown=str(chapter_markdown).strip())

    def _generate_extended_chapters(
        self,
        db: Session,
        course: Course,
        report: Report,
        pages: list[Page],
        planned_chapters: list[PlannedChapter],
    ) -> list[ChapterGeneration]:
        contexts = self._page_contexts(pages)
        return self._run_chapter_jobs_parallel(
            db=db,
            report=report,
            chapters=planned_chapters,
            job=lambda worker_db, index, chapter: self._generate_extended_chapter_job(
                db=worker_db,
                course_id=course.id,
                course_title=course.title,
                report_id=report.id,
                chapter_index=index,
                chapter=chapter,
                pages=contexts,
            ),
        )

    def _generate_extended_chapter_job(
        self,
        db: Session,
        course_id: int,
        course_title: str,
        report_id: int,
        chapter_index: int,
        chapter: PlannedChapter,
        pages: list[PageContext],
    ) -> ChapterGeneration:
        chapter_text = self._build_pages_text(
            [page for page in pages if chapter.start_page <= page.page_number <= chapter.end_page]
        )
        extract_prompt = load_prompt(
            "extended_extract.md",
            course_title=course_title,
            chapter_title=chapter.title,
            start_page=chapter.start_page,
            end_page=chapter.end_page,
            chapter_summary=chapter.content_summary,
            chapter_text=chapter_text,
        )
        knowledge_payload = self._run_text_step(
            db=db,
            course_id=course_id,
            report_id=report_id,
            step_name=f"extract_extended_knowledge_{chapter_index}",
            input_preview=self._preview(extract_prompt),
            messages=[
                {"role": "system", "content": "你是严谨的中文课程知识结构分析助手，只输出合法 JSON。"},
                {"role": "user", "content": extract_prompt},
            ],
            expect_json=True,
            purpose="standard_text",
            max_tokens=4096,
        )
        knowledge_skeleton = self._format_knowledge_skeleton(knowledge_payload)
        extended_prompt = load_prompt(
            "extended_chapter.md",
            course_title=course_title,
            chapter_title=chapter.title,
            knowledge_skeleton=knowledge_skeleton,
        )
        chapter_markdown = self._run_text_step(
            db=db,
            course_id=course_id,
            report_id=report_id,
            step_name=f"generate_extended_chapter_{chapter_index}",
            input_preview=self._preview(extended_prompt),
            messages=[
                {"role": "system", "content": "你是擅长把抽象知识讲清楚的中文课程老师。"},
                {"role": "user", "content": extended_prompt},
            ],
            expect_json=False,
            purpose="standard_text",
            max_tokens=4096,
        )
        return ChapterGeneration(plan=chapter, markdown=str(chapter_markdown).strip())

    def _format_knowledge_skeleton(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return str(payload)
        logic = str(payload.get("logic_markdown") or "").strip()
        points = payload.get("core_knowledge_points") or []
        keywords = payload.get("keywords") or []
        learning_goal = str(payload.get("learning_goal") or "").strip()
        if not isinstance(points, list):
            points = [str(points)]
        if not isinstance(keywords, list):
            keywords = [str(keywords)]

        sections = []
        if learning_goal:
            sections.append(f"## 学习目标\n\n{learning_goal}")
        if logic:
            sections.append(logic)
        if points:
            sections.append("## 核心知识点\n\n" + "\n".join(f"- {point}" for point in points))
        if keywords:
            sections.append("## 关键词\n\n" + "、".join(str(keyword) for keyword in keywords))
        return "\n\n".join(sections).strip() or self._json_dump(payload)

    def _build_advanced_image_plan(self, chapter_generations: list[ChapterGeneration]) -> dict[str, Any]:
        insertions: list[dict[str, Any]] = []
        for index, chapter in enumerate(chapter_generations, start=1):
            for page_number in self._extract_inserted_page_numbers(chapter.markdown):
                insertions.append(
                    {
                        "page_number": page_number,
                        "chapter_title": chapter.plan.title,
                        "chapter_index": index,
                        "source": "advanced_chapter_markdown",
                    }
                )
        return {"insertions": insertions}

    def _extract_inserted_page_numbers(self, markdown: str) -> list[int]:
        import re

        numbers: list[int] = []
        for match in re.finditer(r"page_(\d{3})\.png", markdown):
            number = self._safe_int(match.group(1), 0)
            if number and number not in numbers:
                numbers.append(number)
        return numbers

    def _mode_label(self, mode: str) -> str:
        return {
            "standard": "标准",
            "advanced": "高级",
            "extended": "扩展",
        }.get(mode, mode)

    def _insert_images_for_standard_mode(
        self,
        db: Session,
        course: Course,
        report: Report,
        pages: list[Page],
        chapter_generations: list[ChapterGeneration],
    ) -> tuple[list[ChapterGeneration], dict[str, Any]]:
        all_insertions: list[dict[str, Any]] = []
        updated_chapters: list[ChapterGeneration] = []

        for index, chapter_generation in enumerate(chapter_generations, start=1):
            self._ensure_not_cancelled(db, report)
            candidates = self._select_visual_candidate_pages(
                pages=pages,
                start_page=chapter_generation.plan.start_page,
                end_page=chapter_generation.plan.end_page,
                max_pages=4,
            )
            if not candidates:
                updated_chapters.append(chapter_generation)
                continue

            prompt = load_prompt(
                "image_insert.md",
                course_title=course.title,
                chapter_title=chapter_generation.plan.title,
                start_page=chapter_generation.plan.start_page,
                end_page=chapter_generation.plan.end_page,
                chapter_markdown=chapter_generation.markdown,
                candidate_pages=self._json_dump([self._candidate_page_payload(page) for page in candidates]),
                max_insertions=2,
            )
            image_paths = [self._absolute_page_image_path(course, page) for page in candidates]
            raw_plan = self._run_vision_json_step(
                db=db,
                course_id=course.id,
                report_id=report.id,
                step_name=f"generate_image_insert_plan_{index}",
                input_preview=self._preview(prompt),
                messages=[
                    {"role": "system", "content": "你是严谨的课件图文关系分析助手，只输出合法 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                images=image_paths,
            )
            insertions = self._normalize_image_insertions(raw_plan, candidates)
            all_insertions.extend(
                [
                    {
                        **insertion,
                        "chapter_title": chapter_generation.plan.title,
                        "chapter_index": index,
                    }
                    for insertion in insertions
                ]
            )
            updated_markdown = self._apply_image_insertions(
                markdown=chapter_generation.markdown,
                insertions=insertions,
                report_dir=self._report_dir(course.id, report.id, report.mode),
            )
            updated_chapters.append(ChapterGeneration(plan=chapter_generation.plan, markdown=updated_markdown))

        image_insert_plan = {"insertions": all_insertions}
        self._record_completed_step(
            db=db,
            course_id=course.id,
            report_id=report.id,
            step_name="apply_image_insert_plan",
            input_preview="Apply Kimi image insertion suggestions to chapter markdown.",
            output_content=self._json_dump(image_insert_plan),
        )
        return updated_chapters, image_insert_plan

    def _run_vision_json_step(
        self,
        db: Session,
        course_id: int,
        report_id: int,
        step_name: str,
        input_preview: str,
        messages: list[dict[str, Any]],
        images: list[str],
    ) -> Any:
        cached_output = self._load_completed_step_output(db, report_id, step_name)
        if cached_output is not None:
            try:
                return self.llm_service.parse_json_text(cached_output)
            except Exception:
                return {"insertions": []}

        step = GenerationStep(
            course_id=course_id,
            report_id=report_id,
            step_name=step_name,
            status="running",
            input_preview=input_preview,
            started_at=self._now(),
        )
        db.add(step)
        db.commit()
        db.refresh(step)

        try:
            raw_content = self.llm_service.vision_chat_for_purpose(
                purpose="visual_vision",
                messages=messages,
                images=images,
                temperature=0.1,
                max_tokens=4096,
            )
            output_content = str(raw_content)
            try:
                result = self.llm_service.parse_json_text(output_content)
            except Exception as parse_exc:
                result = {"insertions": []}
                output_content = (
                    output_content
                    + "\n\n[Parse warning] Image insertion JSON could not be parsed; "
                    + f"this chapter was left without image insertions. Error: {parse_exc}"
                )
        except Exception as exc:
            step.status = "failed"
            step.error_message = str(exc)
            step.finished_at = self._now()
            db.commit()
            raise exc

        step.status = "completed"
        step.output_content = output_content
        step.input_tokens = self._estimate_messages_tokens(messages) + len(images) * 1000
        step.output_tokens = self._estimate_text_tokens(output_content)
        step.finished_at = self._now()
        db.commit()
        return result

    def _run_vision_text_step(
        self,
        db: Session,
        course_id: int,
        report_id: int,
        step_name: str,
        input_preview: str,
        messages: list[dict[str, Any]],
        images: list[str],
        purpose: str,
        max_tokens: int,
    ) -> str:
        cached_output = self._load_completed_step_output(db, report_id, step_name)
        if cached_output is not None:
            return cached_output

        step = GenerationStep(
            course_id=course_id,
            report_id=report_id,
            step_name=step_name,
            status="running",
            input_preview=input_preview,
            started_at=self._now(),
        )
        db.add(step)
        db.commit()
        db.refresh(step)

        try:
            result = self.llm_service.vision_chat_for_purpose(
                purpose=purpose,
                messages=messages,
                images=images,
                temperature=0.2,
                max_tokens=max_tokens,
            )
            output_content = str(result)
        except Exception as exc:
            step.status = "failed"
            step.error_message = str(exc)
            step.finished_at = self._now()
            db.commit()
            raise exc

        step.status = "completed"
        step.output_content = output_content
        step.input_tokens = self._estimate_messages_tokens(messages) + len(images) * 1000
        step.output_tokens = self._estimate_text_tokens(output_content)
        step.finished_at = self._now()
        db.commit()
        return output_content

    def _run_text_step(
        self,
        db: Session,
        course_id: int,
        report_id: int,
        step_name: str,
        input_preview: str,
        messages: list[dict[str, Any]],
        expect_json: bool,
        purpose: str = "standard_text",
        max_tokens: int | None = None,
    ) -> Any:
        cached_output = self._load_completed_step_output(db, report_id, step_name)
        if cached_output is not None:
            if expect_json:
                try:
                    return self.llm_service.parse_json_text(cached_output)
                except Exception:
                    pass
            else:
                return cached_output

        step = GenerationStep(
            course_id=course_id,
            report_id=report_id,
            step_name=step_name,
            status="running",
            input_preview=input_preview,
            started_at=self._now(),
        )
        db.add(step)
        db.commit()
        db.refresh(step)

        try:
            if expect_json:
                raw_content = self.llm_service.chat_for_purpose(
                    purpose=purpose,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=max_tokens or 8192,
                )
                output_content = str(raw_content)
                result = self.llm_service.parse_json_text(output_content)
            else:
                result = self.llm_service.chat_for_purpose(
                    purpose=purpose,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=max_tokens or 4096,
                )
                output_content = str(result)
        except Exception as exc:
            step.status = "failed"
            step.error_message = str(exc)
            step.finished_at = self._now()
            db.commit()
            raise exc

        step.status = "completed"
        step.output_content = output_content
        step.input_tokens = self._estimate_messages_tokens(messages)
        step.output_tokens = self._estimate_text_tokens(output_content)
        step.finished_at = self._now()
        db.commit()
        return result

    def _load_completed_step_output(self, db: Session, report_id: int, step_name: str) -> str | None:
        step = (
            db.query(GenerationStep)
            .filter(
                GenerationStep.report_id == report_id,
                GenerationStep.step_name == step_name,
                GenerationStep.status == "completed",
                GenerationStep.output_content.isnot(None),
            )
            .order_by(GenerationStep.id.desc())
            .first()
        )
        if step is None:
            return None
        output_content = step.output_content or ""
        return output_content if output_content.strip() else None

    def _record_completed_step(
        self,
        db: Session,
        course_id: int,
        report_id: int,
        step_name: str,
        input_preview: str,
        output_content: str,
    ) -> None:
        db.add(
            GenerationStep(
                course_id=course_id,
                report_id=report_id,
                step_name=step_name,
                status="completed",
                input_preview=input_preview,
                output_content=output_content,
                input_tokens=0,
                output_tokens=0,
                started_at=self._now(),
                finished_at=self._now(),
            )
        )

    def _estimate_messages_tokens(self, messages: list[dict[str, Any]]) -> int:
        return self._estimate_text_tokens(self._json_dump(messages))

    def _estimate_text_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, round(len(text) / 3))

    def _normalize_outline_payload(self, payload: Any) -> OutlinePlan:
        if isinstance(payload, list):
            raw_chapters = payload
            outline_markdown = ""
            overall_summary_markdown = ""
        elif isinstance(payload, dict):
            raw_chapters = payload.get("chapters") or payload.get("outline") or []
            outline_markdown = str(payload.get("outline_markdown") or "").strip()
            overall_summary_markdown = str(
                payload.get("overall_summary_markdown")
                or payload.get("summary_markdown")
                or payload.get("course_summary")
                or ""
            ).strip()
        else:
            raise ValueError("Outline response must be a JSON object or array.")

        chapters: list[PlannedChapter] = []
        for index, item in enumerate(raw_chapters, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"第{index}章").strip()
            start_page = self._safe_int(item.get("start_page"), 1)
            end_page = self._safe_int(item.get("end_page"), start_page)
            if end_page < start_page:
                start_page, end_page = end_page, start_page
            summary = str(item.get("content_summary") or item.get("summary") or "").strip()
            key_points = item.get("key_points") or []
            if not isinstance(key_points, list):
                key_points = [str(key_points)]
            chapters.append(
                PlannedChapter(
                    title=title,
                    start_page=start_page,
                    end_page=end_page,
                    content_summary=summary,
                    key_points=[str(point) for point in key_points],
                )
            )

        if not chapters:
            raise ValueError("Outline response did not contain any chapters.")

        outline_markdown = self._build_outline_markdown(chapters)
        if not overall_summary_markdown:
            overall_summary_markdown = self._build_overall_summary_fallback(chapters)
        return OutlinePlan(
            chapters=chapters,
            outline_markdown=outline_markdown,
            overall_summary_markdown=overall_summary_markdown,
        )

    def _load_cached_outline_plan(self, db: Session, course_id: int) -> OutlinePlan | None:
        chapters = (
            db.query(Chapter)
            .filter(Chapter.course_id == course_id)
            .order_by(Chapter.order_index.asc(), Chapter.id.asc())
            .all()
        )
        if not chapters:
            return None

        source_report = (
            db.query(Report)
            .filter(
                Report.course_id == course_id,
                Report.outline_markdown.isnot(None),
                Report.summary_markdown.isnot(None),
            )
            .order_by(Report.id.desc())
            .first()
        )
        if source_report is None:
            return None

        planned_chapters = [
            PlannedChapter(
                title=chapter.title,
                start_page=chapter.start_page,
                end_page=chapter.end_page,
                content_summary=chapter.visual_reason or "",
                key_points=chapter.key_points or [],
            )
            for chapter in chapters
        ]
        if not planned_chapters:
            return None

        return OutlinePlan(
            chapters=planned_chapters,
            outline_markdown=source_report.outline_markdown or self._build_outline_markdown(planned_chapters),
            overall_summary_markdown=source_report.summary_markdown or self._build_overall_summary_fallback(planned_chapters),
        )

    def _save_planned_chapters(self, db: Session, course_id: int, chapters: list[PlannedChapter]) -> None:
        db.query(Chapter).filter(Chapter.course_id == course_id).delete()
        db.flush()
        for index, chapter in enumerate(chapters, start=1):
            db.add(
                Chapter(
                    course_id=course_id,
                    title=chapter.title,
                    start_page=chapter.start_page,
                    end_page=chapter.end_page,
                    key_points=chapter.key_points,
                    difficulty=None,
                    need_visual=False,
                    visual_reason=chapter.content_summary,
                    order_index=index,
                )
            )
        db.commit()

    def _get_course_pages(self, db: Session, course_id: int) -> list[Page]:
        return db.query(Page).filter(Page.course_id == course_id).order_by(Page.page_number.asc()).all()

    def _page_contexts(self, pages: list[Page]) -> list[PageContext]:
        return [
            PageContext(
                page_number=page.page_number,
                text=page.text or "",
                analysis_text=page.analysis_text or "",
                image_path=page.image_path,
                text_length=page.text_length,
                analysis_text_length=page.analysis_text_length,
                image_count=page.image_count,
                page_type=page.page_type,
                candidate_for_visual=page.candidate_for_visual,
                candidate_reasons=page.candidate_reasons or [],
                layout_flags=page.layout_flags or [],
                features=page.features or {},
            )
            for page in pages
        ]

    def _build_outline_context(self, pages: list[Page]) -> str:
        chunks: list[str] = []
        for page in pages:
            features = page.features or {}
            summary = str(features.get("page_summary") or "").strip()
            titles = features.get("title_candidates") or []
            title_text = " / ".join(str(title) for title in titles[:2]) if isinstance(titles, list) else ""
            source = summary or (page.analysis_text or page.text or "")[:360]
            if not source:
                continue
            meta = f"[第 {page.page_number} 页 | {page.page_type}]"
            if title_text:
                meta += f" 标题候选：{title_text}"
            chunks.append(f"{meta}\n{source}")
        return "\n\n".join(chunks)

    def _build_pages_text(self, pages: list[Page | PageContext]) -> str:
        chunks: list[str] = []
        for page in pages:
            text = self._page_context_text(page)
            if not text:
                continue
            features = page.features or {}
            summary = str(features.get("page_summary") or "").strip()
            importance = self._page_importance_score(page)
            role = self._page_context_role(page, importance)
            meta = f"[第 {page.page_number} 页 | {page.page_type} | {role} | importance={importance:.2f}]"
            if summary and summary not in text:
                chunks.append(f"{meta}\n页面摘要：{summary}\n{text}")
            else:
                chunks.append(f"{meta}\n{text}")
        return "\n\n".join(chunks)

    def _page_context_text(self, page: Page | PageContext) -> str:
        features = page.features or {}
        summary = str(features.get("page_summary") or "").strip()
        text = (page.analysis_text or page.text or "").strip()
        importance = self._page_importance_score(page)
        if page.page_type in {"title_or_transition", "table_like", "formula_like", "diagram_like"}:
            return summary or text[:320]
        if importance < 2.2:
            return summary or text[:420]
        if importance < 4.0:
            return self._trim_context_text(text, 900)
        return self._trim_context_text(text, 1800)

    def _trim_context_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        head = text[: max_chars - 40].rstrip()
        return head + "\n...[本页上下文已按预算截断]"

    def _page_importance_score(self, page: Page | PageContext) -> float:
        features = page.features or {}
        score = 0.0
        if page.page_type in {"text_with_visual", "table_like", "formula_like", "diagram_like"}:
            score += 2.2
        if page.candidate_for_visual:
            score += 1.4
        if page.page_type == "title_or_transition":
            score -= 1.2
        score += min(float(features.get("visual_object_score", 0.0) or 0.0), 4.0) * 0.45
        score += min(float(features.get("table_like_score", 0.0) or 0.0), 4.0) * 0.35
        score += min(float(features.get("formula_like_score", 0.0) or 0.0), 4.0) * 0.35
        text = (page.analysis_text or page.text or "").lower()
        if any(keyword in text for keyword in ("定义", "定理", "性质", "公式", "例", "假设", "模型", "结论")):
            score += 1.4
        if page.text_length >= 160:
            score += 0.8
        if page.text_length >= 500:
            score += 0.6
        return round(max(score, 0.0), 2)

    def _page_context_role(self, page: Page | PageContext, importance: float) -> str:
        if page.page_type == "title_or_transition":
            return "summary_only"
        if page.page_type in {"table_like", "formula_like", "diagram_like"}:
            return "visual_summary"
        if importance >= 4.0:
            return "full_context"
        if importance >= 2.2:
            return "medium_context"
        return "summary_only"

    def _validate_planned_chapters(
        self,
        db: Session,
        course: Course,
        report: Report,
        pages: list[Page],
        chapters: list[PlannedChapter],
    ) -> list[PlannedChapter]:
        page_numbers = [page.page_number for page in pages]
        min_page = min(page_numbers)
        max_page = max(page_numbers)
        diagnostics: list[dict[str, Any]] = []
        validated: list[PlannedChapter] = []
        previous_end = min_page - 1

        for index, chapter in enumerate(chapters, start=1):
            start_page = min(max(chapter.start_page, min_page), max_page)
            end_page = min(max(chapter.end_page, min_page), max_page)
            if end_page < start_page:
                start_page, end_page = end_page, start_page
            if start_page <= previous_end:
                start_page = min(previous_end + 1, max_page)
                end_page = max(end_page, start_page)
            scoped_pages = [page for page in pages if start_page <= page.page_number <= end_page and (page.analysis_text or page.text or "").strip()]
            if not scoped_pages and start_page < max_page:
                end_page = min(max_page, start_page + 1)
                scoped_pages = [page for page in pages if start_page <= page.page_number <= end_page and (page.analysis_text or page.text or "").strip()]
            if not scoped_pages:
                diagnostics.append({"chapter": chapter.title, "action": "drop_empty_chapter", "original_pages": f"{chapter.start_page}-{chapter.end_page}"})
                continue
            validated.append(
                PlannedChapter(
                    title=chapter.title or f"第{index}章",
                    start_page=start_page,
                    end_page=end_page,
                    content_summary=chapter.content_summary,
                    key_points=chapter.key_points,
                )
            )
            diagnostics.append(
                {
                    "chapter": chapter.title,
                    "original_pages": f"{chapter.start_page}-{chapter.end_page}",
                    "validated_pages": f"{start_page}-{end_page}",
                    "page_count": len(scoped_pages),
                    "action": "adjusted" if (start_page, end_page) != (chapter.start_page, chapter.end_page) else "kept",
                }
            )
            previous_end = end_page

        if not validated:
            validated = [
                PlannedChapter(
                    title="课程内容讲解",
                    start_page=min_page,
                    end_page=max_page,
                    content_summary="基于全部有效课件页生成讲解。",
                    key_points=[],
                )
            ]
            diagnostics.append({"action": "fallback_single_chapter", "validated_pages": f"{min_page}-{max_page}"})

        self._record_completed_step(
            db=db,
            course_id=course.id,
            report_id=report.id,
            step_name="validate_chapter_plan",
            input_preview="Validate chapter page ranges against parsed pages before chapter generation.",
            output_content=self._json_dump(diagnostics),
        )
        self._write_generation_context_cache(course, report, pages, validated, diagnostics)
        return validated

    def _write_generation_context_cache(
        self,
        course: Course,
        report: Report,
        pages: list[Page],
        chapters: list[PlannedChapter],
        diagnostics: list[dict[str, Any]],
    ) -> None:
        cache_path = self._report_dir(course.id, report.id, report.mode) / "generation_context_cache.json"
        payload = {
            "course_id": course.id,
            "report_id": report.id,
            "page_summaries": [
                {
                    "page_number": page.page_number,
                    "page_type": page.page_type,
                    "summary": (page.features or {}).get("page_summary", ""),
                    "title_candidates": (page.features or {}).get("title_candidates", []),
                    "importance_score": self._page_importance_score(page),
                    "context_role": self._page_context_role(page, self._page_importance_score(page)),
                }
                for page in pages
            ],
            "chapters": [
                {
                    "title": chapter.title,
                    "start_page": chapter.start_page,
                    "end_page": chapter.end_page,
                    "summary": chapter.content_summary,
                    "key_points": chapter.key_points,
                }
                for chapter in chapters
            ],
            "validation_diagnostics": diagnostics,
        }
        cache_path.write_text(self._json_dump(payload), encoding="utf-8")

    def _build_outline_markdown(self, chapters: list[PlannedChapter]) -> str:
        lines = ["## 课程目录", "", "| 章节 | 页码范围 | 内容总结 |", "|---|---|---|"]
        for chapter in chapters:
            lines.append(
                f"| {chapter.title} | {chapter.start_page}-{chapter.end_page} | {chapter.content_summary} |"
            )
        return "\n".join(lines)

    def _build_overall_summary_fallback(self, chapters: list[PlannedChapter]) -> str:
        sections = ["## 课程整体总结", "", "这份课件可以按以下章节线索理解："]
        for chapter in chapters:
            points = "、".join(chapter.key_points) if chapter.key_points else "暂无"
            sections.append(
                f"- {chapter.title}（第 {chapter.start_page}-{chapter.end_page} 页）："
                f"{chapter.content_summary} 关键点：{points}。"
            )
        return "\n".join(sections)

    def _run_final_quality_checks(self, markdown: str, course: Course, pages: list[Page]) -> dict[str, Any]:
        warnings: list[str] = []
        page_numbers = {page.page_number for page in pages}
        max_page = max(page_numbers) if page_numbers else course.page_count
        headings = re.findall(r"^#{1,4}\s+(.+)$", markdown, flags=re.MULTILINE)
        if len(markdown.strip()) < 300:
            warnings.append("final_report_too_short")
        if "## 分章节详细讲解" not in markdown:
            warnings.append("missing_chapter_detail_section")
        if re.search(r"\{\{.+?\}\}", markdown):
            warnings.append("template_placeholder_leftover")
        for image_name in re.findall(r"page_(\d{3})\.png", markdown):
            page_number = self._safe_int(image_name, 0)
            if page_number not in page_numbers:
                warnings.append(f"image_ref_page_not_found:{page_number}")
        for page_ref in re.findall(r"第\s*(\d{1,4})\s*页", markdown):
            page_number = self._safe_int(page_ref, 0)
            if page_number and (page_number < 1 or page_number > max_page):
                warnings.append(f"page_ref_out_of_range:{page_number}")
        if markdown.count("<mark") != markdown.count("</mark>"):
            warnings.append("unbalanced_mark_tags")
        empty_heading_count = sum(1 for heading in headings if not heading.strip())
        if empty_heading_count:
            warnings.append(f"empty_headings:{empty_heading_count}")
        return {
            "ok": not warnings,
            "warning_count": len(warnings),
            "warnings": warnings,
            "heading_count": len(headings),
            "image_ref_count": len(re.findall(r"page_\d{3}\.png", markdown)),
            "checked_at": self._now().isoformat(),
        }

    def _select_visual_candidate_pages(self, pages: list[Page | PageContext], start_page: int, end_page: int, max_pages: int) -> list[Page | PageContext]:
        scoped = [page for page in pages if start_page <= page.page_number <= end_page]
        candidates = [
            page
            for page in scoped
            if page.candidate_for_visual
            or page.image_count > 0
            or page.page_type in {"diagram_like", "table_like", "formula_like", "text_with_visual"}
        ]
        scored = sorted(candidates, key=self._visual_candidate_score, reverse=True)
        return scored[:max_pages]

    def _visual_candidate_score(self, page: Page | PageContext) -> float:
        score = 0.0
        if page.candidate_for_visual:
            score += 5.0
        if page.page_type in {"diagram_like", "table_like", "formula_like", "text_with_visual"}:
            score += 3.0
        score += min(float(page.image_count), 3.0)
        features = page.features or {}
        score += float(features.get("visual_object_score", 0.0) or 0.0)
        score += float(features.get("table_like_score", 0.0) or 0.0)
        score += float(features.get("formula_like_score", 0.0) or 0.0)
        if page.text_length <= 220:
            score += 1.0
        return score

    def _candidate_page_payload(self, page: Page | PageContext, markdown_image: str | None = None) -> dict[str, Any]:
        payload = {
            "page_number": page.page_number,
            "page_type": page.page_type,
            "text": (page.analysis_text or page.text or "")[:1000],
            "image_count": page.image_count,
            "candidate_reasons": page.candidate_reasons,
            "layout_flags": page.layout_flags,
            "features": page.features,
        }
        if markdown_image:
            payload["markdown_image"] = markdown_image
        return payload

    def _normalize_image_insertions(self, payload: Any, candidates: list[Page]) -> list[dict[str, Any]]:
        raw_insertions = payload.get("insertions", []) if isinstance(payload, dict) else payload
        if not isinstance(raw_insertions, list):
            return []
        candidate_numbers = {page.page_number for page in candidates}
        normalized: list[dict[str, Any]] = []
        seen_pages: set[int] = set()
        for item in raw_insertions:
            if not isinstance(item, dict):
                continue
            page_number = self._safe_int(item.get("page_number"), 0)
            if page_number not in candidate_numbers or page_number in seen_pages:
                continue
            if not bool(item.get("should_insert", False)):
                continue
            seen_pages.add(page_number)
            normalized.append(
                {
                    "page_number": page_number,
                    "should_insert": True,
                    "insert_after_heading": str(item.get("insert_after_heading") or "").strip(),
                    "caption": str(item.get("caption") or f"第{page_number}页课件截图").strip(),
                    "minor_text_patch": str(item.get("minor_text_patch") or "").strip(),
                    "reason": str(item.get("reason") or "").strip(),
                }
            )
        return normalized[:2]

    def _apply_image_insertions(self, markdown: str, insertions: list[dict[str, Any]], report_dir: Path) -> str:
        updated = markdown
        for insertion in insertions:
            page_number = insertion["page_number"]
            relative_image = self._relative_image_path_for_report(report_dir, page_number)
            patch_text = insertion.get("minor_text_patch", "")
            image_block_parts = []
            if patch_text:
                image_block_parts.append(patch_text)
            image_block_parts.extend(
                [
                    f"![第{page_number}页课件截图]({relative_image})",
                    f"> 图示说明：{insertion['caption']}",
                ]
            )
            image_block = "\n\n" + "\n\n".join(image_block_parts) + "\n"
            heading = insertion.get("insert_after_heading", "")
            updated = self._insert_after_heading(updated, heading, image_block)
        return updated

    def _insert_after_heading(self, markdown: str, heading: str, block: str) -> str:
        if heading and heading in markdown:
            marker_index = markdown.find(heading)
            next_heading_index = markdown.find("\n#", marker_index + len(heading))
            if next_heading_index == -1:
                return markdown.rstrip() + block
            return markdown[:next_heading_index].rstrip() + block + "\n" + markdown[next_heading_index:].lstrip()
        return markdown.rstrip() + block

    def _absolute_page_image_path(self, course: Course, page: Page) -> str:
        course_root = Path(course.pages_json_path).resolve().parent if course.pages_json_path else Path(course.file_path).resolve().parent
        return str((course_root / page.image_path).resolve())

    def _absolute_page_image_path_from_context(self, course_root: Path, page: PageContext) -> str:
        return str((course_root / page.image_path).resolve())

    def _relative_image_path_for_report(self, report_dir: Path, page_number: int) -> str:
        image_path = report_dir.parents[2] / "images" / f"page_{page_number:03d}.png"
        return (Path("../../../images") / image_path.name).as_posix()

    def _report_dir(self, course_id: int, report_id: int, mode: str) -> Path:
        return ensure_dir(
            resolve_project_path(settings.storage_dir)
            / f"course_{course_id:03d}"
            / "reports"
            / mode
            / f"report_{report_id:03d}"
        )

    def _write_report_file(self, course_id: int, report_id: int, mode: str, content: str) -> str:
        report_dir = self._report_dir(course_id, report_id, mode)
        report_path = report_dir / "final_report.md"
        report_path.write_text(content, encoding="utf-8")
        return str(report_path.resolve())

    def _write_image_insert_plan(self, course_id: int, report_id: int, mode: str, plan: dict[str, Any]) -> str:
        report_dir = self._report_dir(course_id, report_id, mode)
        plan_path = report_dir / "image_insert_plan.json"
        plan_path.write_text(self._json_dump(plan), encoding="utf-8")
        return str(plan_path.resolve())

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _preview(self, text: str, max_chars: int = 2000) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "\n..."

    def _json_dump(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
