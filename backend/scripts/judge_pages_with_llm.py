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

from app.services.page_judge_service import PageJudgeService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM page judgement on parsed pages.json.")
    parser.add_argument("pages_json", help="Path to parsed pages.json")
    parser.add_argument("--provider", default=None, help="Provider override, e.g. kimi or glm")
    parser.add_argument("--model", default=None, help="Model override, e.g. Kimi-K2.5")
    parser.add_argument("--batch-size", type=int, default=4, help="How many pages to send per LLM call")
    parser.add_argument("--include-images", action="store_true", help="Attach page screenshots in the LLM request")
    parser.add_argument("--image-base-dir", default=None, help="Base directory that contains the relative image_path files")
    parser.add_argument("--page-range", default=None, help="Inclusive page range like 1-8 or 12-12")
    parser.add_argument("--output", default=None, help="Optional path to save the JSON result")
    parser.add_argument("--boundary-only", action="store_true", help="Only judge pages where llm_review_needed=true")
    args = parser.parse_args()

    pages_path = Path(args.pages_json).resolve()
    pages = json.loads(pages_path.read_text(encoding="utf-8"))
    if args.page_range:
        start_page, end_page = parse_page_range(args.page_range)
        pages = [page for page in pages if start_page <= int(page["page_number"]) <= end_page]

    image_base_dir = args.image_base_dir or str(pages_path.parent)

    service = PageJudgeService()
    if args.boundary_only:
        result = service.judge_boundary_pages_in_batches(
            pages=pages,
            provider=args.provider,
            model=args.model,
            batch_size=args.batch_size,
            include_images=args.include_images,
            image_base_dir=image_base_dir,
        )
    else:
        result = service.judge_pages_in_batches(
            pages=pages,
            provider=args.provider,
            model=args.model,
            batch_size=args.batch_size,
            include_images=args.include_images,
            image_base_dir=image_base_dir,
        )
    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).resolve().write_text(output_text, encoding="utf-8")
    print(output_text)


def parse_page_range(value: str) -> tuple[int, int]:
    if "-" not in value:
        raise ValueError("page range must look like 1-8")
    start_text, end_text = value.split("-", 1)
    start_page = int(start_text)
    end_page = int(end_text)
    if start_page <= 0 or end_page <= 0 or end_page < start_page:
        raise ValueError(f"invalid page range: {value}")
    return start_page, end_page


if __name__ == "__main__":
    main()
