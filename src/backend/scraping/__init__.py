"""JobWatch-style scraping layer, ported for job-search-agent.

Three tiers per careers URL (special adapter -> structured data -> generic links),
per-source status/completeness, discovery feeds (YC, LinkedIn, public job APIs).

Public entry points::

    from . import scraping

    rows = scraping.scrape_jobs()        # list[dict] ready for db.save_job
    health = scraping.last_health()      # latest run's per-source verdicts
    stats = scraping.health_summary()    # counts by status/completeness
"""

from __future__ import annotations

from .config import DEFAULT_WATCH, watch_config
from .fetch import health_summary, last_health, run, scrape_jobs
from .models import Job, SourceResult, clean_url, detect_work_type

__all__ = [
    "DEFAULT_WATCH",
    "Job",
    "SourceResult",
    "clean_url",
    "detect_work_type",
    "health_summary",
    "last_health",
    "run",
    "scrape_jobs",
    "watch_config",
]
