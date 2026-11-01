"""Discovery plugin backed by the JobWatch-style scraping layer.

Unlike :class:`discovery.ats.ATSDiscovery`, this walks *all* supported portals
(ATS APIs, embedded JSON, sitemaps, HTML cards, generic links) plus the public
feeds (YC, LinkedIn guest search, RemoteOK, Remotive, Arbeitnow), each with its
own status and completeness verdict.

The campaign-facing shape matches the other plugins.
"""

from __future__ import annotations

import os

from .base import DiscoveryPlugin
from .url_utils import normalize_url

try:
    from .. import scraping
except ImportError:  # running as a top-level module
    import scraping


class WatchDiscovery(DiscoveryPlugin):
    def __init__(self):
        super().__init__(name="watch", enabled=True)

    def discover(self, campaign: dict, limit: int = 50) -> list[dict]:
        max_companies = int(
            os.environ.get(
                "WATCH_MAX_COMPANIES_PER_CAMPAIGN",
                os.environ.get("WATCH_MAX_COMPANIES", "120"),
            )
        )
        # Campaigns want breadth quickly; skip feeds unless explicitly asked.
        include_feeds = os.environ.get("WATCH_CAMPAIGN_FEEDS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        rows = []
        for job in scraping.scrape_jobs(limit=max_companies, include_feeds=include_feeds):
            normalized = normalize_url(job.get("url", ""))
            rows.append(
                {
                    "url": job.get("url", ""),
                    "original_url": normalized["original_url"],
                    "canonical_url": normalized["canonical_url"],
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "snippet": (job.get("description") or "")[:500],
                    "source": self.name,
                    "query": "watch_direct",
                    "confidence": 0.9,
                    "metadata": {"job": job, "platform": job.get("source", "")},
                }
            )
            if len(rows) >= limit:
                break
        return rows
