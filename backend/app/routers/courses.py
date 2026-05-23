from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import Chapter, Course, Page
from app.services.course_service import CourseService


router = APIRouter(prefix="/api", tags=["courses"])


class FolderRequest(BaseModel):
    name: str
    description: str | None = None


class MoveCourseRequest(BaseModel):
    folder_id: int | None = None


@router.get("/folders")
def list_folders(db: Session = Depends(get_db)) -> list[dict]:
    return CourseService().list_folders(db)


@router.post("/folders")
def create_folder(request: FolderRequest, db: Session = Depends(get_db)) -> dict:
    try:
        folder = CourseService().create_folder(db, name=request.name, description=request.description)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "folder_id": folder.id,
        "name": folder.name,
        "description": folder.description,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
        "updated_at": folder.updated_at.isoformat() if folder.updated_at else None,
    }


@router.put("/folders/{folder_id}")
def update_folder(folder_id: int, request: FolderRequest, db: Session = Depends(get_db)) -> dict:
    try:
        folder = CourseService().update_folder(db, folder_id=folder_id, name=request.name, description=request.description)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "folder_id": folder.id,
        "name": folder.name,
        "description": folder.description,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
        "updated_at": folder.updated_at.isoformat() if folder.updated_at else None,
    }


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    deleted = CourseService().delete_folder(db, folder_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Folder {folder_id} not found.")
    return {"deleted": True}


@router.get("/courses")
def list_courses(db: Session = Depends(get_db)) -> list[dict]:
    return CourseService().list_courses(db)


@router.get("/courses/{course_id}")
def get_course_detail(course_id: int, db: Session = Depends(get_db)) -> dict:
    course = CourseService().get_course_detail(db, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course {course_id} not found.")
    return course


@router.put("/courses/{course_id}/folder")
def move_course_to_folder(course_id: int, request: MoveCourseRequest, db: Session = Depends(get_db)) -> dict:
    try:
        course = CourseService().move_course_to_folder(db, course_id=course_id, folder_id=request.folder_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "course_id": course.id,
        "folder_id": course.folder_id,
        "folder_name": course.folder.name if course.folder else None,
    }


@router.post("/courses/{course_id}/parse")
def parse_course(course_id: int, db: Session = Depends(get_db)) -> dict[str, int | str | bool]:
    try:
        course = CourseService().parse_existing_course(db=db, course_id=course_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "course_id": course.id,
        "status": course.status,
        "page_count": course.page_count,
        "scanned_like": course.scanned_like,
    }


@router.get("/courses/{course_id}/pages")
def get_course_pages(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course {course_id} not found.")

    pages = (
        db.query(Page)
        .filter(Page.course_id == course_id)
        .order_by(Page.page_number.asc())
        .all()
    )
    return [
        {
            "page_number": page.page_number,
            "text": page.text,
            "analysis_text": page.analysis_text,
            "image_path": _to_public_image_path(course, page.image_path),
            "text_length": page.text_length,
            "analysis_text_length": page.analysis_text_length,
            "image_count": page.image_count,
            "need_ocr": page.need_ocr,
            "page_type": page.page_type,
            "candidate_for_visual": page.candidate_for_visual,
            "exclude_text_from_llm": page.exclude_text_from_llm,
            "llm_review_needed": page.llm_review_needed,
            "candidate_reasons": page.candidate_reasons,
            "layout_flags": page.layout_flags,
            "features": page.features,
        }
        for page in pages
    ]


@router.get("/courses/{course_id}/chapters")
def get_course_chapters(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course {course_id} not found.")

    chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course_id)
        .order_by(Chapter.order_index.asc(), Chapter.start_page.asc(), Chapter.id.asc())
        .all()
    )
    return [
        {
            "chapter_id": chapter.id,
            "title": chapter.title,
            "start_page": chapter.start_page,
            "end_page": chapter.end_page,
            "key_points": chapter.key_points or [],
            "order_index": chapter.order_index,
        }
        for chapter in chapters
    ]


@router.get("/courses/{course_id}/images/{image_name}")
def get_course_image(course_id: int, image_name: str, db: Session = Depends(get_db)) -> FileResponse:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course {course_id} not found.")

    safe_name = Path(image_name).name
    if safe_name != image_name or not safe_name.lower().endswith(".png"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image name.")

    course_root = Path(course.pages_json_path).resolve().parent if course.pages_json_path else Path(course.file_path).resolve().parent
    image_path = (course_root / "images" / safe_name).resolve()
    image_root = (course_root / "images").resolve()
    if image_root not in image_path.parents or not image_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Image {safe_name} not found.")

    return FileResponse(image_path)


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    deleted = CourseService().delete_course(db, course_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course {course_id} not found.")
    return {"deleted": True}


def _to_public_image_path(course: Course, relative_image_path: str) -> str:
    course_root = Path(course.pages_json_path).resolve().parent if course.pages_json_path else Path(course.file_path).resolve().parent
    return str((course_root / relative_image_path).resolve())
