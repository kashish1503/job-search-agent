"""Normalized job and source-health models for the scraping layer.

These mirror the two ideas that make the JobWatch crawler reliable:

* a ``Job`` has a stable key derived from the source and the portal's own job id,
  so re-scraping never creates duplicates;
* a ``SourceResult`` records *how* a portal responded, so "no openings" is never
  confused with "we failed to read the page".
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "gh_jid", "gh_src", "fbclid", "gclid")


def clean_url(value: str) -> str:
    """Drop tracking parameters and normalise host/case. Safe on empty input."""
    if not value:
        return ""
    parts = urlsplit(value.strip())
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query)
            if not k.lower().startswith(TRACKING_PREFIXES)
        ]
    )
    return urlunsplit(
        (parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), query, "")
    )


def digest(*parts: str, size: int = 24) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8", "ignore")).hexdigest()[:size]


def detect_work_type(text: str, remote: bool = False) -> str:
    lowered = (text or "").lower()
    if "hybrid" in lowered:
        return "hybrid"
    if remote or "remote" in lowered or "worldwide" in lowered or "anywhere" in lowered:
        return "remote"
    if any(word in lowered for word in ("onsite", "on-site", "in-office", "in office")):
        return "onsite"
    return "unspecified"


def _date_only(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else text[:30]


@dataclass(slots=True)
class Job:
    source: str
    source_job_id: str
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""
    posted_at: str | None = None
    remote: bool = False
    salary_text: str = ""
    raw: dict = field(default_factory=dict)
    # Optional pre-computed row id, used to stay compatible with rows written by
    # the legacy ``sources_ats`` fetchers so the two layers cannot duplicate jobs.
    row_id: str = ""

    def __post_init__(self) -> None:
        self.url = clean_url(self.url)
        self.source_job_id = str(self.source_job_id or self.url)
        if not self.title:
            self.title = "Untitled role"

    @property
    def key(self) -> str:
        return digest(self.source, self.source_job_id)

    @property
    def content_hash(self) -> str:
        return digest(
            self.company,
            self.title,
            self.location,
            (self.description or "")[:2000],
            self.salary_text,
        )

    def to_row(self) -> dict:
        """Convert to the dict shape the existing ``jobs`` table expects."""
        return {
            "id": self.row_id or self.key,
            "source": self.source,
            "title": self.title[:300],
            "company": (self.company or "")[:160],
            "url": self.url,
            "description": (self.description or "")[:20000],
            "work_type": detect_work_type(
                f"{self.title} {self.location}", self.remote
            ),
            "location": (self.location or "")[:200],
            "posted_at": _date_only(self.posted_at),
            "metadata": {
                "remote": bool(self.remote),
                "salary_text": self.salary_text,
                "content_hash": self.content_hash,
                **(self.raw or {}),
            },
        }


@dataclass(slots=True)
class SourceResult:
    company: str
    careers_url: str
    status: str
    parser: str
    jobs: list[Job] = field(default_factory=list)
    error: str = ""
    duration_ms: int = 0
    expected_jobs: int | None = None
    previous_jobs: int | None = None
    coverage_ratio: float | None = None
    completeness: str = "unverified"

    def __post_init__(self) -> None:
        found = len(self.jobs)
        if self.completeness not in ("bounded", "bounded_partial"):
            if self.expected_jobs is not None:
                self.coverage_ratio = (
                    1.0
                    if self.expected_jobs == 0 and found == 0
                    else (found / self.expected_jobs if self.expected_jobs else None)
                )
                self.completeness = (
                    "verified" if found == self.expected_jobs else "partial"
                )
            elif self.parser not in ("none", "generic_html") and self.status not in (
                "failed",
                "blocked",
            ):
                self.completeness = "structured"
        if self.status == "failed" and self.completeness == "structured":
            self.completeness = "unverified"

    @property
    def needs_attention(self) -> bool:
        return self.status in ("failed", "blocked") or self.completeness in (
            "partial",
            "suspicious_drop",
        )

    def to_health_row(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "company": self.company,
            "careers_url": self.careers_url,
            "status": self.status,
            "parser": self.parser,
            "jobs_found": len(self.jobs),
            "duration_ms": self.duration_ms,
            "error": (self.error or "")[:2000],
            "expected_jobs": self.expected_jobs,
            "coverage_ratio": self.coverage_ratio,
            "completeness": self.completeness,
        }
