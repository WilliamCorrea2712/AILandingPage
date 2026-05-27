"""Celery worker — render and publish task. Requirements: 10.2, 8.1"""
from __future__ import annotations
import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.render_worker.run_render_job",
    bind=True, max_retries=2, default_retry_delay=30, queue="render_jobs",
)
def run_render_job(self, job_id: str, project_id: str, generation_id: str, user_id: str | None = None):
    from app.database import get_db_session
    from app.models.ai_generation import AIGeneration
    from app.models.project import Project
    from app.services.renderer import RenderResult
    from app.services.publisher import Publisher
    from app.services.analytics_service import record_event
    import uuid

    with get_db_session() as db:
        try:
            gen = db.get(AIGeneration, uuid.UUID(generation_id))
            project = db.get(Project, uuid.UUID(project_id))
            if not gen or not project:
                raise ValueError("Generation or project not found.")

            render_result = RenderResult(html=gen.html_output or "", css=gen.css_output or "")
            publisher = Publisher()
            pub_result = publisher.publish(project, render_result)

            from app.models.publication import Publication
            pub = Publication(
                project_id=project.id,
                generation_id=gen.id,
                subdomain=pub_result.subdomain,
                ssl_status=pub_result.ssl_status,
                cdn_status=pub_result.cdn_status,
                published_url=pub_result.url,
                published_at=pub_result.published_at,
            )
            db.add(pub)
            project.status = "published"
            db.commit()
            record_event(db, "publication_done", user_id=user_id, project_id=project_id, job_id=job_id)
            return {"job_id": job_id, "url": pub_result.url}
        except Exception as exc:
            logger.error("Render job %s failed: %s", job_id, exc, exc_info=True)
            record_event(db, "error_occurred", user_id=user_id, project_id=project_id, job_id=job_id,
                         metadata={"error": str(exc)})
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                raise
