from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.services.interaction_service import InteractionService


router = APIRouter(prefix="/api", tags=["interactions"])


class ChatRequest(BaseModel):
    question: str
    mode: str = "normal"
    scope: str = "report"
    chapter_id: int | None = None
    page_number: int | None = None
    image_name: str | None = None


class FeedbackRequest(BaseModel):
    feedback_text: str
    target_content: str
    scope: str = "report"
    chapter_id: int | None = None
    page_number: int | None = None
    image_name: str | None = None


@router.get("/reports/{report_id}/chat")
def list_chat_messages(report_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    try:
        return InteractionService().list_chat_messages(db, report_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/reports/{report_id}/chat")
def ask_report_question(report_id: int, request: ChatRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not request.question.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question is required.")
    try:
        return InteractionService().ask_question(
            db=db,
            report_id=report_id,
            question=request.question,
            mode=request.mode,
            scope=request.scope,
            chapter_id=request.chapter_id,
            page_number=request.page_number,
            image_name=request.image_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Chat request failed: {exc}") from exc


@router.get("/reports/{report_id}/feedback")
def list_report_feedback(report_id: int, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    try:
        return InteractionService().list_feedback(db, report_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/reports/{report_id}/feedback")
def rewrite_report_feedback(report_id: int, request: FeedbackRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not request.feedback_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Feedback text is required.")
    if not request.target_content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target content is required.")
    try:
        return InteractionService().rewrite_feedback(
            db=db,
            report_id=report_id,
            feedback_text=request.feedback_text,
            target_content=request.target_content,
            scope=request.scope,
            chapter_id=request.chapter_id,
            page_number=request.page_number,
            image_name=request.image_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Feedback rewrite failed: {exc}") from exc


@router.post("/feedback/{feedback_id}/apply")
def apply_feedback_rewrite(feedback_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return InteractionService().apply_feedback(db, feedback_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
