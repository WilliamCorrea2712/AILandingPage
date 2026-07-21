"""
Celery application configuration.

Requirements: 10.1, 10.2, 10.6
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "ai_landing_page_generator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.generation_worker",
        "app.workers.render_worker",
        "app.workers.training_worker",
        "app.workers.image_worker",
        "app.workers.learning_worker",
    ],
)

celery_app.conf.update(
    # Task routing — separate queues per job type
    task_routes={
        "app.workers.generation_worker.*": {"queue": "generation_jobs"},
        "app.workers.render_worker.*": {"queue": "render_jobs"},
        "app.workers.training_worker.*": {"queue": "training_jobs"},
        "app.workers.image_worker.*": {"queue": "image_jobs"},
        "app.workers.learning_worker.*": {"queue": "training_jobs"},
    },
    # Retry policy: max 2 retries, 30s interval
    task_max_retries=2,
    task_default_retry_delay=30,
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Result expiry
    result_expires=3600,
    # Worker settings
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # ── Periodic tasks (Celery Beat) ────────────────────────────────────────
    beat_schedule={
        "weekly-pattern-learning": {
            "task": "app.workers.learning_worker.run_pattern_learning",
            "schedule": 604800.0,  # every 7 days in seconds
            "args": (7,),          # analyze last 7 days
            "options": {"queue": "training_jobs"},
        },
        "daily-pattern-learning": {
            "task": "app.workers.learning_worker.run_pattern_learning",
            "schedule": 86400.0,   # every 24h — lighter run
            "args": (1,),          # analyze last 1 day
            "options": {"queue": "training_jobs"},
        },
    },
)
