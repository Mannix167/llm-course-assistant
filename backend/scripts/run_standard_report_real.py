from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database.db import SessionLocal, init_db
from app.database.models import Course
from app.services.course_service import CourseService
from app.services.report_service import ReportService


def ensure_course(course_id: int | None, pdf_path: Path | None) -> int:
    init_db()
    with SessionLocal() as db:
        if course_id is not None:
            course = db.get(Course, course_id)
            if course is None:
                raise ValueError(f"Course {course_id} not found.")
            if course.status != "parsed":
                course = CourseService().parse_existing_course(db, course.id)
            return course.id

        if pdf_path is None:
            existing = db.query(Course).filter(Course.status == "parsed").order_by(Course.id.asc()).first()
            if existing is not None:
                return existing.id
            pdf_path = Path(r"D:\course learn agent\3 经典单方程模型 1.pdf")

        course = CourseService().create_uploaded_course(db, pdf_path, original_file_name=pdf_path.name)
        course = CourseService().parse_existing_course(db, course.id)
        return course.id


def clip(text: str | None, limit: int) -> str:
    value = text or ""
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n..."


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real report generation with configured LLM.")
    parser.add_argument("--course-id", type=int, default=None)
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--mode", default="standard", choices=["standard", "advanced", "extended"])
    parser.add_argument("--preview-chars", type=int, default=2200)
    args = parser.parse_args()

    course_id = ensure_course(args.course_id, args.pdf)
    with SessionLocal() as db:
        report = ReportService().create_report(db=db, course_id=course_id, mode=args.mode)
        detail = ReportService().get_report_detail(db, report.id)
        steps = ReportService().list_report_steps(db, report.id)

    print(
        json.dumps(
            {
                "course_id": course_id,
                "report_id": report.id,
                "status": report.status,
                "report_path": report.report_path,
                "steps": [
                    {
                        "step_name": step["step_name"],
                        "status": step["status"],
                        "output_preview": clip(step["output_content"], 500),
                    }
                    for step in steps
                ],
                "outline_markdown": detail["outline_markdown"],
                "summary_markdown": detail["summary_markdown"],
                "content_preview": clip(detail["content_markdown"], args.preview_chars),
                "final_markdown_preview": clip(detail["final_markdown"], args.preview_chars),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
