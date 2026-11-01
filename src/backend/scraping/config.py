"""Configuration for the scraping layer.

The layer reads one optional ``watch`` object from the existing ``config.search``
JSON blob, so it needs no schema change and no new config table. Anything the
user does not set falls back to the defaults below.

Example (stored inside config.search)::

    "watch": {
      "max_companies_per_run": 300,
      "extra_company_urls": [
        {"company": "Acme", "url": "https://acme.com/careers", "kind": "cards",
         "path_pattern": "/careers/[^/?#]+"}
      ],
      "feeds": {"hiring_posts": {"enabled": true, "feed_urls": ["https://..."]}}
    }
"""

from __future__ import annotations

import copy
import os

DEFAULT_WATCH = {
    "enabled": True,
    "max_companies_per_run": 300,
    "source_concurrency": 12,
    "company_timeout_seconds": 90,
    "fetch_deadline_seconds": 900,
    "hydrate_concurrency": 8,
    "hydration_min_chars": 400,
    "hydrate_max_jobs": 400,
    "hydrate_deadline_seconds": 240,
    "stale_hours": 20,
    # Extra non-ATS careers pages. kind: auto | cards | sitemap | next_data
    "extra_company_urls": [],
    "feeds": {
        "yc": {"enabled": True, "locations": ["India", "Remote"]},
        "linkedin": {
            "enabled": True,
            "queries": [
                "ai engineer",
                "backend engineer",
                "fullstack engineer",
                "solutions engineer",
                "developer advocate",
            ],
            "locations": [
                {"location": "India", "geo_id": "102713980", "distance": 0},
                {"location": "Bengaluru, Karnataka, India", "geo_id": "105214831", "distance": 0},
            ],
            "experience_levels": "1,2,3",
            "recency_seconds": 86400,
            "page_size": 10,
            "max_results_per_query": 50,
            "request_delay_seconds": 2.0,
        },
        "hiring_posts": {
            "enabled": False,
            "feed_urls": [],
            "max_entries_per_feed": 100,
        },
        "remoteok": {"enabled": True},
        "remotive": {"enabled": True},
        "arbeitnow": {"enabled": True},
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    # Deep copy so callers can mutate the result without touching the defaults.
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def watch_config(search_config: dict | None = None) -> dict:
    """Merge defaults, stored config, and the few useful env overrides."""
    stored = (search_config or {}).get("watch") or {}
    cfg = _deep_merge(DEFAULT_WATCH, stored)

    if "WATCH_ENABLED" in os.environ:
        cfg["enabled"] = _env_bool("WATCH_ENABLED", cfg["enabled"])
    if os.environ.get("WATCH_MAX_COMPANIES"):
        try:
            cfg["max_companies_per_run"] = int(os.environ["WATCH_MAX_COMPANIES"])
        except ValueError:
            pass
    if os.environ.get("WATCH_SOURCE_CONCURRENCY"):
        try:
            cfg["source_concurrency"] = int(os.environ["WATCH_SOURCE_CONCURRENCY"])
        except ValueError:
            pass

    feeds = cfg["feeds"]
    raw_urls = os.environ.get("HIRING_POST_FEED_URLS", "")
    if raw_urls.strip():
        parsed = [
            chunk.strip()
            for chunk in raw_urls.replace(";", "\n").replace(",", "\n").splitlines()
            if chunk.strip()
        ]
        feeds["hiring_posts"]["feed_urls"] = list(
            dict.fromkeys([*(feeds["hiring_posts"].get("feed_urls") or []), *parsed])
        )
        feeds["hiring_posts"]["enabled"] = True

    return cfg
