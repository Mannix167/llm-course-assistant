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
        with pdf_path.open("rb") as file_obj:
            upload_response = client.post(
                "/api/upload",
                files={"file": (pdf_path.name, file_obj, "application/pdf")},
            )
        upload_response.raise_for_status()
        upload_data = upload_response.json()
        course_id = int(upload_data["course_id"])

        parse_response = client.post(f"/api/courses/{course_id}/parse")
        parse_response.raise_for_status()
        parse_data = parse_response.json()

        pages_response = client.get(f"/api/courses/{course_id}/pages")
        pages_response.raise_for_status()
        pages_data = pages_response.json()

    print(
        json.dumps(
            {
                "upload": upload_data,
                "parse": parse_data,
                "pages_count": len(pages_data),
                "first_page": {
                    "page_number": pages_data[0]["page_number"],
                    "page_type": pages_data[0]["page_type"],
                    "candidate_for_visual": pages_data[0]["candidate_for_visual"],
                }
                if pages_data
                else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
