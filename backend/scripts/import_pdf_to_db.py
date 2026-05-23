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

from sqlalchemy import select
from sqlalchemy import func

from app.database.db import SessionLocal, init_db
from app.database.models import Page
from app.services.course_service import CourseService


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a PDF and import the result into SQLite.")
    parser.add_argument("pdf_path", help="Path to the PDF file.")
    parser.add_argument("course_dir", help="Output course storage directory.")
    parser.add_argument("--title", default=None, help="Optional course title override.")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        course = CourseService().parse_pdf_to_course(
            db=db,
            pdf_path=Path(args.pdf_path),
            course_dir=Path(args.course_dir),
            title=args.title,
        )

        page_count = db.scalar(select(func.count(Page.id)).where(Page.course_id == course.id))
        print(
            json.dumps(
                {
                    "course_id": course.id,
                    "title": course.title,
                    "status": course.status,
                    "page_count": course.page_count,
                    "db_page_count": page_count,
                    "pages_json_path": course.pages_json_path,
                    "scanned_like": course.scanned_like,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
