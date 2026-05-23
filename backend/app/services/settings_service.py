from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import ENV_FILE, settings
from app.services.llm_service import LLMService, MODEL_SELECTION_BY_PURPOSE, OPENAI_COMPATIBLE_PROVIDERS


PROVIDER_NAMES = sorted(OPENAI_COMPATIBLE_PROVIDERS | {"anthropic"})
PROVIDER_CONFIG_FIELDS = {
    "openai_compatible": ("OPENAI_COMPATIBLE_API_KEY", "OPENAI_COMPATIBLE_BASE_URL"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
    "glm": ("GLM_API_KEY", "GLM_BASE_URL"),
    "kimi": ("KIMI_API_KEY", "KIMI_BASE_URL"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_BASE_URL"),
    "qwen": ("QWEN_API_KEY", "QWEN_BASE_URL"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"),
}


class SettingsService:
    def get_model_config(self) -> dict[str, Any]:
        return {
            "purposes": {
                purpose: {
                    "provider": str(getattr(settings, provider_field, "") or ""),
                    "model": str(getattr(settings, model_field, "") or ""),
                    "provider_env": provider_field.upper(),
                    "model_env": model_field.upper(),
                }
                for purpose, (provider_field, model_field) in MODEL_SELECTION_BY_PURPOSE.items()
            },
            "providers": {
                provider: {
                    "base_url": self._get_provider_base_url(provider),
                    "has_api_key": bool(self._get_provider_api_key(provider)),
                }
                for provider in PROVIDER_NAMES
            },
            "provider_options": PROVIDER_NAMES,
        }

    def update_model_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, str] = {}
        purposes = payload.get("purposes") or {}
        providers = payload.get("providers") or {}

        if not isinstance(purposes, dict) or not isinstance(providers, dict):
            raise ValueError("Invalid model configuration payload.")

        for purpose, value in purposes.items():
            if purpose not in MODEL_SELECTION_BY_PURPOSE:
                raise ValueError(f"Unsupported model purpose: {purpose}")
            if not isinstance(value, dict):
                raise ValueError(f"Invalid config for purpose: {purpose}")
            provider = str(value.get("provider") or "").strip().lower()
            model = str(value.get("model") or "").strip()
            if provider and provider not in PROVIDER_NAMES:
                raise ValueError(f"Unsupported provider '{provider}' for purpose '{purpose}'.")
            provider_field, model_field = MODEL_SELECTION_BY_PURPOSE[purpose]
            if provider:
                updates[provider_field.upper()] = provider
            if model:
                updates[model_field.upper()] = model

        for provider, value in providers.items():
            normalized_provider = str(provider).strip().lower()
            if normalized_provider not in PROVIDER_CONFIG_FIELDS:
                raise ValueError(f"Unsupported provider config: {provider}")
            if not isinstance(value, dict):
                raise ValueError(f"Invalid provider config: {provider}")
            api_key_field, base_url_field = PROVIDER_CONFIG_FIELDS[normalized_provider]
            base_url = str(value.get("base_url") or "").strip()
            api_key = str(value.get("api_key") or "").strip()
            if base_url:
                updates[base_url_field] = base_url
            if api_key:
                updates[api_key_field] = api_key

        if updates:
            self._write_env_updates(updates)
            self._apply_runtime_updates(updates)

        return self.get_model_config()

    def test_provider(self, provider: str, model: str, message: str | None = None) -> dict[str, Any]:
        provider = provider.strip().lower()
        model = model.strip()
        if provider not in PROVIDER_NAMES:
            raise ValueError(f"Unsupported provider: {provider}")
        if not model:
            raise ValueError("Model name is required.")

        content = LLMService().chat(
            provider=provider,
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise connection test assistant."},
                {"role": "user", "content": message or "Reply with OK."},
            ],
            temperature=0,
            max_tokens=32,
        )
        return {"ok": True, "provider": provider, "model": model, "response_preview": content[:500]}

    def _get_provider_base_url(self, provider: str) -> str:
        _, base_url_field = PROVIDER_CONFIG_FIELDS[provider]
        return str(getattr(settings, base_url_field.lower(), "") or "")

    def _get_provider_api_key(self, provider: str) -> str:
        api_key_field, _ = PROVIDER_CONFIG_FIELDS[provider]
        return str(getattr(settings, api_key_field.lower(), "") or "")

    def _write_env_updates(self, updates: dict[str, str]) -> None:
        env_path = Path(ENV_FILE)
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        seen: set[str] = set()
        output: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                output.append(line)

        for key, value in updates.items():
            if key not in seen:
                output.append(f"{key}={value}")

        env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")

    def _apply_runtime_updates(self, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            setattr(settings, key.lower(), value)
