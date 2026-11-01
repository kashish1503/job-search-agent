"""Extractors for the different kinds of URLs a careers page can be.

Every adapter is an ``async`` function with the same contract::

    jobs, expected = await adapter(client, ..., company="Acme")

``expected`` is the total the portal itself declares, when it declares one. It is
what lets the health report say ``verified`` instead of merely ``unstructured``.

The adapters are grouped exactly like the JobWatch crawler:

1. ATS board APIs (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee)
2. Search / listing endpoints (Amazon India, Google Careers)
3. Data embedded in the page (Next.js payloads, JSON-LD)
4. Sitemap crawling
5. Server-rendered job cards
6. Generic link extraction, the last resort
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import Job, clean_url, digest

USER_AGENT = "Mozilla/5.0 (compatible; openclaw-jobwatch/1.0)"
HTML_HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}


def md5_uid(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()[:16]


def strip_html(value: str) -> str:
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def _text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _first(mapping: dict, *keys, default=""):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _location(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        address = value.get("address")
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            text = ", ".join(dict.fromkeys(str(p) for p in parts if p))
            if text:
                return text
        parts = [
            value.get("name"),
            value.get("city"),
            value.get("region"),
            value.get("state"),
            value.get("country"),
            value.get("countryCode"),
        ]
        return ", ".join(dict.fromkeys(str(p) for p in parts if p))
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                address = item.get("address") or item
                if isinstance(address, dict):
                    parts.extend(
                        str(address.get(k))
                        for k in ("addressLocality", "addressRegion", "addressCountry")
                        if address.get(k)
                    )
            else:
                parts.append(str(item))
        return ", ".join(dict.fromkeys(p for p in parts if p))
    return ""


# ── 1. ATS board APIs ─────────────────────────────────────────────────────────


async def greenhouse(client, slug: str, company: str):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    response = await client.get(url, params={"content": "false"})
    response.raise_for_status()
    data = response.json()
    raw = data.get("jobs") or []
    expected = (data.get("meta") or {}).get("total")

    jobs = []
    for item in raw:
        jid = str(item.get("id") or "")
        if not jid:
            continue
        jobs.append(
            Job(
                source="greenhouse",
                source_job_id=jid,
                company=company,
                title=_text(item.get("title")),
                url=item.get("absolute_url") or f"https://boards.greenhouse.io/{slug}/jobs/{jid}",
                location=_location(item.get("location")),
                posted_at=item.get("updated_at"),
                row_id=md5_uid(f"gh:{slug}:{jid}"),  # same id as the legacy fetcher
                raw={"platform": "greenhouse", "slug": slug},
            )
        )
    return jobs, expected


async def lever(client, slug: str, company: str):
    url = f"https://api.lever.co/v0/postings/{slug}"
    response = await client.get(url, params={"mode": "json"})
    response.raise_for_status()
    postings = response.json()
    if not isinstance(postings, list):
        postings = postings.get("data") or []

    jobs = []
    for item in postings:
        jid = str(item.get("id") or "")
        if not jid:
            continue
        categories = item.get("categories") or {}
        location = _location(categories.get("location")) or _location(
            item.get("workplaceType")
        )
        jobs.append(
            Job(
                source="lever",
                source_job_id=jid,
                company=company,
                title=_text(item.get("text")),
                url=item.get("hostedUrl") or f"https://jobs.lever.co/{slug}/{jid}",
                location=location,
                description=item.get("descriptionPlain") or strip_html(item.get("description", "")),
                posted_at=item.get("createdAt"),
                remote=str(item.get("workplaceType", "")).lower() == "remote",
                row_id=md5_uid(f"lv:{slug}:{jid}"),
                raw={"platform": "lever", "slug": slug},
            )
        )
    return jobs, None


async def ashby(client, slug: str, company: str):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    response = await client.get(url, params={"includeCompensation": "true"})
    response.raise_for_status()
    data = response.json()
    postings = data.get("jobPostings") or data.get("jobs") or []

    jobs = []
    for item in postings:
        jid = str(item.get("id") or item.get("jobId") or "")
        if not jid:
            continue
        location = _location(item.get("locationName")) or _location(item.get("location"))
        jobs.append(
            Job(
                source="ashby",
                source_job_id=jid,
                company=company,
                title=_text(item.get("title")),
                url=item.get("externalLink") or f"https://jobs.ashbyhq.com/{slug}/{jid}",
                location=location,
                description=item.get("descriptionPlain") or strip_html(item.get("descriptionHtml", "")),
                posted_at=item.get("publishedDate") or item.get("updatedAt"),
                remote=bool(item.get("isRemote")),
                salary_text=_text(item.get("compensationTierSummary")),
                row_id=md5_uid(f"ab:{slug}:{jid}"),
                raw={"platform": "ashby", "slug": slug},
            )
        )
    return jobs, None


async def workable(client, slug: str, company: str):
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    response = await client.get(url, params={"details": "true"})
    response.raise_for_status()
    data = response.json()
    raw = data.get("jobs") or []
    expected = data.get("total")

    jobs = []
    for item in raw:
        jid = str(item.get("shortcode") or item.get("id") or "")
        if not jid:
            continue
        location = _location(item.get("location")) or _location(item.get("city"))
        jobs.append(
            Job(
                source="workable",
                source_job_id=jid,
                company=company,
                title=_text(item.get("title")),
                url=item.get("url")
                or item.get("application_url")
                or f"https://apply.workable.com/{slug}/j/{jid}/",
                location=location,
                description=strip_html(item.get("description", "")),
                posted_at=item.get("created_at"),
                remote=bool(item.get("telecommuting")),
                row_id=digest("workable", slug, jid, size=16),
                raw={"platform": "workable", "slug": slug},
            )
        )
    return jobs, expected


async def smartrecruiters(client, slug: str, company: str, max_pages: int = 10):
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    items = []
    total = 0
    offset = 0
    for _ in range(max_pages):
        response = await client.get(url, params={"limit": 100, "offset": offset})
        response.raise_for_status()
        data = response.json()
        total = int(data.get("totalFound") or 0)
        page = data.get("content") or []
        items.extend(page)
        if not page or len(items) >= total:
            break
        offset += len(page)

    jobs = []
    for item in items:
        jid = str(item.get("id") or "")
        if not jid:
            continue
        location = _location(item.get("location"))
        jobs.append(
            Job(
                source="smartrecruiters",
                source_job_id=jid,
                company=company,
                title=_text(item.get("name")),
                url=f"https://jobs.smartrecruiters.com/{slug}/{jid}",
                location=location,
                posted_at=item.get("releasedDate"),
                remote="remote" in location.lower(),
                row_id=digest("smartrecruiters", slug, jid, size=16),
                raw={"platform": "smartrecruiters", "slug": slug},
            )
        )
    return jobs, total or None


async def recruitee(client, slug: str, company: str):
    url = f"https://{slug}.recruitee.com/api/offers/"
    response = await client.get(url)
    response.raise_for_status()
    data = response.json()
    offers = data.get("offers") or []

    jobs = []
    for item in offers:
        jid = str(item.get("id") or "")
        if not jid:
            continue
        jobs.append(
            Job(
                source="recruitee",
                source_job_id=jid,
                company=company,
                title=_text(item.get("title")),
                url=item.get("careers_url") or item.get("url") or f"https://{slug}.recruitee.com/o/{jid}",
                location=_location(item.get("location")) or _location(item.get("city")),
                description=strip_html(item.get("description", "")),
                posted_at=item.get("created_at"),
                remote=bool(item.get("remote")),
                row_id=digest("recruitee", slug, jid, size=16),
                raw={"platform": "recruitee", "slug": slug},
            )
        )
    return jobs, None


# ── 2. Search / listing endpoints ─────────────────────────────────────────────


async def amazon_india(client, company: str = "Amazon", country: str = "IND", max_pages: int = 6):
    """Amazon's public search.json, paginated. It declares the hit total."""
    endpoint = "https://www.amazon.jobs/en/search.json"
    first = await client.get(
        endpoint, params={"country": country, "result_limit": 100, "offset": 0}
    )
    first.raise_for_status()
    data = first.json()
    total = int(data.get("hits") or 0)
    payloads = [data]

    semaphore = asyncio.Semaphore(4)

    async def page(offset: int):
        async with semaphore:
            last = None
            for attempt in range(4):
                response = await client.get(
                    endpoint,
                    params={"country": country, "result_limit": 100, "offset": offset},
                )
                if response.status_code == 200:
                    return response.json()
                last = response
                if response.status_code not in (429, 500, 502, 503, 504):
                    response.raise_for_status()
                await asyncio.sleep(1.5 * (attempt + 1))
            if last is not None:
                last.raise_for_status()
            return {}

    offsets = list(range(100, min(total, max_pages * 100), 100))
    if offsets:
        payloads += await asyncio.gather(*(page(offset) for offset in offsets))

    jobs = []
    seen = set()
    for payload in payloads:
        for item in payload.get("jobs") or []:
            jid = str(item.get("id_icims") or item.get("id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            path = item.get("job_path") or ""
            jobs.append(
                Job(
                    source="amazon",
                    source_job_id=jid,
                    company=company,
                    title=_text(item.get("title")),
                    url=urljoin("https://www.amazon.jobs", path) if path else "",
                    location=_text(item.get("location")),
                    description=_text(item.get("description_short"))
                    or _text(item.get("job_summary")),
                    posted_at=item.get("posted_date"),
                    remote="remote" in _text(item.get("location")).lower(),
                    row_id=digest("amazon", jid, size=16),
                    raw={"platform": "amazon", "category": item.get("business_category")},
                )
            )
    return jobs, total


async def google_careers(client, company: str = "Google", location: str = "India", company_filter: str = "", max_pages: int = 20):
    base = "https://www.google.com/about/careers/applications/jobs/results/"
    jobs = []
    seen = set()
    for page in range(1, max_pages + 1):
        params = {"location": location, "page": page}
        if company_filter:
            params["company"] = company_filter
        response = await client.get(base, params=params)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        added = 0
        for anchor in soup.find_all("a", attrs={"aria-label": True, "href": True}):
            label = anchor.get("aria-label", "")
            if not label.startswith("Learn more about"):
                continue
            href = urljoin(base, anchor["href"])
            ident = href.split("/results/")[-1].split("?")[0]
            if ident in seen:
                continue
            seen.add(ident)
            added += 1
            card = anchor.find_parent("div", class_="sMn82b") or anchor.parent
            jobs.append(
                Job(
                    source="google",
                    source_job_id=ident,
                    company=company_filter and "Google DeepMind" or company,
                    title=label.replace("Learn more about", "").strip(),
                    url=href,
                    location=location,
                    description=" ".join(card.get_text(" ", strip=True).split())[:6000],
                    row_id=digest("google", ident, size=16),
                    raw={"platform": "google"},
                )
            )
        if not added:
            break
    return jobs, None


# ── 3. Data embedded in the page ──────────────────────────────────────────────


def _looks_like_job(item: dict) -> bool:
    return isinstance(item, dict) and bool(_first(item, "title", "jobTitle", "position", "text"))


def _find_job_list(node, depth: int = 0):
    """Find the largest list of dicts that look like job records."""
    best = []
    if depth > 12:
        return best
    if isinstance(node, list):
        dicts = [item for item in node if isinstance(item, dict)]
        if len(dicts) >= 3:
            looking = sum(1 for item in dicts if _looks_like_job(item))
            if looking >= max(3, len(dicts) // 2) and len(dicts) > len(best):
                best = dicts
        for item in node:
            candidate = _find_job_list(item, depth + 1)
            if len(candidate) > len(best):
                best = candidate
    elif isinstance(node, dict):
        for value in node.values():
            candidate = _find_job_list(value, depth + 1)
            if len(candidate) > len(best):
                best = candidate
    return best


def _embedded_jobs(records: list, company: str, source: str, base_url: str = ""):
    jobs = []
    for item in records:
        title = _text(_first(item, "title", "jobTitle", "position", "text", "name"))
        if not title:
            continue
        jid = str(
            _first(item, "id", "jobId", "greenhouseId", "shortcode", "slug", "uuid", default="")
        )
        raw_url = _first(
            item,
            "absolute_url",
            "hostedUrl",
            "externalLink",
            "applyUrl",
            "jobUrl",
            "url",
            default="",
        )
        if not raw_url and item.get("slug"):
            raw_url = urljoin(base_url, str(item["slug"])) if base_url else str(item["slug"])
        if not jid:
            jid = raw_url or title
        location = _location(_first(item, "location", "locationName", "locations", "city"))
        description = _text(
            _first(item, "descriptionPlain", "description", "content", "jobDescription")
        )
        if not description:
            description = strip_html(_first(item, "descriptionHtml", default=""))
        jobs.append(
            Job(
                source=source,
                source_job_id=str(jid),
                company=company,
                title=title,
                url=str(raw_url),
                location=location,
                description=description[:20000],
                posted_at=_first(item, "publishedDate", "createdAt", "updated_at", "date", default=None),
                remote=bool(_first(item, "isRemote", "remote", default=False)),
                row_id=digest(source, str(jid), size=16),
                raw={"platform": source, "embedded": True},
            )
        )
    return jobs


async def next_data(client, url: str, company: str):
    """Read a Next.js ``__NEXT_DATA__`` payload and find the job array inside it."""
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    node = soup.select_one("script#__NEXT_DATA__")
    if not node or not node.string:
        raise ValueError("page has no __NEXT_DATA__ payload")
    data = json.loads(node.string)
    records = _find_job_list(data)
    if not records:
        raise ValueError("__NEXT_DATA__ contained no job-shaped list")
    jobs = _embedded_jobs(records, company, "next_data", base_url=url)
    return jobs, len(records)


async def stripe(client, company: str = "Stripe"):
    """Stripe keeps its whole job index in __NEXT_DATA__ as jobIndexData."""
    url = "https://stripe.com/careers/search"
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    node = soup.select_one("script#__NEXT_DATA__")
    if not node or not node.string:
        raise ValueError("Stripe __NEXT_DATA__ job index is missing")
    index = json.loads(node.string)["props"]["pageProps"]["jobIndexData"]
    listings = index.get("listings") or []
    locations = index.get("filters", {}).get("locations") or []

    jobs = []
    for item in listings:
        jid = str(item.get("greenhouseId") or item.get("slug") or "")
        if not jid:
            continue
        picked = [
            locations[i]
            for i in item.get("locationIndices", [])
            if isinstance(i, int) and 0 <= i < len(locations)
        ]
        location = ", ".join(
            dict.fromkeys(str(place.get("name") or "") for place in picked if place.get("name"))
        )
        jobs.append(
            Job(
                source="stripe",
                source_job_id=jid,
                company=company,
                title=_text(item.get("title")),
                url=f"https://stripe.com/jobs/listing/{item.get('slug', 'job')}/{jid}",
                location=location,
                posted_at=None,
                remote=any(bool(place.get("remote")) for place in picked),
                row_id=digest("stripe", jid, size=16),
                raw={"platform": "stripe"},
            )
        )
    return jobs, len(listings)


def jsonld_jobs(html: str, company: str, page_url: str = ""):
    """Extract schema.org JobPosting objects. Works on most modern careers pages."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text()
        if not raw or "JobPosting" not in raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in list(nodes):
            if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                nodes.extend(node["@graph"])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            if isinstance(types, list):
                is_posting = "JobPosting" in types
            else:
                is_posting = types == "JobPosting"
            if not is_posting:
                continue
            title = _text(node.get("title"))
            if not title:
                continue
            employer = node.get("hiringOrganization") or {}
            name = company or _text(employer.get("name") if isinstance(employer, dict) else "")
            jid = str(
                node.get("identifier")
                if isinstance(node.get("identifier"), str)
                else (node.get("identifier") or {}).get("value", "")
                or node.get("url")
                or title
            )
            salary = node.get("baseSalary") or {}
            salary_text = ""
            if isinstance(salary, dict):
                value = salary.get("value") or {}
                if isinstance(value, dict):
                    salary_text = " ".join(
                        str(value.get(key))
                        for key in ("minValue", "maxValue", "unitText")
                        if value.get(key)
                    )
            jobs.append(
                Job(
                    source="jsonld",
                    source_job_id=jid,
                    company=name,
                    title=title,
                    url=node.get("url") or page_url,
                    location=_location(node.get("jobLocation")),
                    description=_text(node.get("description"))[:20000],
                    posted_at=node.get("datePosted") or node.get("validThrough"),
                    remote="remote" in _text(node.get("jobLocationType")).lower(),
                    salary_text=salary_text,
                    row_id=digest("jsonld", jid, size=16),
                    raw={"platform": "jsonld"},
                )
            )
    return jobs


# ── 4. Sitemaps ───────────────────────────────────────────────────────────────


_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


async def sitemap(client, url: str, company: str, path_pattern: str = "", max_pages: int = 120):
    """Walk a sitemap so detail pages the landing page never links are still found."""
    seeds = [url] if url.endswith((".xml", ".xml.gz")) else [
        url.rstrip("/") + "/sitemap.xml",
        url.rstrip("/") + "/sitemap_index.xml",
    ]
    sitemap_texts = []
    for seed in seeds:
        try:
            response = await client.get(seed)
            if response.status_code == 200 and "<" in response.text:
                sitemap_texts.append(response.text)
        except Exception:
            continue
    if not sitemap_texts:
        return [], None

    locs = []
    for text in sitemap_texts:
        found = _LOC.findall(text)
        if "<sitemapindex" in text.lower():
            children = [loc for loc in found if loc.endswith((".xml", ".xml.gz"))][:10]
            for child in children:
                try:
                    response = await client.get(child)
                    if response.status_code == 200:
                        locs.extend(_LOC.findall(response.text))
                except Exception:
                    continue
        else:
            locs.extend(found)

    locs = list(dict.fromkeys(locs))
    if path_pattern:
        pattern = re.compile(path_pattern, re.I)
        locs = [loc for loc in locs if pattern.search(urlparse(loc).path)]
    if not locs:
        return [], 0

    targets = locs[:max_pages]
    semaphore = asyncio.Semaphore(8)

    async def detail(loc: str):
        async with semaphore:
            try:
                response = await client.get(loc)
                response.raise_for_status()
                return loc, response.text
            except Exception:
                return loc, ""

    pages = await asyncio.gather(*(detail(loc) for loc in targets))
    jobs = []
    for loc, html in pages:
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        main = soup.select_one("main") or soup.body
        heading = (main or soup).find("h1")
        if not heading:
            continue
        title = " ".join(heading.get_text(" ", strip=True).split())
        if len(title) < 3:
            continue
        chunks = [" ".join(x.split()) for x in (main or soup).stripped_strings if x.strip()]
        visible = " ".join(chunks)[:12000]
        location = _guess_location(chunks)
        jobs.append(
            Job(
                source="sitemap",
                source_job_id=urlparse(loc).path.rstrip("/").rsplit("/", 1)[-1] or loc,
                company=company,
                title=title[:300],
                url=loc,
                location=location,
                description=visible[:12000],
                remote="remote" in visible.lower(),
                row_id=digest("sitemap", loc, size=16),
                raw={"platform": "sitemap"},
            )
        )
    return jobs, len(locs)


# ── 5. Server-rendered job cards ──────────────────────────────────────────────

_CITY = re.compile(
    r"india|bengaluru|bangalore|hyderabad|pune|gurugram|gurgaon|noida|delhi|mumbai|chennai|"
    r"remote|worldwide|global|anywhere|apac|london|berlin|new york|san francisco|toronto",
    re.I,
)


def _guess_location(chunks: list) -> str:
    candidates = [chunk for chunk in chunks if _CITY.search(chunk) and len(chunk) < 120]
    return min(candidates, key=len) if candidates else ""


async def html_cards(client, url: str, company: str, path_pattern: str = r"/jobs?/[^/?#]+"):
    """Parse official server-rendered job cards and keep nearby location text."""
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    visible = " ".join(soup.get_text(" ", strip=True).split())

    declared = None
    for pattern in (
        r"([\d,]+)\s+(?:open\s+)?positions",
        r"([\d,]+)\s+(?:open\s+)?jobs",
        r"([\d,]+)\s+results",
    ):
        match = re.search(pattern, visible, re.I)
        if match:
            declared = int(match.group(1).replace(",", ""))
            break

    pattern = re.compile(path_pattern, re.I)
    jobs = []
    seen = set()
    for anchor in soup.select("a[href]"):
        href = urljoin(str(response.url), anchor.get("href", ""))
        if not pattern.search(urlparse(href).path) or href in seen:
            continue
        seen.add(href)
        chunks = [" ".join(x.split()) for x in anchor.stripped_strings if x.strip()]
        title = chunks[0] if chunks else " ".join(anchor.get_text(" ", strip=True).split())
        container = anchor.find_parent(["article", "li", "tr"]) or anchor.parent
        context = " ".join(container.get_text(" ", strip=True).split()) if container else title
        if len(title) < 4 or title.lower() in {"apply", "apply now", "learn more", "view role", "view job"}:
            heading = container.find(["h1", "h2", "h3", "h4"]) if container else None
            title = " ".join(heading.get_text(" ", strip=True).split()) if heading else title
        if len(title) < 4:
            continue
        location = _guess_location(chunks[1:]) or _guess_location([context])
        jobs.append(
            Job(
                source="official_html",
                source_job_id=urlparse(href).path.rstrip("/").rsplit("/", 1)[-1] or href,
                company=company,
                title=title[:300],
                url=href,
                location=location,
                description=context[:6000],
                remote="remote" in context.lower(),
                row_id=digest("official_html", href, size=16),
                raw={"platform": "official_html"},
            )
        )
    return jobs, declared


# ── 6. Generic fallback ───────────────────────────────────────────────────────


def _declares_no_openings(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:no|0)\s+(?:global\s+|current\s+|open\s+)?(?:job\s+)?openings?\s+(?:are\s+)?available\b"
            r"|\bno\s+(?:open\s+)?positions?\s+(?:are\s+)?available\b",
            text,
            re.I,
        )
    )


_JOBISH = re.compile(r"job|career|opening|position|engineer|scientist|developer", re.I)
_LINK_NAV = {
    "career",
    "careers",
    "jobs",
    "browse jobs",
    "search jobs",
    "job search",
    "current jobs",
}


async def generic(client, url: str, company: str):
    """Last resort: JSON-LD first, then every job-looking link on the page."""
    response = await client.get(url)
    response.raise_for_status()
    html = response.text

    embeddings = jsonld_jobs(html, company, page_url=str(response.url))
    if embeddings:
        return embeddings, len(embeddings)

    soup = BeautifulSoup(html, "html.parser")
    visible = " ".join(soup.get_text(" ", strip=True).split())
    if _declares_no_openings(visible):
        return [], 0

    jobs = []
    seen = set()
    here = urlparse(str(response.url))
    for anchor in soup.select("a[href]"):
        title = " ".join(anchor.get_text(" ", strip=True).split())
        href = urljoin(str(response.url), anchor.get("href", ""))
        if len(title) < 4 or not _JOBISH.search(f"{title} {href}"):
            continue
        target = urlparse(href)
        if (target.scheme, target.netloc, target.path.rstrip("/")) == (
            here.scheme,
            here.netloc,
            here.path.rstrip("/"),
        ):
            continue
        if title.lower() in _LINK_NAV and not re.search(
            r"/job[s]?/[^/?#]+|opening|position", target.path, re.I
        ):
            continue
        if href in seen:
            continue
        seen.add(href)
        jobs.append(
            Job(
                source="html",
                source_job_id=href,
                company=company,
                title=title[:300],
                url=href,
                row_id=digest("html", href, size=16),
                raw={"platform": "generic_html"},
            )
        )
    return jobs, None


# ── Helpers used by the dispatcher ────────────────────────────────────────────


def slug_from_url(url: str, host_hint: str) -> str:
    parsed = urlparse(url)
    if host_hint not in parsed.netloc.lower():
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if "boards" in parts:
        index = parts.index("boards")
        parts = parts[index + 1 :]
    if "posting-api" in parts:
        index = parts.index("posting-api")
        parts = parts[index + 1 :]
        if parts and parts[0] == "job-board":
            parts = parts[1:]
    return parts[0].lower() if parts else ""


def ats_hint(url: str) -> tuple[str, str]:
    """Return ``(platform, slug)`` when the URL is a known ATS board."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "greenhouse.io" in host:
        slug = slug_from_url(url, "greenhouse.io")
        return ("greenhouse", slug) if slug else ("", "")
    if "lever.co" in host:
        slug = slug_from_url(url, "lever.co")
        return ("lever", slug) if slug else ("", "")
    if "ashbyhq.com" in host:
        slug = slug_from_url(url, "ashbyhq.com")
        return ("ashby", slug) if slug else ("", "")
    if "workable.com" in host:
        slug = slug_from_url(url, "workable.com")
        return ("workable", slug) if slug else ("", "")
    if "smartrecruiters.com" in host:
        slug = slug_from_url(url, "smartrecruiters.com")
        return ("smartrecruiters", slug) if slug else ("", "")
    if "recruitee.com" in host:
        return ("recruitee", parsed.netloc.split(".")[0])
    return "", ""


def is_amazon(url: str, company: str) -> bool:
    return "amazon.jobs" in url.lower() or company.strip().lower() == "amazon"


def is_google(url: str, company: str) -> bool:
    host = urlparse(url).netloc.lower()
    return (
        ("google.com" in host and "/careers" in url.lower())
        or company.strip().lower() in ("google", "google deepmind")
    )


def is_stripe(url: str, company: str) -> bool:
    return "stripe.com" in url.lower() and "/careers" in url.lower()


async def hydrate(client, jobs: list[Job], min_chars: int = 400, concurrency: int = 8):
    """Second pass: fetch full descriptions only for short JD stubs."""
    semaphore = asyncio.Semaphore(concurrency)

    async def one(job: Job):
        if len(job.description or "") > min_chars or not job.url:
            return
        async with semaphore:
            try:
                response = await client.get(job.url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                main = soup.select_one("main") or soup.body
                if main:
                    job.description = " ".join(main.get_text(" ", strip=True).split())[:30000]
                if not job.description:
                    job.raw["detail_error"] = "empty detail page"
                job.raw["detail_url"] = clean_url(job.url)
            except Exception as exc:  # a broken detail page must never fail the run
                job.raw["detail_error"] = f"{type(exc).__name__}: {exc}"

    await asyncio.gather(*(one(job) for job in jobs))
