"""
Celery application configuration.
"""

import os
from celery import Celery

# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "biolinker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["biolinker.tasks.article_tasks"],
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Rate limiting
    task_default_rate_limit="10/m",  # 10 tasks per minute by default
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
)

# Optional: Configure task routes
celery_app.conf.task_routes = {
    "biolinker.tasks.article_tasks.process_articles_task": {"queue": "processing"},
    "biolinker.tasks.article_tasks.fetch_pubmed_articles_task": {"queue": "fetching"},
}

