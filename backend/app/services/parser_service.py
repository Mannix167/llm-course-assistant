from __future__ import annotations

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import fitz


VISUAL_KEYWORDS = (
    "图表",
    "图示",
    "表格",
    "如下图",
    "如下表",
    "曲线",
    "结构",
    "框架",
    "流程",
    "示意",
    "公式",
    "矩阵",
    "概率分布",
    "figure",
    "table",
    "chart",
    "diagram",
    "matrix",
)

STRONG_VISUAL_KEYWORDS = (
    "图表",
    "图示",
    "表格",
    "如下图",
    "如下表",
    "曲线",
    "流程",
    "示意",
    "公式",
    "矩阵",
    "figure",
    "table",
    "chart",
    "diagram",
    "matrix",
)

MATH_SYMBOLS = set("=+-*/^∑∫∂∞≈≤≥βασμλθπσΩˆ")
TABLE_LINE_RE = re.compile(r"^\s*[\d\.\(\)（）\-]+\s*$")


@dataclass(slots=True)
class PageFeatures:
    text_block_count: int
    image_block_count: int
    drawing_count: int
    large_drawing_count: int
    line_count: int
    short_line_ratio: float
    numeric_char_ratio: float
    math_char_ratio: float
    empty_line_ratio: float
    average_line_length: float
    max_font_size: float
    table_like_score: float
    formula_like_score: float
    visual_object_score: float


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str
    analysis_text: str
    image_path: str
    text_length: int
    analysis_text_length: int
    image_count: int
    width: float
    height: float
    need_ocr: bool
    page_type: str
    candidate_for_visual: bool
    exclude_text_from_llm: bool
    llm_review_needed: bool
    candidate_reasons: list[str] = field(default_factory=list)
    layout_flags: list[str] = field(default_factory=list)
    features: dict[str, float | int] = field(default_factory=dict)


@dataclass(slots=True)
class PDFParseResult:
    source_pdf: str
    original_pdf: str
    pages_json: str
    page_count: int
    scanned_like: bool
    pages: list[ParsedPage]


class PDFParserService:
    def __init__(self, image_scale: float = 2.0) -> None:
        self.image_scale = image_scale

    def parse(self, pdf_path: str | Path, course_dir: str | Path) -> PDFParseResult:
        source_pdf = Path(pdf_path).resolve()
        if not source_pdf.exists():
            raise FileNotFoundError(f"PDF file not found: {source_pdf}")
        if source_pdf.suffix.lower() != ".pdf":
            raise ValueError(f"Only PDF files are supported: {source_pdf.name}")

        target_dir = Path(course_dir).resolve()
        original_dir = target_dir / "original"
        images_dir = target_dir / "images"
        original_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        original_pdf = original_dir / source_pdf.name
        if source_pdf != original_pdf:
            shutil.copy2(source_pdf, original_pdf)

        pages: list[ParsedPage] = []
        render_jobs: list[tuple[int, Path]] = []
        with fitz.open(source_pdf) as document:
            for index, page in enumerate(document, start=1):
                page_dict = page.get_text("dict")
                text = self._extract_text(page)
                text_length = len(text)
                image_count = len(page.get_images(full=True))
                image_path = images_dir / f"page_{index:03d}.png"
                render_jobs.append((index - 1, image_path))

                features = self._extract_features(page, page_dict, text, image_count)
                page_type, candidate_for_visual, exclude_text_from_llm, llm_review_needed, candidate_reasons, layout_flags = self._classify_page(
                    text=text,
                    text_length=text_length,
                    features=features,
                )
                analysis_text = self._build_analysis_text(text, page_type, exclude_text_from_llm)

                feature_payload = asdict(features)
                feature_payload.update(self._build_structured_text_features(text))
                pages.append(
                    ParsedPage(
                        page_number=index,
                        text=text,
                        analysis_text=analysis_text,
                        image_path=self._relative_path(image_path, target_dir),
                        text_length=text_length,
                        analysis_text_length=len(analysis_text),
                        image_count=image_count,
                        width=round(float(page.rect.width), 2),
                        height=round(float(page.rect.height), 2),
                        need_ocr=text_length < 50,
                        page_type=page_type,
                        candidate_for_visual=candidate_for_visual,
                        exclude_text_from_llm=exclude_text_from_llm,
                        llm_review_needed=llm_review_needed,
                        candidate_reasons=candidate_reasons,
                        layout_flags=layout_flags,
                        features=feature_payload,
                    )
                )

        self._render_pages_parallel(source_pdf, render_jobs)

        scanned_like = self._is_scanned_like(pages)
        pages_json = target_dir / "pages.json"
        pages_json.write_text(
            json.dumps([asdict(page) for page in pages], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return PDFParseResult(
            source_pdf=str(source_pdf),
            original_pdf=self._relative_path(original_pdf, target_dir),
            pages_json=self._relative_path(pages_json, target_dir),
            page_count=len(pages),
            scanned_like=scanned_like,
            pages=pages,
        )

    def _extract_text(self, page: fitz.Page) -> str:
        text = page.get_text("text", sort=True)
        return self._clean_extracted_text(text)

    def _clean_extracted_text(self, text: str) -> str:
        raw_lines = [self._normalize_line(line) for line in text.replace("\x00", "").splitlines()]
        lines = [line for line in raw_lines if line and not self._is_noise_line(line)]
        return "\n".join(self._merge_wrapped_lines(lines)).strip()

    def _normalize_line(self, line: str) -> str:
        line = line.replace("\u3000", " ")
        line = re.sub(r"\s+", " ", line).strip()
        line = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", line)
        return line

    def _is_noise_line(self, line: str) -> bool:
        if re.fullmatch(r"[-–—_]{2,}", line):
            return True
        if re.fullmatch(r"(第\s*)?\d{1,4}\s*(页|/|／)?\s*\d{0,4}", line):
            return True
        if re.fullmatch(r"\d{1,4}", line):
            return True
        return len(line) <= 2 and not re.search(r"[\u4e00-\u9fffA-Za-z]", line)

    def _merge_wrapped_lines(self, lines: list[str]) -> list[str]:
        merged: list[str] = []
        for line in lines:
            if not merged:
                merged.append(line)
                continue
            previous = merged[-1]
            should_merge = (
                len(previous) >= 16
                and len(line) >= 6
                and not re.search(r"[。！？；：.!?;:]$", previous)
                and not re.match(r"^(\d+[\.、]|[-•●])", line)
                and not self._looks_like_table_line(previous)
                and not self._looks_like_table_line(line)
            )
            if should_merge:
                merged[-1] = previous + line
            else:
                merged.append(line)
        return merged

    def _render_page(self, page: fitz.Page, image_path: Path) -> None:
        matrix = fitz.Matrix(self.image_scale, self.image_scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(image_path)

    def _render_pages_parallel(self, pdf_path: Path, render_jobs: list[tuple[int, Path]]) -> None:
        if not render_jobs:
            return
        max_workers = min(4, len(render_jobs))
        if max_workers <= 1:
            for page_index, image_path in render_jobs:
                self._render_page_from_pdf(pdf_path, page_index, image_path)
            return

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._render_page_from_pdf, pdf_path, page_index, image_path)
                for page_index, image_path in render_jobs
            ]
            for future in as_completed(futures):
                future.result()

    def _render_page_from_pdf(self, pdf_path: Path, page_index: int, image_path: Path) -> None:
        with fitz.open(pdf_path) as document:
            page = document.load_page(page_index)
            self._render_page(page, image_path)

    def _extract_features(
        self,
        page: fitz.Page,
        page_dict: dict,
        text: str,
        image_count: int,
    ) -> PageFeatures:
        blocks = page_dict.get("blocks", [])
        text_blocks = [block for block in blocks if block.get("type") == 0]
        image_blocks = [block for block in blocks if block.get("type") == 1]
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        non_space_text = "".join(ch for ch in text if not ch.isspace())
        text_chars = len(non_space_text) or 1
        digits = sum(ch.isdigit() for ch in non_space_text)
        math_chars = sum(ch in MATH_SYMBOLS for ch in non_space_text)
        short_lines = sum(1 for line in lines if len(line) <= 18)
        empty_line_ratio = 0.0
        if text:
            raw_lines = text.splitlines()
            empty_line_ratio = round(sum(1 for line in raw_lines if not line.strip()) / max(len(raw_lines), 1), 3)

        line_count = len(lines)
        average_line_length = round(sum(len(line) for line in lines) / max(line_count, 1), 2)
        max_font_size = self._extract_max_font_size(text_blocks)
        drawing_count = len(page.get_drawings())
        large_drawing_count = self._count_large_drawings(page, drawing_count)

        normalized_text = text.lower()
        visual_keyword_hits = sum(1 for keyword in VISUAL_KEYWORDS if keyword in normalized_text)
        table_like_score = self._score_table_like(lines, digits / text_chars, average_line_length)
        formula_like_score = self._score_formula_like(lines, math_chars / text_chars, drawing_count)
        visual_object_score = round(
            image_count * 1.5
            + len(image_blocks) * 1.2
            + min(large_drawing_count / 4, 2.0)
            + visual_keyword_hits * 0.35,
            3,
        )

        return PageFeatures(
            text_block_count=len(text_blocks),
            image_block_count=len(image_blocks),
            drawing_count=drawing_count,
            large_drawing_count=large_drawing_count,
            line_count=line_count,
            short_line_ratio=round(short_lines / max(line_count, 1), 3),
            numeric_char_ratio=round(digits / text_chars, 3),
            math_char_ratio=round(math_chars / text_chars, 3),
            empty_line_ratio=empty_line_ratio,
            average_line_length=average_line_length,
            max_font_size=round(max_font_size, 2),
            table_like_score=table_like_score,
            formula_like_score=formula_like_score,
            visual_object_score=visual_object_score,
        )

    def _extract_max_font_size(self, text_blocks: list[dict]) -> float:
        max_size = 0.0
        for block in text_blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    max_size = max(max_size, float(span.get("size", 0.0)))
        return max_size

    def _count_large_drawings(self, page: fitz.Page, drawing_count: int) -> int:
        if drawing_count == 0:
            return 0
        page_area = float(page.rect.width * page.rect.height) or 1.0
        large = 0
        for drawing in page.get_drawings():
            rect = drawing.get("rect")
            if not rect:
                continue
            area = float(rect.width * rect.height)
            if area / page_area >= 0.035:
                large += 1
        return large

    def _score_table_like(self, lines: list[str], numeric_ratio: float, average_line_length: float) -> float:
        if not lines:
            return 0.0
        table_line_hits = sum(1 for line in lines if self._looks_like_table_line(line))
        dense_value_lines = sum(1 for line in lines if sum(ch.isdigit() for ch in line) >= 6)
        score = (
            table_line_hits / max(len(lines), 1) * 3.2
            + dense_value_lines / max(len(lines), 1) * 2.4
            + numeric_ratio * 3.0
        )
        if average_line_length < 18:
            score += 0.6
        return round(score, 3)

    def _score_formula_like(self, lines: list[str], math_ratio: float, drawing_count: int) -> float:
        if not lines:
            return 0.0
        formula_lines = sum(1 for line in lines if self._looks_like_formula_line(line))
        score = formula_lines / max(len(lines), 1) * 2.8 + math_ratio * 6.0
        if drawing_count >= 2:
            score += 0.4
        return round(score, 3)

    def _looks_like_table_line(self, line: str) -> bool:
        tokens = [token for token in re.split(r"\s+", line) if token]
        if len(tokens) < 4:
            return False
        numeric_tokens = sum(1 for token in tokens if self._is_numeric_like(token) or TABLE_LINE_RE.match(token))
        return numeric_tokens / len(tokens) >= 0.55

    def _looks_like_formula_line(self, line: str) -> bool:
        if len(line) < 8:
            return False
        math_hits = sum(ch in MATH_SYMBOLS for ch in line)
        return math_hits >= 2 or ("E(" in line and "|" in line)

    def _is_numeric_like(self, token: str) -> bool:
        cleaned = token.replace(".", "").replace("-", "").replace("%", "")
        return bool(cleaned) and cleaned.isdigit()

    def _classify_page(
        self,
        text: str,
        text_length: int,
        features: PageFeatures,
    ) -> tuple[str, bool, bool, bool, list[str], list[str]]:
        reasons: list[str] = []
        flags: list[str] = []

        if features.table_like_score >= 2.2:
            flags.append("table_like")
        if features.formula_like_score >= 1.8:
            flags.append("formula_like")
        if features.visual_object_score >= 1.6:
            flags.append("visual_objects_present")
        if features.short_line_ratio >= 0.55:
            flags.append("fragmented_layout")
        if features.max_font_size >= 24 and text_length <= 140:
            flags.append("title_sized_text")

        candidate_for_visual = False
        exclude_text_from_llm = False
        llm_review_needed = False
        page_type = "text"

        normalized_text = text.lower()
        has_strong_visual_keyword = any(keyword in normalized_text for keyword in STRONG_VISUAL_KEYWORDS)
        has_raster_visual = features.image_block_count > 0 or features.large_drawing_count >= 2

        if "table_like" in flags and features.numeric_char_ratio >= 0.18:
            page_type = "table_like"
            candidate_for_visual = True
            exclude_text_from_llm = True
            reasons.append("page contains dense numeric grid or tabular layout")
        elif "formula_like" in flags and (text_length <= 220 or has_raster_visual):
            page_type = "formula_like"
            candidate_for_visual = True
            exclude_text_from_llm = True
            reasons.append("page is dominated by formulas or symbolic expressions")
        elif has_raster_visual and text_length >= 160:
            page_type = "text_with_visual"
            candidate_for_visual = True
            reasons.append("page mixes narrative text with a meaningful visual object")
        elif has_raster_visual:
            page_type = "diagram_like"
            candidate_for_visual = True
            exclude_text_from_llm = text_length <= 120
            reasons.append("page contains embedded image or visual chart")
        elif "title_sized_text" in flags and features.line_count <= 4 and text_length <= 120:
            page_type = "title_or_transition"
            candidate_for_visual = False
            reasons.append("page is likely a section divider or title slide")
        elif has_strong_visual_keyword and text_length <= 220:
            page_type = "diagram_like"
            candidate_for_visual = True
            exclude_text_from_llm = text_length <= 120
            reasons.append("page references chart, formula, table, or structural diagram")

        if page_type == "text" and features.table_like_score >= 1.5:
            llm_review_needed = True
            reasons.append("rule-based signals suggest possible table-like content")
        if page_type == "text_with_visual" and features.table_like_score >= 1.6:
            llm_review_needed = True
            reasons.append("mixed page may need LLM disambiguation between text and table")
        if page_type == "diagram_like" and text_length > 220:
            llm_review_needed = True
            reasons.append("visual page also contains substantial text, needs finer judgment")
        if candidate_for_visual and not exclude_text_from_llm and text_length >= 120:
            llm_review_needed = True
            reasons.append("candidate visual page should be refined by LLM before report generation")
        if page_type == "text" and features.visual_object_score >= 4.5:
            llm_review_needed = True
            reasons.append("page has strong visual signals despite text-first classification")

        if not reasons:
            reasons.append("page is mainly suitable for normal text analysis")

        return page_type, candidate_for_visual, exclude_text_from_llm, llm_review_needed, reasons, flags

    def _build_analysis_text(self, text: str, page_type: str, exclude_text_from_llm: bool) -> str:
        if not text:
            return ""

        if exclude_text_from_llm:
            summary_lines = self._extract_summary_lines(text, max_lines=3, max_chars=180)
            if not summary_lines:
                return ""
            prefix = f"[{page_type}] "
            return prefix + " / ".join(summary_lines)

        if page_type == "text_with_visual":
            return self._trim_text(text, max_chars=1800)

        return text

    def _extract_summary_lines(self, text: str, max_lines: int, max_chars: int) -> list[str]:
        lines = []
        for line in text.splitlines():
            cleaned = " ".join(line.split())
            if not cleaned:
                continue
            if self._looks_like_table_line(cleaned):
                continue
            lines.append(cleaned)
            if len(lines) >= max_lines:
                break
        summary = []
        current_length = 0
        for line in lines:
            if current_length + len(line) > max_chars and summary:
                break
            summary.append(line)
            current_length += len(line)
        return summary

    def _trim_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."

    def _build_structured_text_features(self, text: str) -> dict[str, object]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title_candidates = [
            line
            for line in lines[:8]
            if 4 <= len(line) <= 48 and not self._looks_like_table_line(line) and not self._looks_like_formula_line(line)
        ][:3]
        summary = self._extract_summary_lines(text, max_lines=4, max_chars=260)
        non_space_chars = len("".join(ch for ch in text if not ch.isspace()))
        return {
            "page_summary": " / ".join(summary),
            "title_candidates": title_candidates,
            "clean_line_count": len(lines),
            "content_density": round(non_space_chars / max(len(lines), 1), 2),
        }

    def _is_scanned_like(self, pages: list[ParsedPage]) -> bool:
        if not pages:
            return False
        short_text_pages = sum(1 for page in pages if page.text_length < 50)
        return short_text_pages / len(pages) >= 0.6

    def _relative_path(self, path: Path, base_dir: Path) -> str:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
