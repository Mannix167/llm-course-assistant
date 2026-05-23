from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database.db import init_db
from app.routers.courses import router as courses_router
from app.routers.interactions import router as interactions_router
from app.routers.reports import router as reports_router
from app.routers.settings import router as settings_router
from app.routers.upload import router as upload_router


app = FastAPI(title="Course Learning Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(upload_router)
app.include_router(courses_router)
app.include_router(reports_router)
app.include_router(interactions_router)
app.include_router(settings_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
