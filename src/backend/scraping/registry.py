"""Turn the existing ATS registry into scrape targets.

The legacy ``ats`` source already stores companies as ``(platform, slug)``. This
module maps those pairs back to a careers URL and adds any extra careers pages the
user configured by hand, so the new layer reuses the same discovery work instead
of maintaining a second company list.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .models import clean_url

try:
    from .. import db
except ImportError:  # running as a top-level module (scripts, tests)
    import db


PLATFORM_URLS = {
    "greenhouse": "https://job-boards.greenhouse.io/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
    "workable": "https://apply.workable.com/{slug}/",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{slug}",
    "recruitee": "https://{slug}.recruitee.com/",
}


def _company_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    first = host.split(".")[0] if host else "Unknown"
    return first.replace("-", " ").replace("_", " ").title()


def build_rows(cfg: dict, limit: int | None = None) -> list:
    """Return ``[{company, careers_url, platform, slug, kind, path_pattern}]``."""
    cap = int(limit or cfg.get("max_companies_per_run", 300))
    rows = []
    skipped = 0

    for company in db.list_watch_companies(limit=cap):
        platform = (company.get("platform") or "").lower()
        slug = (company.get("slug") or "").strip()
        template = PLATFORM_URLS.get(platform)
        if not template or not slug:
            skipped += 1
            continue
        rows.append(
            {
                "company": (company.get("company_name") or slug).strip(),
                "careers_url": template.format(slug=slug),
                "platform": platform,
                "slug": slug,
                "kind": "auto",
                "path_pattern": "",
            }
        )

    for entry in cfg.get("extra_company_urls") or []:
        if isinstance(entry, str):
            entry = {"url": entry}
        if not isinstance(entry, dict):
            continue
        url = (entry.get("url") or "").strip()
        if not url:
            continue
        rows.append(
            {
                "company": (entry.get("company") or _company_from_url(url)).strip(),
                "careers_url": url,
                "platform": "html",
                "slug": "",
                "kind": (entry.get("kind") or "auto").lower(),
                "path_pattern": entry.get("path_pattern") or "",
            }
        )

    seen = set()
    unique = []
    for row in rows:
        key = clean_url(row["careers_url"])
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)

    if skipped:
        print(f"[watch] skipped {skipped} registry entries with no supported platform URL")
    return unique[:cap]
