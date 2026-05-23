from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.llm_service import LLMService
from app.utils.prompt_loader import load_prompt


class PageJudgeService:
    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm_service = llm_service or LLMService()

    def build_candidate_pages_payload(self, pages: list[dict[str, Any]], max_text_chars: int = 1200) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for page in pages:
            payload.append(
                {
                    "page_number": page["page_number"],
                    "current_page_type": page["page_type"],
                    "candidate_for_visual": page["candidate_for_visual"],
                    "exclude_text_from_llm": page["exclude_text_from_llm"],
                    "candidate_reasons": page["candidate_reasons"],
                    "layout_flags": page["layout_flags"],
                    "analysis_text": page["analysis_text"][:max_text_chars],
                    "features": page["features"],
                }
            )
        return payload

    def filter_boundary_pages(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [page for page in pages if bool(page.get("llm_review_needed"))]

    def judge_pages(
        self,
        pages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        include_images: bool = False,
        image_base_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        prompt = load_prompt("page_judgement.md")
        payload = self.build_candidate_pages_payload(pages)
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请审查以下经过规则解析后的课件页面，只返回页级精判 JSON。"
                    "请使用中文解释 llm_reason。\n"
                    f"{payload}"
                ),
            },
        ]

        resolved_provider = provider or settings.page_judge_provider
        resolved_model = model or settings.page_judge_model
        if include_images:
            if not image_base_dir:
                raise ValueError("image_base_dir is required when include_images=True")
            image_paths = [str((Path(image_base_dir) / page["image_path"]).resolve()) for page in pages]
            content = self.llm_service.vision_chat(
                messages=messages,
                images=image_paths,
                provider=resolved_provider,
                model=resolved_model,
                temperature=0.1,
                max_tokens=4000,
            )
            return self.llm_service.parse_json_text(content)

        return self.llm_service.chat_json(
            messages=messages,
            provider=resolved_provider,
            model=resolved_model,
            temperature=0.1,
            max_tokens=4000,
        )

    def judge_pages_in_batches(
        self,
        pages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        batch_size: int = 8,
        include_images: bool = False,
        image_base_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        combined_pages: list[dict[str, Any]] = []
        for start in range(0, len(pages), batch_size):
            batch = pages[start : start + batch_size]
            result = self._judge_pages_with_fallback(
                pages=batch,
                provider=provider,
                model=model,
                include_images=include_images,
                image_base_dir=image_base_dir,
            )
            combined_pages.extend(result.get("pages", []))
        return {"pages": combined_pages}

    def judge_boundary_pages_in_batches(
        self,
        pages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        batch_size: int = 8,
        include_images: bool = False,
        image_base_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        boundary_pages = self.filter_boundary_pages(pages)
        return self.judge_pages_in_batches(
            pages=boundary_pages,
            provider=provider,
            model=model,
            batch_size=batch_size,
            include_images=include_images,
            image_base_dir=image_base_dir,
        )

    def _judge_pages_with_fallback(
        self,
        pages: list[dict[str, Any]],
        provider: str | None,
        model: str | None,
        include_images: bool,
        image_base_dir: str | Path | None,
    ) -> dict[str, Any]:
        try:
            return self.judge_pages(
                pages=pages,
                provider=provider,
                model=model,
                include_images=include_images,
                image_base_dir=image_base_dir,
            )
        except Exception:
            if len(pages) == 1:
                raise

            midpoint = max(1, len(pages) // 2)
            left = self._judge_pages_with_fallback(
                pages=pages[:midpoint],
                provider=provider,
                model=model,
                include_images=include_images,
                image_base_dir=image_base_dir,
            )
            right = self._judge_pages_with_fallback(
                pages=pages[midpoint:],
                provider=provider,
                model=model,
                include_images=include_images,
                image_base_dir=image_base_dir,
            )
            return {"pages": left.get("pages", []) + right.get("pages", [])}

    def summarize_parsed_pages_for_llm(self, pages: list[Any]) -> list[dict[str, Any]]:
        normalized = []
        for page in pages:
            if hasattr(page, "__dataclass_fields__"):
                normalized.append(asdict(page))
            else:
                normalized.append(dict(page))
        return self.build_candidate_pages_payload(normalized)
