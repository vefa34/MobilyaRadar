"""Background job dispatch: Celery (production) or an in-process thread (development/tests)."""
from __future__ import annotations

import logging
import threading

from celery import Celery

from app.config import get_settings

log = logging.getLogger("worker")
settings = get_settings()

celery_app = Celery("globalbuyer", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, task_serializer="json",
                       beat_schedule={"purge-expired": {"task": "app.worker.purge_expired_task", "schedule": 6 * 3600.0}})


@celery_app.task(name="app.worker.run_research_job")
def run_research_job(job_id: str) -> str:
    import uuid

    from app.services.pipeline import run_job
    run_job(uuid.UUID(job_id))
    return job_id


@celery_app.task(name="app.worker.purge_expired_task")
def purge_expired_task() -> dict:
    from app.db import session_scope
    from app.services.retention import purge_expired
    with session_scope() as db:
        return purge_expired(db)


def dispatch_job(job_id) -> str:
    backend = get_settings().task_backend
    if backend == "celery":
        run_research_job.delay(str(job_id))
        return "celery"
    if backend == "inline":  # tests: run synchronously in the request
        from app.services.pipeline import run_job
        run_job(job_id)
        return "inline"

    def _run():
        from app.services.pipeline import run_job
        try:
            run_job(job_id)
        except Exception:  # noqa: BLE001
            log.exception("job %s crashed", job_id)

    threading.Thread(target=_run, name=f"job-{job_id}", daemon=True).start()
    return "thread"
