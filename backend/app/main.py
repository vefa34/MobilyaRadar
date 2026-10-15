import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.api import auth, companies, dashboard, exports, research, sources
from app.config import get_settings
from app.db import SessionLocal, get_engine
from app.models import JobStatus, Organization, SearchJob, User
from app.security import hash_password
from app.services.source_catalog import sync_seed_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan,
              description="Global Furniture Buyer Intelligence — discovery, verification and qualification of furniture buyers.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition", "X-Export-Rows", "X-Export-Withheld-Fields", "X-Export-Excluded-Companies"])
for r in (auth.router, research.router, companies.router, sources.router, exports.router, dashboard.router):
    app.include_router(r)


def startup() -> None:
    if settings.environment == "production" and settings.secret_key.startswith("change-me"):
        raise RuntimeError("SECRET_KEY must be set in production")
    get_engine()
    db = SessionLocal()
    try:
        sync_seed_sources(db)
        # Jobs interrupted by a restart are marked failed (thread backend) so users can restart them.
        if settings.task_backend == "thread":
            for j in db.scalars(select(SearchJob).where(SearchJob.status.in_(["planning", "discovering", "enriching", "scoring", "queued"]))):
                j.status, j.error = JobStatus.FAILED.value, "interrupted by server restart — use Start to resume"
        if settings.bootstrap_admin_email and settings.bootstrap_admin_password and not db.scalar(
                select(User).where(User.email == settings.bootstrap_admin_email.lower())):
            org = Organization(name="Default organisation")
            db.add(org)
            db.flush()
            db.add(User(org_id=org.id, email=settings.bootstrap_admin_email.lower(), password_hash=hash_password(settings.bootstrap_admin_password),
                        role="owner", full_name="Admin"))
        db.commit()
    finally:
        db.close()


@app.get("/api/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("select 1"))
        return {"status": "ok", "demo_mode": settings.demo_mode, "task_backend": settings.task_backend, "llm_provider": settings.llm_provider}
    finally:
        db.close()
