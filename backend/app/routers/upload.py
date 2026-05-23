from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.services.course_service import CourseService


router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
def upload_pdf(
    file: UploadFile = File(...),
    folder_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict[str, int | str | None]:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file name.")
    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = Path(temp_file.name)

    try:
        course = CourseService().create_uploaded_course(
            db=db,
            source_file_path=temp_path,
            original_file_name=file.filename,
            folder_id=folder_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    return {"course_id": course.id, "folder_id": course.folder_id, "status": course.status}
