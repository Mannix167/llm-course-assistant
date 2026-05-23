from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.parser_service import PDFParserService


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a PDF into page text, screenshots, and metadata.")
    parser.add_argument("pdf_path", help="Path to the PDF file.")
    parser.add_argument("course_dir", help="Output course storage directory.")
    parser.add_argument("--image-scale", type=float, default=2.0, help="Page render scale. Default: 2.0")
    args = parser.parse_args()

    result = PDFParserService(image_scale=args.image_scale).parse(
        pdf_path=Path(args.pdf_path),
        course_dir=Path(args.course_dir),
    )
    print(
        json.dumps(
            {
                "source_pdf": result.source_pdf,
                "original_pdf": result.original_pdf,
                "pages_json": result.pages_json,
                "page_count": result.page_count,
                "scanned_like": result.scanned_like,
                "visual_candidate_pages": [
                    page.page_number for page in result.pages if page.candidate_for_visual
                ],
                "llm_review_pages": [
                    page.page_number for page in result.pages if page.llm_review_needed
                ],
                "pages": [asdict(page) for page in result.pages],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
