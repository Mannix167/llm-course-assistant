from __future__ import annotations

import html
import re
import tempfile
from pathlib import Path

import fitz
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import SessionLocal, get_db
from app.database.models import Course, Report
from app.services.report_service import ReportService


router = APIRouter(prefix="/api", tags=["reports"])


class CreateReportRequest(BaseModel):
    mode: str = "standard"


class UpdateReportMarkdownRequest(BaseModel):
    final_markdown: str


def _generate_report_background(report_id: int) -> None:
    db = SessionLocal()
    try:
        ReportService().generate_existing_report(db=db, report_id=report_id)
    finally:
        db.close()


@router.post("/courses/{course_id}/reports")
def create_course_report(
    course_id: int,
    request: CreateReportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    try:
        report = ReportService().create_report_record(db=db, course_id=course_id, mode=request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Report generation failed: {exc}") from exc

    background_tasks.add_task(_generate_report_background, report.id)
    return {
        "report_id": report.id,
        "course_id": report.course_id,
        "mode": report.mode,
        "status": report.status,
    }


@router.get("/courses/{course_id}/reports")
def list_course_reports(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course {course_id} not found.")

    reports = db.query(Report).filter(Report.course_id == course_id).order_by(Report.id.asc()).all()
    return [
        {
            "report_id": report.id,
            "course_id": report.course_id,
            "mode": report.mode,
            "status": report.status,
            "report_path": report.report_path,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        }
        for report in reports
    ]


@router.get("/reports/{report_id}")
def get_report_detail(report_id: int, db: Session = Depends(get_db)) -> dict:
    report = ReportService().get_report_detail(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found.")
    return report


@router.get("/reports/{report_id}/steps")
def list_report_steps(report_id: int, db: Session = Depends(get_db)) -> list[dict]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found.")
    return ReportService().list_report_steps(db, report_id)


@router.post("/reports/{report_id}/stop")
def stop_report_generation(report_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        report = ReportService().request_stop_report_generation(db, report_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"report_id": report.id, "status": report.status}


@router.put("/reports/{report_id}/markdown")
def update_report_markdown(report_id: int, request: UpdateReportMarkdownRequest, db: Session = Depends(get_db)) -> dict:
    try:
        report = ReportService().update_report_markdown(db, report_id, request.final_markdown)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {
        "report_id": report.id,
        "course_id": report.course_id,
        "mode": report.mode,
        "status": report.status,
        "report_path": report.report_path,
        "final_markdown": report.final_markdown,
    }


@router.get("/reports/{report_id}/download.md")
def download_report_markdown(report_id: int, db: Session = Depends(get_db)) -> FileResponse:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found.")
    if not report.report_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This report has no markdown file.")

    from pathlib import Path

    report_path = Path(report.report_path).resolve()
    if not report_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report file not found: {report_path}")

    filename = f"course_report_{report.id}_{report.mode}.md"
    return FileResponse(
        report_path,
        media_type="text/markdown; charset=utf-8",
        filename=filename,
    )


@router.get("/reports/{report_id}/download.pdf")
def download_report_pdf(report_id: int, db: Session = Depends(get_db)) -> FileResponse:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found.")
    if not report.final_markdown:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This report has no markdown content.")

    pdf_path = Path(tempfile.gettempdir()) / f"course_report_{report.id}_{report.mode}.pdf"
    _write_report_pdf(report, pdf_path)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"course_report_{report.id}_{report.mode}.pdf",
    )


def _write_report_pdf(report: Report, pdf_path: Path) -> None:
    try:
        _write_weasyprint_pdf(report, pdf_path)
    except Exception:
        _write_basic_pdf(report.final_markdown or "", pdf_path)


def _write_weasyprint_pdf(report: Report, pdf_path: Path) -> None:
    import markdown
    from weasyprint import HTML

    report_markdown = _normalize_markdown_for_pdf(report.final_markdown or "")
    body = markdown.markdown(
        report_markdown,
        extensions=["extra", "tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )
    html_text = _build_report_html(body, report)
    base_url = str(Path(report.report_path).resolve().parent) if report.report_path else str(Path.cwd())
    HTML(string=html_text, base_url=base_url).write_pdf(str(pdf_path))


def _normalize_markdown_for_pdf(markdown: str) -> str:
    text = re.sub(r"<mark(?:\s+data-note=\"highlight\")?>(.*?)</mark>", r"<mark>\1</mark>", markdown, flags=re.DOTALL)
    return text


def _build_report_html(body: str, report: Report) -> str:
    title = f"Course Report #{report.id}"
    css = """
    @page {
      size: A4;
      margin: 22mm 18mm 20mm;
      @bottom-center {
        content: counter(page) " / " counter(pages);
        color: #71717a;
        font-size: 9pt;
      }
    }
    * { box-sizing: border-box; }
    body {
      color: #18181b;
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif;
      font-size: 11pt;
      line-height: 1.74;
    }
    h1, h2, h3, h4 {
      color: #09090b;
      line-height: 1.32;
      page-break-after: avoid;
    }
    h1 {
      border-bottom: 2px solid #18181b;
      font-size: 24pt;
      margin: 0 0 18pt;
      padding-bottom: 10pt;
    }
    h2 {
      border-bottom: 1px solid #d4d4d8;
      font-size: 17pt;
      margin: 22pt 0 10pt;
      padding-bottom: 5pt;
    }
    h3 { font-size: 14pt; margin: 17pt 0 7pt; }
    h4 { font-size: 12pt; margin: 13pt 0 5pt; }
    p { margin: 0 0 8pt; }
    a { color: #1d4ed8; text-decoration: none; }
    ul, ol { margin: 0 0 10pt 18pt; padding: 0; }
    li { margin: 2pt 0; }
    blockquote {
      background: #f8fafc;
      border-left: 4px solid #94a3b8;
      color: #334155;
      margin: 10pt 0;
      padding: 8pt 11pt;
    }
    table {
      border-collapse: collapse;
      font-size: 9.5pt;
      margin: 10pt 0 14pt;
      width: 100%;
    }
    th, td {
      border: 1px solid #d4d4d8;
      padding: 5pt 6pt;
      vertical-align: top;
    }
    th { background: #f4f4f5; font-weight: 700; }
    code {
      background: #f4f4f5;
      border-radius: 3pt;
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 9.5pt;
      padding: 1pt 3pt;
    }
    pre {
      background: #18181b;
      border-radius: 5pt;
      color: #f4f4f5;
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 9pt;
      line-height: 1.5;
      margin: 10pt 0 14pt;
      padding: 10pt;
      white-space: pre-wrap;
    }
    pre code { background: transparent; color: inherit; padding: 0; }
    img {
      display: block;
      margin: 10pt auto;
      max-height: 170mm;
      max-width: 100%;
      object-fit: contain;
    }
    mark {
      background: #fde68a;
      border-radius: 2pt;
      padding: 0 2pt;
    }
    hr { border: 0; border-top: 1px solid #e4e4e7; margin: 16pt 0; }
    .meta {
      color: #71717a;
      font-size: 9.5pt;
      margin-bottom: 16pt;
    }
    """
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <title>{html.escape(title)}</title>
    <style>{css}</style>
  </head>
  <body>
    <div class="meta">报告 #{report.id} · {html.escape(report.mode)} 模式</div>
    {body}
  </body>
</html>"""


def _write_basic_pdf(markdown: str, pdf_path: Path) -> None:
    doc = fitz.open()
    font_path = _find_chinese_font()
    font_name = "helv"
    margin = 42
    page_width = 595
    page_height = 842

    page = doc.new_page(width=page_width, height=page_height)
    y = margin
    in_code = False

    def ensure_space(required: float) -> None:
        nonlocal page, y
        if y + required <= page_height - margin:
            return
        page = doc.new_page(width=page_width, height=page_height)
        y = margin

    def write_line(text: str, x: float, font_size: float, color: tuple[float, float, float] = (0, 0, 0), line_height: float | None = None) -> None:
        nonlocal y
        ensure_space(line_height or font_size * 1.65)
        if font_path:
            page.insert_text((x, y), text, fontsize=font_size, fontname="msyh", fontfile=font_path, color=color)
        else:
            page.insert_text((x, y), text, fontsize=font_size, fontname=font_name, color=color)
        y += line_height or font_size * 1.65

    def write_wrapped(text: str, x: float, font_size: float, max_chars: int, color: tuple[float, float, float] = (0, 0, 0)) -> None:
        clean = _clean_inline_markdown(text)
        for line in _wrap_text(clean, max_chars):
            write_line(line, x, font_size, color=color)

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            y += 4
            continue
        if not line.strip():
            y += 7
            continue
        if line.strip() == "---":
            ensure_space(18)
            page.draw_line((margin, y), (page_width - margin, y), color=(0.82, 0.82, 0.86), width=0.8)
            y += 16
            continue

        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", line.strip())
        if image_match:
            write_wrapped(f"[图片] {image_match.group(1) or image_match.group(2)}", margin, 9.5, 54, color=(0.38, 0.38, 0.44))
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            text = _clean_inline_markdown(heading.group(2))
            sizes = {1: 18, 2: 15, 3: 12.5, 4: 11.5, 5: 10.5, 6: 10.5}
            y += 8 if level <= 2 else 4
            write_wrapped(text, margin, sizes.get(level, 10.5), 34 if level == 1 else 42)
            if level <= 2:
                ensure_space(8)
                page.draw_line((margin, y - 3), (page_width - margin, y - 3), color=(0.82, 0.82, 0.86), width=0.7)
            continue

        if in_code:
            write_wrapped(line, margin + 10, 8.8, 62, color=(0.12, 0.12, 0.14))
            continue

        if "|" in line and line.count("|") >= 2:
            write_wrapped(line, margin, 8.8, 70, color=(0.18, 0.18, 0.2))
            continue

        list_item = re.match(r"^\s*([-*+]|\d+\.)\s+(.+)$", line)
        if list_item:
            marker = "•" if not list_item.group(1).endswith(".") else list_item.group(1)
            write_wrapped(f"{marker} {list_item.group(2)}", margin + 10, 10.2, 45)
            continue

        write_wrapped(line, margin, 10.5, 46)

    doc.save(pdf_path)
    doc.close()


def _clean_inline_markdown(text: str) -> str:
    text = re.sub(r"<mark(?:\s+data-note=\"highlight\")?>(.*?)</mark>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"!\[(.*?)\]\((.*?)\)", r"[图片] \1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _markdown_to_plain_text(markdown: str) -> str:
    text = re.sub(r"!\[(.*?)\]\((.*?)\)", r"[图片] \1", markdown)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^\s*[-*]\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _wrap_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _find_chinese_font() -> str | None:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Report {report_id} not found.")

    db.delete(report)
    db.commit()
    return {"deleted": True}
