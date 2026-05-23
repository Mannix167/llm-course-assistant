from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.settings_service import SettingsService


router = APIRouter(prefix="/api/settings", tags=["settings"])


class ModelConfigRequest(BaseModel):
    purposes: dict[str, dict[str, Any]] = {}
    providers: dict[str, dict[str, Any]] = {}


class TestProviderRequest(BaseModel):
    provider: str
    model: str
    message: str | None = None


@router.get("/model-config")
def get_model_config() -> dict[str, Any]:
    return SettingsService().get_model_config()


@router.put("/model-config")
def update_model_config(request: ModelConfigRequest) -> dict[str, Any]:
    try:
        return SettingsService().update_model_config(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/model-config/test")
def test_model_config(request: TestProviderRequest) -> dict[str, Any]:
    try:
        return SettingsService().test_provider(
            provider=request.provider,
            model=request.model,
            message=request.message,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
