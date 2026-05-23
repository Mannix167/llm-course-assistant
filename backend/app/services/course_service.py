from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import resolve_project_path, settings
from app.database.models import Course, CourseFolder, Page, Report
from app.services.parser_service import PDFParseResult, PDFParserService
from app.utils.file_utils import ensure_dir


class CourseService:
    def __init__(self, parser_service: PDFParserService | None = None) -> None:
        self.parser_service = parser_service or PDFParserService()

    def create_uploaded_course(
        self,
        db: Session,
        source_file_path: str | Path,
        original_file_name: str | None = None,
        title: str | None = None,
        folder_id: int | None = None,
    ) -> Course:
        source_path = Path(source_file_path).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Upload source file not found: {source_path}")

        file_name = original_file_name or source_path.name
        course_title = title or Path(file_name).stem
        file_type = Path(file_name).suffix.lower().lstrip(".") or "pdf"
        folder = db.get(CourseFolder, folder_id) if folder_id else None
        if folder_id and folder is None:
            raise ValueError(f"Folder {folder_id} not found.")

        course = Course(
            folder_id=folder.id if folder else None,
            title=course_title,
            file_name=file_name,
            file_type=file_type,
            file_path="",
            page_count=0,
            status="uploaded",
            scanned_like=False,
            pages_json_path=None,
        )
        db.add(course)
        db.flush()

        upload_path = self._build_upload_file_path(course.id, file_name)
        shutil.copy2(source_path, upload_path)
        course.file_path = str(upload_path)

        db.commit()
        db.refresh(course)
        return course

    def parse_existing_course(self, db: Session, course_id: int) -> Course:
        course = db.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course {course_id} not found.")
        if course.file_type.lower() != "pdf":
            raise ValueError("Only PDF files are supported.")

        storage_dir = self._build_storage_dir(course.id)
        course.status = "parsing"
        db.flush()

        parse_result = self.parser_service.parse(pdf_path=course.file_path, course_dir=storage_dir)
        self._apply_parse_result_to_course(
            db=db,
            course=course,
            parse_result=parse_result,
            course_dir=storage_dir,
        )
        db.commit()
        db.refresh(course)
        return course

    def list_courses(self, db: Session) -> list[dict]:
        rows = (
            db.query(Course, func.count(Report.id))
            .outerjoin(Report, Report.course_id == Course.id)
            .group_by(Course.id)
            .order_by(Course.id.asc())
            .all()
        )
        return [
            {
                "course_id": course.id,
                "folder_id": course.folder_id,
                "folder_name": course.folder.name if course.folder else None,
                "title": course.title,
                "file_name": course.file_name,
                "file_type": course.file_type,
                "page_count": course.page_count,
                "status": course.status,
                "scanned_like": course.scanned_like,
                "report_count": report_count,
                "created_at": course.created_at.isoformat() if course.created_at else None,
                "updated_at": course.updated_at.isoformat() if course.updated_at else None,
            }
            for course, report_count in rows
        ]

    def get_course_detail(self, db: Session, course_id: int) -> dict | None:
        course = db.get(Course, course_id)
        if course is None:
            return None
        report_count = db.scalar(select(func.count(Report.id)).where(Report.course_id == course_id)) or 0
        return {
            "course_id": course.id,
            "folder_id": course.folder_id,
            "folder_name": course.folder.name if course.folder else None,
            "title": course.title,
            "file_name": course.file_name,
            "file_type": course.file_type,
            "file_path": course.file_path,
            "page_count": course.page_count,
            "status": course.status,
            "scanned_like": course.scanned_like,
            "pages_json_path": course.pages_json_path,
            "report_count": report_count,
            "created_at": course.created_at.isoformat() if course.created_at else None,
            "updated_at": course.updated_at.isoformat() if course.updated_at else None,
        }

    def delete_course(self, db: Session, course_id: int) -> bool:
        course = db.get(Course, course_id)
        if course is None:
            return False

        storage_dir = Path(course.pages_json_path).resolve().parent if course.pages_json_path else None
        file_path = Path(course.file_path).resolve() if course.file_path else None

        db.delete(course)
        db.commit()

        if storage_dir and storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)

        if file_path and file_path.exists():
            try:
                if not storage_dir or storage_dir not in file_path.parents:
                    file_path.unlink(missing_ok=True)
            except OSError:
                pass

        return True

    def list_folders(self, db: Session) -> list[dict]:
        rows = (
            db.query(CourseFolder, func.count(Course.id))
            .outerjoin(Course, Course.folder_id == CourseFolder.id)
            .group_by(CourseFolder.id)
            .order_by(CourseFolder.name.asc())
            .all()
        )
        return [
            {
                "folder_id": folder.id,
                "name": folder.name,
                "description": folder.description,
                "course_count": course_count,
                "created_at": folder.created_at.isoformat() if folder.created_at else None,
                "updated_at": folder.updated_at.isoformat() if folder.updated_at else None,
            }
            for folder, course_count in rows
        ]

    def create_folder(self, db: Session, name: str, description: str | None = None) -> CourseFolder:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Folder name is required.")
        existing = db.scalar(select(CourseFolder).where(CourseFolder.name == clean_name))
        if existing is not None:
            raise ValueError(f"Folder '{clean_name}' already exists.")
        folder = CourseFolder(name=clean_name, description=(description or "").strip() or None)
        db.add(folder)
        db.commit()
        db.refresh(folder)
        return folder

    def update_folder(self, db: Session, folder_id: int, name: str, description: str | None = None) -> CourseFolder:
        folder = db.get(CourseFolder, folder_id)
        if folder is None:
            raise ValueError(f"Folder {folder_id} not found.")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Folder name is required.")
        duplicate = db.scalar(select(CourseFolder).where(CourseFolder.name == clean_name, CourseFolder.id != folder_id))
        if duplicate is not None:
            raise ValueError(f"Folder '{clean_name}' already exists.")
        folder.name = clean_name
        folder.description = (description or "").strip() or None
        db.commit()
        db.refresh(folder)
        return folder

    def delete_folder(self, db: Session, folder_id: int) -> bool:
        folder = db.get(CourseFolder, folder_id)
        if folder is None:
            return False
        db.query(Course).filter(Course.folder_id == folder_id).update({"folder_id": None})
        db.delete(folder)
        db.commit()
        return True

    def move_course_to_folder(self, db: Session, course_id: int, folder_id: int | None) -> Course:
        course = db.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course {course_id} not found.")
        if folder_id is not None and db.get(CourseFolder, folder_id) is None:
            raise ValueError(f"Folder {folder_id} not found.")
        course.folder_id = folder_id
        db.commit()
        db.refresh(course)
        return course

    def parse_pdf_to_course(
        self,
        db: Session,
        pdf_path: str | Path,
        course_dir: str | Path,
        title: str | None = None,
    ) -> Course:
        parse_result = self.parser_service.parse(pdf_path=pdf_path, course_dir=course_dir)
        course = self._upsert_course_from_parse_result(
            db=db,
            parse_result=parse_result,
            course_dir=course_dir,
            title=title,
        )
        db.commit()
        db.refresh(course)
        return course

    def _upsert_course_from_parse_result(
        self,
        db: Session,
        parse_result: PDFParseResult,
        course_dir: str | Path,
        title: str | None = None,
    ) -> Course:
        source_path = Path(parse_result.source_pdf)
        target_dir = Path(course_dir).resolve()
        course_title = title or source_path.stem
        original_pdf_path = str((target_dir / parse_result.original_pdf).resolve())
        pages_json_path = str((target_dir / parse_result.pages_json).resolve())

        existing = db.scalar(select(Course).where(Course.file_path == original_pdf_path))
        if existing is None:
            course = Course(
                title=course_title,
                file_name=source_path.name,
                file_type=source_path.suffix.lower().lstrip("."),
                file_path=original_pdf_path,
                page_count=parse_result.page_count,
                status="parsed",
                scanned_like=parse_result.scanned_like,
                pages_json_path=pages_json_path,
            )
            db.add(course)
            db.flush()
        else:
            course = existing

        course.title = course_title
        course.file_name = source_path.name
        course.file_type = source_path.suffix.lower().lstrip(".")
        self._apply_parse_result_to_course(
            db=db,
            course=course,
            parse_result=parse_result,
            course_dir=course_dir,
        )
        course.file_path = original_pdf_path
        course.pages_json_path = pages_json_path
        return course

    def _apply_parse_result_to_course(
        self,
        db: Session,
        course: Course,
        parse_result: PDFParseResult,
        course_dir: str | Path,
    ) -> None:
        course_dir_path = Path(course_dir).resolve()
        original_pdf_path = str((course_dir_path / parse_result.original_pdf).resolve())
        pages_json_path = str((course_dir_path / parse_result.pages_json).resolve())

        course.page_count = parse_result.page_count
        course.status = "parsed"
        course.scanned_like = parse_result.scanned_like
        course.file_path = original_pdf_path
        course.pages_json_path = pages_json_path

        db.query(Page).filter(Page.course_id == course.id).delete()
        db.flush()

        for parsed_page in parse_result.pages:
            db.add(
                Page(
                    course_id=course.id,
                    page_number=parsed_page.page_number,
                    text=parsed_page.text,
                    analysis_text=parsed_page.analysis_text,
                    image_path=parsed_page.image_path,
                    text_length=parsed_page.text_length,
                    analysis_text_length=parsed_page.analysis_text_length,
                    image_count=parsed_page.image_count,
                    width=parsed_page.width,
                    height=parsed_page.height,
                    need_ocr=parsed_page.need_ocr,
                    page_type=parsed_page.page_type,
                    candidate_for_visual=parsed_page.candidate_for_visual,
                    exclude_text_from_llm=parsed_page.exclude_text_from_llm,
                    llm_review_needed=parsed_page.llm_review_needed,
                    candidate_reasons=parsed_page.candidate_reasons,
                    layout_flags=parsed_page.layout_flags,
                    features=parsed_page.features,
                )
            )

    def _build_upload_file_path(self, course_id: int, file_name: str) -> Path:
        upload_root = ensure_dir(resolve_project_path(settings.upload_dir))
        safe_name = Path(file_name).name
        return upload_root / f"course_{course_id:03d}_{safe_name}"

    def _build_storage_dir(self, course_id: int) -> Path:
        storage_root = ensure_dir(resolve_project_path(settings.storage_dir))
        return ensure_dir(storage_root / f"course_{course_id:03d}")
