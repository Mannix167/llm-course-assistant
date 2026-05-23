from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    pdf_path = Path(r"D:\course learn agent\3 经典单方程模型 1.pdf")
    with TestClient(app) as client:
        initial_courses = client.get("/api/courses")
        initial_courses.raise_for_status()
        initial_courses_data = initial_courses.json()

        with pdf_path.open("rb") as file_obj:
            upload_response = client.post(
                "/api/upload",
                files={"file": (pdf_path.name, file_obj, "application/pdf")},
            )
        upload_response.raise_for_status()
        uploaded = upload_response.json()
        course_id = int(uploaded["course_id"])

        parse_response = client.post(f"/api/courses/{course_id}/parse")
        parse_response.raise_for_status()

        course_detail = client.get(f"/api/courses/{course_id}")
        course_detail.raise_for_status()

        course_reports = client.get(f"/api/courses/{course_id}/reports")
        course_reports.raise_for_status()

        delete_response = client.delete(f"/api/courses/{course_id}")
        delete_response.raise_for_status()

        final_courses = client.get("/api/courses")
        final_courses.raise_for_status()

    print(
        json.dumps(
            {
                "initial_course_count": len(initial_courses_data),
                "uploaded_course_id": course_id,
                "course_detail": course_detail.json(),
                "report_count_for_uploaded_course": len(course_reports.json()),
                "delete_course_response": delete_response.json(),
                "final_course_count": len(final_courses.json()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
