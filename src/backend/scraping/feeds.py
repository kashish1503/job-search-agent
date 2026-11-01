"""Discovery feeds: sources that are not one employer's careers page.

These are the widest nets in the layer, and each one is deliberately labelled so
the UI can tell a company-portal job from a LinkedIn card or a hiring post.

Included:

* Y Combinator's job index, which ships its postings as embedded JSON
* LinkedIn's public guest search (no login, bounded pagination)
* Google Alerts RSS feeds pointing at public LinkedIn hiring posts
* RemoteOK, Remotive and Arbeitnow public JSON APIs

Every feed returns ``(jobs, expected)`` and optionally a third element that
overrides the completeness verdict, because a bounded feed is never "partial".
"""

from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .adapters import strip_html
from .models import Job, digest


def _as_date(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:30]


def _epoch_to_date(value) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


# ── Y Combinator ──────────────────────────────────────────────────────────────


YC_INDIA = re.compile(
    r"india|bengaluru|bangalore|hyderabad|pune|gurugram|gurgaon|noida|delhi|mumbai|chennai",
    re.I,
)
YC_REMOTE = re.compile(r"remote|worldwide|global|anywhere|apac", re.I)
YC_EXCLUDED_REMOTE = re.compile(
    r"(?:us|u\.s\.|united states|canada|emea|europe|uk)\s*(?:only|based|required)"
    r"|remote\s*\((?:us|canada|emea|europe|uk)",
    re.I,
)


async def ycombinator(client, locations: list[str] | None = None):
    """The jobs page embeds a ``jobPostings`` JSON array in its React payload."""
    allowed = [item.lower() for item in (locations or ["India", "Remote"])]
    want_india = any("india" in item for item in allowed)
    want_remote = any("remote" in item for item in allowed)

    response = await client.get("https://www.ycombinator.com/jobs")
    response.raise_for_status()
    decoded = html_lib.unescape(response.text)

    marker = '"jobPostings":'
    start = decoded.find(marker)
    if start < 0:
        raise ValueError("YC jobs page no longer embeds jobPostings")
    payload, _ = json.JSONDecoder().raw_decode(decoded, start + len(marker))

    jobs = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        path = str(item.get("url") or "").strip()
        if not title or not path:
            continue
        location = str(item.get("location") or "")
        is_remote = bool(YC_REMOTE.search(location))
        india = bool(YC_INDIA.search(location))
        if not (india and want_india) and not (
            is_remote and want_remote and not YC_EXCLUDED_REMOTE.search(location)
        ):
            continue
        jid = str(item.get("id") or path)
        extras = [
            item.get("companyOneLiner"),
            f"Min experience: {item.get('minExperience')}" if item.get("minExperience") else "",
            f"Salary: {item.get('salaryRange')}" if item.get("salaryRange") else "",
            f"Equity: {item.get('equityRange')}" if item.get("equityRange") else "",
        ]
        jobs.append(
            Job(
                source="yc",
                source_job_id=jid,
                company=str(item.get("companyName") or "Y Combinator startup"),
                title=title,
                url=f"https://www.ycombinator.com{path}",
                location=location,
                description=" ".join(str(x) for x in extras if x),
                remote=is_remote,
                salary_text=str(item.get("salaryRange") or ""),
                row_id=digest("yc", jid, size=16),
                raw={
                    "platform": "yc",
                    "batch": item.get("companyBatchName"),
                    "role": item.get("prettyRole"),
                    "visa": item.get("visa"),
                },
            )
        )
    return jobs, len(payload), "bounded"


# ── LinkedIn public guest search ──────────────────────────────────────────────


def _parse_linkedin_cards(text: str, query: str, search_location: str = ""):
    soup = BeautifulSoup(text, "html.parser")
    jobs = []
    for card in soup.select("li div.base-search-card, div.job-search-card"):
        urn = str(card.get("data-entity-urn") or "")
        match = re.search(r"jobPosting:(\d+)", urn)
        link = card.select_one("a.base-card__full-link[href],a[href*='/jobs/view/']")
        jid = match.group(1) if match else (
            re.search(r"/jobs/view/(\d+)", link.get("href", "") if link else "") or [None, None]
        )[1]
        if not jid or not link:
            continue
        title_node = card.select_one(".base-search-card__title,.job-search-card__title")
        company_node = card.select_one(".base-search-card__subtitle,.job-search-card__subtitle")
        location_node = card.select_one(".job-search-card__location")
        time_node = card.select_one("time[datetime]")
        title = " ".join((title_node or link).get_text(" ", strip=True).split())
        company = (
            " ".join(company_node.get_text(" ", strip=True).split())
            if company_node
            else "LinkedIn employer"
        )
        location = (
            " ".join(location_node.get_text(" ", strip=True).split())
            if location_node
            else ""
        )
        jobs.append(
            Job(
                source="linkedin",
                source_job_id=jid,
                company=company,
                title=title,
                url=f"https://www.linkedin.com/jobs/view/{jid}",
                location=location,
                posted_at=time_node.get("datetime") if time_node else None,
                remote="remote" in location.lower(),
                row_id=digest("linkedin", jid, size=16),
                raw={"platform": "linkedin", "query": query, "search_location": search_location},
            )
        )
    return jobs


async def linkedin(client, config: dict):
    """Bounded public search: queries x locations x recency windows."""
    queries = [str(q).strip() for q in config.get("queries", []) if str(q).strip()]
    if not queries:
        return [], None, "bounded"

    locations = config.get("locations") or [{"location": "India"}]
    locations = [
        item if isinstance(item, dict) else {"location": str(item)} for item in locations
    ]
    page_size = max(1, min(int(config.get("page_size", 10)), 25))
    max_per_query = max(1, min(int(config.get("max_results_per_query", 50)), 1000))
    experience = str(config.get("experience_levels", "1,2,3"))
    delay = max(0.0, float(config.get("request_delay_seconds", 2.0)))
    recency = max(0, int(config.get("recency_seconds", 3600)))
    endpoint = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    merged: dict[str, Job] = {}
    complete = True
    for place in locations:
        base_params = {"location": str(place.get("location") or "India"), "f_E": experience}
        if place.get("geo_id"):
            base_params["geoId"] = str(place["geo_id"])
        if place.get("distance") is not None:
            base_params["distance"] = str(place["distance"])
        params = {**base_params, "f_TPR": f"r{recency}"} if recency else base_params
        for query in queries:
            for start in range(0, max_per_query, page_size):
                response = await client.get(
                    endpoint, params={"keywords": query, **params, "start": start}
                )
                if response.status_code in (429, 999):
                    if merged:
                        complete = False
                        break
                    raise RuntimeError(f"LinkedIn guest search rate-limited ({response.status_code})")
                response.raise_for_status()
                page = _parse_linkedin_cards(
                    response.text, query, base_params["location"]
                )
                for job in page:
                    merged[job.key] = job
                if len(page) < page_size:
                    break
                if delay:
                    import asyncio

                    await asyncio.sleep(delay)
            if not complete:
                break
        if not complete:
            break
    return list(merged.values()), None, "bounded" if complete else "bounded_partial"


# ── LinkedIn hiring posts via Google Alerts RSS ───────────────────────────────


POST_HIRING = re.compile(
    r"we(?:'| a)?re hiring|now hiring|hiring for|join (?:our|the) team|"
    r"open(?:ing| role| position)|send (?:me |your )?(?:resume|cv)|\bdm\b|apply",
    re.I,
)
POST_SCAM = re.compile(
    r"\$\s*\d+(?:\s*[-–]\s*\$?\d+)?\s*(?:/|per)\s*hour|earn\s+\S+\s+(?:daily|weekly)|"
    r"easy money|registration fee|training fee|whatsapp|telegram\s+(?:me|only)|"
    r"no experience.{0,40}high pay",
    re.I | re.S,
)


def _unwrap_alert_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.netloc.lower().endswith("google.com"):
        query = parse_qs(parsed.query)
        for key in ("url", "q"):
            if query.get(key):
                return unquote(query[key][0])
    return value


def parse_hiring_post_feed(xml_text: str, feed_name: str = "", keywords: list[str] | None = None):
    """RSS/Atom entries that point at public LinkedIn posts, with spam gates."""
    root = ElementTree.fromstring(xml_text)
    entries = root.findall(".//{*}entry") or root.findall(".//item")
    role_re = re.compile(
        r"machine learning|\bml\b|\bmle\b|generative ai|gen\s?ai|agentic|\bai engineer|"
        r"data scien|applied scien|research engineer|software (?:development )?engineer|"
        r"software developer|\bsde\b|\bswe\b|backend engineer|"
        + ("|".join(re.escape(word) for word in (keywords or [])) if keywords else ""),
        re.I,
    )
    location_re = re.compile(
        r"india|bengaluru|bangalore|hyderabad|pune|gurugram|gurgaon|noida|delhi|mumbai|"
        r"chennai|remote|worldwide|global|anywhere|apac",
        re.I,
    )

    jobs = []
    for entry in entries:
        def value(name):
            node = entry.find(f"{{*}}{name}")
            if node is None:
                node = entry.find(name)
            return "" if node is None else "".join(node.itertext()).strip()

        link_node = entry.find("{*}link")
        if link_node is None:
            link_node = entry.find("link")
        link = _unwrap_alert_url(
            (link_node.get("href") if link_node is not None else "") or value("link")
        )
        parsed = urlparse(link)
        path = parsed.path.lower()
        if not parsed.netloc.lower().endswith("linkedin.com") or not (
            "/posts/" in path or "/feed/update/" in path
        ):
            continue
        title = value("title")
        content = value("content") or value("description") or value("summary")
        text = " ".join(
            BeautifulSoup(f"{title} {content}", "html.parser").get_text(" ", strip=True).split()
        )
        if not (role_re.search(text) and POST_HIRING.search(text) and location_re.search(text)):
            continue
        if POST_SCAM.search(text):
            continue
        author = value("name") or value("author") or "Unknown author"
        identifier = value("id") or re.sub(r"\W+", "-", link).strip("-")
        posted = value("published") or value("pubDate") or value("updated") or None
        jobs.append(
            Job(
                source="hiring_post",
                source_job_id=identifier,
                company=f"Hiring post · {author}",
                title=title[:300] or "Hiring post",
                url=link,
                location="Remote" if re.search(r"remote|worldwide|global", text, re.I) else "India / location in post",
                description=text[:12000],
                posted_at=posted,
                remote=bool(re.search(r"remote|worldwide|anywhere|apac", text, re.I)),
                row_id=digest("hiring_post", identifier, size=16),
                raw={"platform": "hiring_post", "author": author, "feed": feed_name, "trust": "unverified"},
            )
        )
    return jobs


async def hiring_posts(client, feed_urls: list[str], keywords: list[str] | None = None, max_entries: int = 100):
    merged: dict[str, Job] = {}
    for index, url in enumerate([url for url in feed_urls if url.strip()]):
        response = await client.get(url)
        response.raise_for_status()
        for job in parse_hiring_post_feed(response.text, f"feed-{index + 1}", keywords)[:max_entries]:
            merged[job.key] = job
    return list(merged.values()), None, "bounded"


# ── Public remote-job APIs ────────────────────────────────────────────────────


async def remoteok(client, max_jobs: int = 200):
    response = await client.get("https://remoteok.com/api")
    response.raise_for_status()
    payload = response.json()
    jobs = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        jid = str(item.get("id") or item.get("slug") or "")
        if not jid:
            continue
        salary = ""
        if item.get("salary_min") or item.get("salary_max"):
            salary = f"{item.get('salary_min', '')}-{item.get('salary_max', '')} USD"
        jobs.append(
            Job(
                source="remoteok",
                source_job_id=jid,
                company=str(item.get("company") or "RemoteOK employer"),
                title=str(item.get("position")),
                url=str(item.get("url") or item.get("apply_url") or ""),
                location=str(item.get("location") or "Remote"),
                description=strip_html(item.get("description", ""))[:20000],
                posted_at=_as_date(item.get("date")),
                remote=True,
                salary_text=salary,
                row_id=digest("remoteok", jid, size=16),
                raw={"platform": "remoteok", "tags": item.get("tags")},
            )
        )
        if len(jobs) >= max_jobs:
            break
    return jobs, None


async def remotive(client, max_jobs: int = 200):
    response = await client.get(
        "https://remotive.com/api/remote-jobs", params={"limit": max_jobs}
    )
    response.raise_for_status()
    payload = response.json()
    jobs = []
    for item in payload.get("jobs") or []:
        jid = str(item.get("id") or "")
        if not jid:
            continue
        location = str(item.get("candidate_required_location") or "Remote")
        jobs.append(
            Job(
                source="remotive",
                source_job_id=jid,
                company=str(item.get("company_name") or "Remotive employer"),
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                location=location,
                description=strip_html(item.get("description", ""))[:20000],
                posted_at=_as_date(item.get("publication_date")),
                remote=True,
                salary_text=str(item.get("salary") or ""),
                row_id=digest("remotive", jid, size=16),
                raw={"platform": "remotive", "job_type": item.get("job_type"), "tags": item.get("tags")},
            )
        )
        if len(jobs) >= max_jobs:
            break
    return jobs, None


async def arbeitnow(client, pages: int = 3, max_jobs: int = 300):
    jobs = []
    total = None
    for page in range(1, max(1, pages) + 1):
        response = await client.get(
            "https://arbeitnow.com/api/job-board-api", params={"page": page}
        )
        response.raise_for_status()
        payload = response.json()
        records = payload.get("data") or []
        meta = payload.get("meta") or {}
        total = meta.get("total") or total
        if not records:
            break
        for item in records:
            jid = str(item.get("slug") or "")
            if not jid:
                continue
            jobs.append(
                Job(
                    source="arbeitnow",
                    source_job_id=jid,
                    company=str(item.get("company_name") or "Arbeitnow employer"),
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    location=str(item.get("location") or "Remote"),
                    description=strip_html(item.get("description", ""))[:20000],
                    posted_at=_epoch_to_date(item.get("created_at")),
                    remote=bool(item.get("remote")),
                    row_id=digest("arbeitnow", jid, size=16),
                    raw={"platform": "arbeitnow", "job_types": item.get("job_types")},
                )
            )
            if len(jobs) >= max_jobs:
                return jobs, total
    return jobs, total
