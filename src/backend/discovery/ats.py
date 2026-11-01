from __future__ import annotations

import os

from .base import DiscoveryPlugin
from .url_utils import normalize_url

try:
    from .. import sources_ats
except ImportError:
    import sources_ats


class ATSDiscovery(DiscoveryPlugin):
    def __init__(self):
        super().__init__(name="ats", enabled=True)

    def discover(self, campaign: dict, limit: int = 50) -> list[dict]:
        jobs = []
        max_companies = int(os.environ.get("ATS_MAX_COMPANIES_PER_CAMPAIGN", "120"))
        for job in sources_ats.scrape_ats(
            refresh_registry=False,
            max_companies=max_companies,
        )[:limit]:
            normalized = normalize_url(job.get("url", ""))
            jobs.append(
                {
                    "url": job.get("url", ""),
                    "original_url": normalized["original_url"],
                    "canonical_url": normalized["canonical_url"],
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "snippet": job.get("description", "")[:500],
                    "source": self.name,
                    "query": "ats_direct",
                    "confidence": 0.95,
                    "metadata": {"job": job},
                }
            )
        return jobs
