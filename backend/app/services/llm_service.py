from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


OPENAI_COMPATIBLE_PROVIDERS = {"openai_compatible", "deepseek", "glm", "kimi", "gemini", "qwen"}
MODEL_SELECTION_BY_PURPOSE = {
    "quick_text": ("quick_text_provider", "quick_text_model"),
    "standard_text": ("standard_text_provider", "standard_text_model"),
    "visual_text": ("visual_text_provider", "visual_text_model"),
    "visual_vision": ("visual_vision_provider", "visual_vision_model"),
    "advanced": ("advanced_provider", "advanced_model"),
    "review": ("review_provider", "review_model"),
    "chat": ("chat_provider", "chat_model"),
    "advanced_chat": ("advanced_chat_provider", "advanced_chat_model"),
    "page_judge": ("page_judge_provider", "page_judge_model"),
}


@dataclass(slots=True)
class ProviderConfig:
    provider: str
    base_url: str
    api_key: str
    default_model: str | None
    api_style: str


class LLMService:
    def __init__(self, timeout_seconds: float | None = None) -> None:
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds

    def chat(
        self,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        config = self._resolve_provider(provider=provider, model=model)
        if config.api_style == "anthropic":
            payload = self._build_anthropic_payload(messages, config.default_model or model, temperature, max_tokens)
            response = self._post_json(config, "/messages", payload)
            return self._extract_anthropic_text(response)

        payload = self._build_openai_payload(messages, config.default_model or model, temperature, max_tokens)
        response = self._post_json(config, "/chat/completions", payload)
        return self._extract_openai_text(response)

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        json_messages = list(messages) + [
            {
                "role": "system",
                "content": "Return valid JSON only. You may wrap it in a ```json code block, but do not add any explanation outside the JSON.",
            }
        ]
        content = self.chat(
            messages=json_messages,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self.parse_json_text(content)

    def vision_chat(
        self,
        messages: list[dict[str, Any]],
        images: list[str],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        config = self._resolve_provider(provider=provider, model=model)
        if config.api_style == "anthropic":
            payload = self._build_anthropic_vision_payload(messages, images, config.default_model or model, temperature, max_tokens)
            response = self._post_json(config, "/messages", payload)
            return self._extract_anthropic_text(response)

        payload = self._build_openai_vision_payload(messages, images, config.default_model or model, temperature, max_tokens)
        response = self._post_json(config, "/chat/completions", payload)
        return self._extract_openai_text(response)

    def chat_for_purpose(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        provider, model = self.resolve_model_selection(purpose)
        return self.chat(
            messages=messages,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_json_for_purpose(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        provider, model = self.resolve_model_selection(purpose)
        return self.chat_json(
            messages=messages,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def vision_chat_for_purpose(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        images: list[str],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        provider, model = self.resolve_model_selection(purpose)
        return self.vision_chat(
            messages=messages,
            images=images,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def resolve_model_selection(self, purpose: str) -> tuple[str, str]:
        normalized = purpose.strip().lower()
        if normalized not in MODEL_SELECTION_BY_PURPOSE:
            raise ValueError(f"Unsupported model selection purpose: {purpose}")
        provider_field, model_field = MODEL_SELECTION_BY_PURPOSE[normalized]
        provider = str(getattr(settings, provider_field, "") or "").strip()
        model = str(getattr(settings, model_field, "") or "").strip()
        if not provider or not model:
            raise ValueError(
                f"Model selection for purpose '{purpose}' is incomplete. Check {provider_field} and {model_field} in .env."
            )
        return provider, model

    def check_provider_ready(self, provider: str | None, model: str | None = None) -> dict[str, Any]:
        config = self._resolve_provider(provider=provider, model=model)
        return {
            "provider": config.provider,
            "base_url": config.base_url,
            "api_style": config.api_style,
            "has_api_key": bool(config.api_key),
            "model": model,
        }

    def _resolve_provider(self, provider: str | None, model: str | None) -> ProviderConfig:
        resolved_provider = (provider or "openai_compatible").lower()
        field_prefix = resolved_provider

        if resolved_provider in OPENAI_COMPATIBLE_PROVIDERS:
            base_url = self._get_setting_value(f"{field_prefix}_base_url") or settings.openai_compatible_base_url
            api_key = self._get_setting_value(f"{field_prefix}_api_key") or settings.openai_compatible_api_key
            default_model = model
            return ProviderConfig(
                provider=resolved_provider,
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                default_model=default_model,
                api_style="openai",
            )

        if resolved_provider == "anthropic":
            return ProviderConfig(
                provider=resolved_provider,
                base_url=settings.anthropic_base_url.rstrip("/"),
                api_key=settings.anthropic_api_key,
                default_model=model,
                api_style="anthropic",
            )

        raise ValueError(f"Unsupported provider: {resolved_provider}")

    def _get_setting_value(self, name: str) -> str:
        return str(getattr(settings, name, "") or "")

    def _build_openai_payload(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        if not model:
            raise ValueError("A model name is required for OpenAI-compatible requests.")
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    def _build_openai_vision_payload(
        self,
        messages: list[dict[str, Any]],
        images: list[str],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        if not model:
            raise ValueError("A model name is required for OpenAI-compatible vision requests.")
        prepared_messages = [dict(message) for message in messages]
        prepared_messages.append(
            {
                "role": "user",
                "content": self._build_openai_vision_content(images),
            }
        )
        return self._build_openai_payload(prepared_messages, model, temperature, max_tokens)

    def _build_openai_vision_content(self, images: list[str]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for image_path in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._encode_image_as_data_url(image_path)},
                }
            )
        return content

    def _build_anthropic_payload(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        if not model:
            raise ValueError("A model name is required for Anthropic requests.")
        system_messages = [message["content"] for message in messages if message.get("role") == "system"]
        chat_messages = [message for message in messages if message.get("role") != "system"]
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._normalize_anthropic_messages(chat_messages),
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system_messages:
            payload["system"] = "\n\n".join(str(content) for content in system_messages)
        return payload

    def _build_anthropic_vision_payload(
        self,
        messages: list[dict[str, Any]],
        images: list[str],
        model: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload = self._build_anthropic_payload(messages, model, temperature, max_tokens)
        anthropic_messages = payload["messages"]
        anthropic_messages.append(
            {
                "role": "user",
                "content": self._build_anthropic_vision_content(images),
            }
        )
        return payload

    def _normalize_anthropic_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, list):
                normalized.append({"role": message["role"], "content": content})
            else:
                normalized.append({"role": message["role"], "content": [{"type": "text", "text": str(content)}]})
        return normalized

    def _build_anthropic_vision_content(self, images: list[str]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for image_path in images:
            media_type, encoded = self._encode_image(image_path)
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": encoded,
                    },
                }
            )
        return content

    def _post_json(self, config: ProviderConfig, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not config.api_key:
            raise ValueError(f"Missing API key for provider '{config.provider}'. Fill it in .env first.")

        headers = {"Content-Type": "application/json"}
        if config.api_style == "anthropic":
            headers["x-api-key"] = config.api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {config.api_key}"

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{config.base_url}{endpoint}", headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body_preview = response.text[:2000]
                raise ValueError(
                    f"LLM request failed for provider '{config.provider}' with status {response.status_code}: {body_preview}"
                ) from exc
            return response.json()

    def _extract_openai_text(self, response: dict[str, Any]) -> str:
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Unexpected OpenAI-compatible response: {response}") from exc

        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            return "\n".join(part for part in parts if part)
        return str(content)

    def _extract_anthropic_text(self, response: dict[str, Any]) -> str:
        try:
            blocks = response["content"]
        except KeyError as exc:
            raise ValueError(f"Unexpected Anthropic response: {response}") from exc
        parts = [block.get("text", "") for block in blocks if block.get("type") == "text"]
        return "\n".join(part for part in parts if part)

    def parse_json_text(self, content: str) -> dict[str, Any]:
        text = content.strip()
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.DOTALL | re.IGNORECASE)
        if fenced_match:
            text = fenced_match.group(1).strip()
        else:
            json_start = min([idx for idx in (text.find("{"), text.find("[")) if idx != -1], default=-1)
            if json_start > 0:
                text = text[json_start:].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = self._remove_illegal_control_chars(text)
            return json.loads(cleaned)

    def _remove_illegal_control_chars(self, text: str) -> str:
        return "".join(ch for ch in text if ch >= " " or ch in "\n\r\t")

    def _encode_image_as_data_url(self, image_path: str) -> str:
        media_type, encoded = self._encode_image(image_path)
        return f"data:{media_type};base64,{encoded}"

    def _encode_image(self, image_path: str) -> tuple[str, str]:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        media_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return media_type, encoded
