import os
import re
import time
import hashlib
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from . import db, llm
    from . import sources_ats
except ImportError:
    import db, llm
    import sources_ats

IST = timezone(timedelta(hours=5, minutes=30))
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-hunter-bot/1.0)"}


def _uid(*parts):
    return hashlib.md5("-".join(parts).encode()).hexdigest()[:16]


def _now_ist():
    return datetime.now(IST).isoformat()


def _first_word(text):
    return re.split(r"[\s(|]", text)[0][:60]


# ── Work-type detection ───────────────────────────────────────────────────────

def detect_work_type(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["hybrid"]):
        return "hybrid"
    if any(w in t for w in ["remote"]):
        return "remote"
    if any(w in t for w in ["onsite", "on-site", "in-office", "in office"]):
        return "onsite"
    return "unspecified"


def detect_location(text: str) -> str:
    """Best-effort single-line location extraction."""
    patterns = [
        r"\b(remote|worldwide|global)\b",
        r"\b([A-Z][a-z]+(?:,\s*[A-Z]{2})?)\b",   # City, ST
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)[:60]
    return ""


# ── Title pre-filter ──────────────────────────────────────────────────────────

def passes_title_filter(title: str, skip_patterns: list) -> bool:
    """Return False if the job title matches any skip pattern (case-insensitive).

    This runs before keyword matching and LLM scoring to cheaply drop roles
    like 'Marketing Manager' or 'Mechanical Engineer' found at tech companies.
    """
    t = title.lower()
    return not any(p.lower() in t for p in skip_patterns)


# ── Sources ───────────────────────────────────────────────────────────────────
def scrape_hn_jobs():
    """Scrape recent HN job posts via Algolia search_by_date API (last 30 days)."""
    jobs = []
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        r = requests.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"tags": "job", "hitsPerPage": 100, "numericFilters": f"created_at_i>{cutoff}"},
            headers=HEADERS,
            timeout=10,
        )
        hits = r.json().get("hits", [])
        for hit in hits:
            title = hit.get("title") or hit.get("story_title") or ""
            if not title:
                continue
            # Use the external URL if available, otherwise the HN item URL
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            uid = _uid("hn", str(hit.get("objectID", title)))
            if db.job_exists(uid):
                continue
            posted_raw = hit.get("created_at") or ""
            posted_at = posted_raw[:10] if posted_raw else ""  # YYYY-MM-DD
            jobs.append(dict(
                id=uid, source="hn_jobs", title=title[:200],
                company=_first_word(title), url=url,
                description=title,
                work_type=detect_work_type(title), location=detect_location(title),
                posted_at=posted_at,
            ))
    except Exception as e:
        print(f"[hn_jobs] {e}")
    return jobs


def scrape_hn_jobs_page(max_pages=5):
    """Scrape news.ycombinator.com/jobs — plain HTML, no JS needed.

    Each job row: <tr class="athing submission"> with title in <span class="titleline"><a>,
    company domain in <span class="sitestr">, date in <span class="age" title="ISO...">.
    Pagination: <a class='morelink'> with href like 'jobs?next=...&n=31'.
    """
    jobs = []
    url = "https://news.ycombinator.com/jobs"
    try:
        for _ in range(max_pages):
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            rows = soup.select("tr.athing.submission")
            if not rows:
                break

            for row in rows:
                item_id = row.get("id", "")
                title_el = row.select_one("span.titleline > a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if not href.startswith("http"):
                    href = f"https://news.ycombinator.com/{href}" if href else f"https://news.ycombinator.com/item?id={item_id}"

                site_el = row.select_one("span.sitestr")
                company = site_el.get_text(strip=True) if site_el else _first_word(title)

                # Date from the next sibling row's <span class="age">
                age_el = row.find_next("span", class_="age")
                posted_at = ""
                if age_el and age_el.get("title"):
                    posted_at = age_el["title"][:10]  # YYYY-MM-DD from ISO

                uid = _uid("hn-page", item_id or title)
                if db.job_exists(uid):
                    continue
                jobs.append(dict(
                    id=uid, source="hn_jobs_page", title=title[:200],
                    company=company[:80], url=href,
                    description=title,
                    work_type=detect_work_type(title), location=detect_location(title),
                    posted_at=posted_at,
                ))

            # Follow pagination
            more = soup.select_one("a.morelink")
            if not more:
                break
            next_href = more.get("href", "")
            url = f"https://news.ycombinator.com/{next_href}" if next_href else None
            if not url:
                break
    except Exception as e:
        print(f"[hn_jobs_page] {e}")
    return jobs


def _playwright_get_html(url, wait_ms=2500):
    """Render a URL with Playwright and return the HTML. Returns None on failure."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, timeout=30000)
            page.wait_for_timeout(wait_ms)
            html = page.content()
            browser.close()
        return html
    except Exception as e:
        print(f"[playwright] {url}: {e}")
        return None


def scrape_web3career(max_pages=10):
    """Scrape web3.career/remote-jobs with pagination, 30-day cutoff.

    Uses Playwright (JS-rendered). Pages via ?page=N.
    Stops when jobs are older than 30 days.
    """
    jobs = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page_ctx = browser.new_page(user_agent=HEADERS["User-Agent"])
            stop_paging = False

            for page_num in range(1, max_pages + 1):
                url = f"https://web3.career/remote-jobs?page={page_num}"
                print(f"  web3career page {page_num}...")
                page_ctx.goto(url, timeout=30000)
                page_ctx.wait_for_timeout(3000)
                html = page_ctx.content()
                soup = BeautifulSoup(html, "html.parser")

                title_cells = soup.select("td[data-jobid][scope='row']")
                if not title_cells:
                    seen_ids = set()
                    title_cells = []
                    for td in soup.select("td[data-jobid]"):
                        jid = td.get("data-jobid")
                        if jid and jid not in seen_ids:
                            seen_ids.add(jid)
                            title_cells.append(td)

                if not title_cells:
                    break  # no more jobs

                page_jobs_before = len(jobs)
                for td in title_cells:
                    job_id = td.get("data-jobid", "")
                    a = td.select_one("a[href]")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    href = a.get("href", "")
                    if not href.startswith("http"):
                        href = "https://web3.career" + href

                    siblings = soup.select(f"td[data-jobid='{job_id}']")
                    company, posted_at, location, tags = "", "", "", ""
                    for sib in siblings:
                        if sib == td:
                            continue
                        h3 = sib.select_one("h3")
                        if h3 and not company:
                            company = h3.get_text(strip=True)[:80]
                            continue
                        time_el = sib.select_one("time[datetime]")
                        if time_el and not posted_at:
                            posted_at = time_el.get("datetime", "")[:30]
                            continue
                        badges = sib.select("a[class*='badge'], span[class*='badge'], [class*='tag']")
                        if badges:
                            tags = " ".join(b.get_text(strip=True) for b in badges)
                            continue
                        txt = sib.get_text(strip=True)
                        if txt and not location and len(txt) < 60:
                            location = txt

                    # 30-day cutoff check
                    if posted_at:
                        try:
                            job_date = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                            if job_date.tzinfo is None:
                                job_date = job_date.replace(tzinfo=timezone.utc)
                            if job_date < cutoff:
                                stop_paging = True
                                continue
                        except (ValueError, TypeError):
                            pass

                    if not company:
                        company = _first_word(title)

                    uid = _uid("w3c", href)
                    if db.job_exists(uid):
                        continue
                    jobs.append(dict(
                        id=uid, source="web3career", title=title[:200],
                        company=company, url=href,
                        description=f"{title} {tags}".strip(),
                        work_type="remote", location=location or "remote",
                        posted_at=posted_at,
                    ))

                if stop_paging or len(jobs) == page_jobs_before:
                    break  # no new jobs or hit 30-day cutoff

            browser.close()
    except Exception as e:
        print(f"[web3career] {e}")
    print(f"  web3career: {len(jobs)} jobs across pages")
    return jobs


def scrape_cryptorank_funding():
    """Scrape cryptorank.io/funding-rounds with Playwright, scrolling for more rows."""
    jobs = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto("https://cryptorank.io/funding-rounds", timeout=30000)
            page.wait_for_timeout(4000)
            # Scroll down 3 times to load more rows via infinite scroll
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Cryptorank uses a table; columns are roughly:
        # 0: project name+link, 1: amount, 2: round type, 3: date, 4+: other
        SKIP_NAMES = {"project", "funds raised", "round type", "date", "sum", "total",
                      "featured", "name", "#"}
        rows = soup.select("table tbody tr") or soup.select("tr[class*='Row']")
        seen = set()

        for row in rows:
            cells = row.select("td")
            if len(cells) < 2:
                continue

            # Name + source link from first cell
            name_el = cells[0].select_one("a[href], span[title]")
            name = (name_el.get_text(strip=True) if name_el else cells[0].get_text(strip=True))
            name = re.sub(r'\s+', ' ', name).strip()[:80]

            if not name or len(name) < 2 or name.lower() in SKIP_NAMES:
                continue
            # Skip rows that are clearly UI/label text
            if any(kw in name.lower() for kw in ["featured", "funds raised", "round type"]):
                continue
            if name in seen:
                continue
            seen.add(name)

            # Source URL (link to cryptorank project page)
            source_href = ""
            if name_el and name_el.name == "a":
                source_href = name_el.get("href", "")
                if source_href and not source_href.startswith("http"):
                    source_href = "https://cryptorank.io" + source_href

            # Amount — look for a cell containing $ or M/B
            amount = "?"
            for cell in cells[1:4]:
                txt = cell.get_text(strip=True)
                if any(c in txt for c in ["$", "M", "B", "K"]) and any(c.isdigit() for c in txt):
                    amount = txt[:50]
                    break

            # Round type — usually a short label like "Seed", "Series A", etc.
            round_type = ""
            for cell in cells[1:5]:
                txt = cell.get_text(strip=True)
                if any(kw in txt.lower() for kw in
                       ["seed", "series", "pre-seed", "strategic", "private", "public", "ido", "ico", "grant"]):
                    round_type = txt[:50]
                    break

            # Date — look for a cell that looks like a date
            announced_at = ""
            for cell in cells[1:6]:
                txt = cell.get_text(strip=True)
                if re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})\b', txt, re.I):
                    announced_at = txt[:30]
                    break

            uid = _uid("cr", name)
            careers = _find_careers(name)
            time.sleep(0.3)

            db.save_funded_company(dict(
                id=uid, company=name,
                amount=amount, round_type=round_type,
                careers_url=careers,
                source_url=source_href,
                announced_at=announced_at,
                found_at=_now_ist(),
            ))
            if careers:
                jobs.append(dict(
                    id=_uid("cr-job", name), source="cryptorank_funding",
                    title=f"Hiring at {name} (recently funded)",
                    company=name, url=careers,
                    description=f"{name} raised {amount} ({round_type}). Careers: {careers}",
                    work_type="unspecified", location="",
                ))
        print(f"  cryptorank: {len(seen)} companies, {len(jobs)} with careers pages")
    except Exception as e:
        print(f"[cryptorank] {e}")
    return jobs


def scrape_dropstab():
    """Scrape dropstab.com/latest-fundraising-rounds — JS-rendered, uses Playwright."""
    jobs = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[dropstab] playwright not installed, skipping")
        return jobs

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto("https://dropstab.com/latest-fundraising-rounds", timeout=30000)
            # Wait for content to load
            page.wait_for_timeout(3000)

            # Try to find funding round rows
            # dropstab renders a table/list of funding rounds
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Try to find company/round entries — dropstab uses various selectors
        entries = (
            soup.select("tr[class*='row'], div[class*='round'], div[class*='funding']") or
            soup.select("tbody tr") or
            soup.select("[class*='TableRow'], [class*='table-row']")
        )

        for entry in entries[:50]:
            # Extract company name — look for the primary text element
            name_el = entry.select_one(
                "td:first-child, [class*='name'], [class*='project'], a[href*='/coins/']"
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)[:80]
            if not name or len(name) < 2:
                continue

            # Extract amount and round type
            tds = entry.select("td")
            amount = tds[1].get_text(strip=True) if len(tds) > 1 else "?"
            round_type = tds[2].get_text(strip=True) if len(tds) > 2 else ""

            uid = _uid("ds", name)
            careers = _find_careers(name)
            time.sleep(0.3)

            db.save_funded_company(dict(
                id=uid, company=name,
                amount=amount[:50],
                round_type=round_type[:50],
                careers_url=careers, found_at=_now_ist(),
            ))
            if careers:
                jobs.append(dict(
                    id=_uid("ds-job", name), source="dropstab_funding",
                    title=f"Hiring at {name} (recently funded, dropstab)",
                    company=name, url=careers,
                    description=f"{name} raised {amount}. Careers: {careers}",
                    work_type="unspecified", location="",
                ))
    except Exception as e:
        print(f"[dropstab] {e}")
    return jobs


def _find_careers(company_name: str) -> str:
    """Try to find a careers/jobs page for the company via Bing search."""
    CAREERS_DOMAINS = [
        "lever.co", "greenhouse.io", "ashbyhq.com", "workable.com",
        "jobs.ashbyhq", "boards.greenhouse", "apply.workable",
        "jobs.solana.com", "jobstash.xyz",
    ]
    query = _sanitize_query(f'"{company_name}" jobs careers')
    try:
        r = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "first": 1},
            headers={
                **HEADERS,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.bing.com/",
            },
            timeout=12,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 > a") or li.select_one("a[href]")
            if not a:
                continue
            href = a.get("href", "")
            lo = href.lower()
            if any(d in lo for d in CAREERS_DOMAINS):
                return href[:300]
            if any(kw in lo for kw in ["/careers", "/jobs", "career"]):
                slug = re.sub(r"[^a-z0-9]", "", company_name.lower())[:12]
                if slug and slug in re.sub(r"[^a-z0-9]", "", lo):
                    return href[:300]
    except Exception as e:
        print(f"[find_careers] {company_name!r}: {e}")
    return ""
# ── Filtering ─────────────────────────────────────────────────────────────────

def passes_filters(job: dict, cfg: dict) -> bool:
    """Return True if job passes the user's search config filters."""
    text = f"{job.get('title','')} {job.get('description','')}".lower()

    # Must match at least one keyword
    keywords = [k.lower() for k in cfg.get("keywords", [])]
    if keywords and not any(k in text for k in keywords):
        return False

    # Work type filter
    allowed_types = [t.lower() for t in cfg.get("work_type", [])]
    if allowed_types and "unspecified" not in allowed_types:
        job_wt = job.get("work_type", "unspecified").lower()
        if job_wt != "unspecified" and job_wt not in allowed_types:
            return False

    # Exclude locations
    exclude = [loc.lower() for loc in cfg.get("exclude_locations", [])]
    loc_text = f"{job.get('location','')} {job.get('description','')}".lower()
    if any(ex in loc_text for ex in exclude):
        return False

    # YoE filter — parse stated requirement from job text and compare to config
    max_yoe = cfg.get("max_yoe")
    if max_yoe is not None:
        # Match patterns like "5+ years", "4-6 years", "minimum 7 years experience"
        yoe_match = re.search(
            r'(\d+)\s*(?:\+|to|-|–)?\s*\d*\s*years?\s*(?:of\s*)?(?:experience|exp\b)',
            text,
        )
        if yoe_match:
            required_min = int(yoe_match.group(1))
            if required_min > int(max_yoe):
                return False

    return True


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_job(job: dict) -> tuple[int, str]:
    """Synchronous single-job scoring fallback (used when batching unavailable)."""
    candidate_profile = db.get_profile()
    data = llm.chat_json(llm._build_score_prompt(job, candidate_profile), max_tokens=80, task="score")
    return int(data.get("score", 0)), str(data.get("reason", ""))[:120]


def _submit_batch_scoring(jobs: list, now: str) -> dict:
    """
    Submit jobs for batch scoring via Anthropic Message Batches API (50% off).
    Saves jobs with status='pending_score'. Returns scrape summary immediately.
    Scores arrive later via poll_pending_batches().
    """
    from datetime import datetime, timezone
    candidate_profile = db.get_profile()

    batch_id = llm.create_scoring_batch(jobs, candidate_profile)
    if not batch_id:
        return None  # provider doesn't support batching

    # Save all jobs as pending_score so they show up in DB
    for job in jobs:
        job.update(score=0, reason="pending batch scoring", found_at=now,
                   status="pending_score", batch_id=batch_id)
        db.save_job(job)

    # Track the batch
    internal_id = hashlib.md5(batch_id.encode()).hexdigest()[:16]
    db.save_batch({
        "id": internal_id,
        "provider": llm.PROVIDER,
        "batch_id": batch_id,
        "status": "in_progress",
        "total_requests": len(jobs),
        "completed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[scrape] submitted batch {batch_id} with {len(jobs)} jobs for async scoring")
    return {"batch_id": batch_id, "jobs_submitted": len(jobs)}


def poll_pending_batches() -> dict:
    """
    Check all in-progress batches. For completed ones, update job scores.
    Called by APScheduler every 5 min and by POST /api/batches/poll.
    Returns summary of what was processed.
    """
    pending = db.get_pending_batches()
    if not pending:
        return {"checked": 0, "completed": 0, "jobs_scored": 0}

    total_scored = 0
    completed_count = 0

    for batch in pending:
        result = llm.poll_batch(batch["batch_id"], provider=batch.get("provider"))
        if not result or result["status"] == "in_progress":
            continue

        # Batch is done — update all job scores
        cfg = db.get_config()
        threshold = cfg.get("score_threshold", 60)

        for r in result["results"]:
            status = "new" if r["score"] >= threshold else "filtered"
            db.update_job_score(r["custom_id"], r["score"], r["reason"], status)
            total_scored += 1

        db.mark_batch_done(batch["batch_id"], result["status"])
        completed_count += 1
        print(f"[batch] {batch['batch_id']}: scored {len(result['results'])} jobs")

    return {"checked": len(pending), "completed": completed_count, "jobs_scored": total_scored}




# ── DDG site-search scraper (autonomous ATS discovery) ────────────────────────

DEFAULT_SITE_QUERIES = [
    "fullstack remote site:jobs.ashbyhq.com",
    "backend remote site:jobs.workable.com",
    "fullstack remote site:job-boards.greenhouse.io",
    "backend remote site:jobs.lever.co",
]

# These selectors describe how to pull basic job info off each platform's
# individual job-posting page. Keeps extraction logic in one place.
_ATS_META = {
    "jobs.ashbyhq.com":        {"title": "h1", "company_re": r"ashbyhq\.com/([^/]+)/"},
    "job-boards.greenhouse.io": {"title": "h1.app-title", "company_re": r"greenhouse\.io/([^/]+)/"},
    "jobs.lever.co":           {"title": "h2", "company_re": r"lever\.co/([^/]+)/"},
    "jobs.workable.com":       {"title": "h2", "company_re": r"workable\.com/([^/]+)/"},
}


def _sanitize_query(query: str) -> str:
    """
    Normalize a search query before sending it to any search engine.

    Fixes:
    - Curly/smart quotes ("web3") → straight quotes ("web3")
      These appear when queries are copy-pasted from Word/browser into the Config UI
      and cause URL double-encoding failures.
    - Strips leading/trailing whitespace.
    """
    # Replace Unicode left/right double quotation marks with ASCII double quote
    query = query.replace("\u201c", '"').replace("\u201d", '"')
    # Replace Unicode left/right single quotation marks with ASCII apostrophe
    query = query.replace("\u2018", "'").replace("\u2019", "'")
    return query.strip()


def _clean_company_name(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip(" -|,:")
    text = re.sub(r"\b(careers?|jobs?|job board|apply now|join us)\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -|,:")
    return text[:80]


def _looks_like_company(value: str) -> bool:
    text = _clean_company_name(value)
    if not text:
        return False
    lowered = text.lower()
    bad = {
        "ai/llm",
        "ai",
        "llm",
        "remote",
        "worldwide",
        "global",
        "developer",
        "software",
        "senior",
        "staff",
        "principal",
        "fullstack",
        "full stack",
        "backend",
        "frontend",
        "engineer",
        "lead",
        "job board",
        "careers",
        "jobs",
    }
    if lowered in bad:
        return False
    if len(text) <= 2:
        return False
    return True


def _company_from_title_patterns(title: str) -> str:
    patterns = [
        r"\s+at\s+([A-Z][A-Za-z0-9&'.+\- ]{1,60})$",
        r"\|\s*([A-Z][A-Za-z0-9&'.+\- ]{1,60})$",
        r"\s+-\s+([A-Z][A-Za-z0-9&'.+\- ]{1,60})$",
        r"^([A-Z][A-Za-z0-9&'.+\- ]{1,60})\s+[-|:]\s+",
    ]
    for pattern in patterns:
        match = re.search(pattern, title or "")
        if match:
            candidate = _clean_company_name(match.group(1))
            if _looks_like_company(candidate):
                return candidate
    return ""


def _company_from_json_ld(soup: BeautifulSoup) -> str:
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text()
        if not raw or "JobPosting" not in raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            org = item.get("hiringOrganization")
            if isinstance(org, dict):
                candidate = _clean_company_name(org.get("name", ""))
                if _looks_like_company(candidate):
                    return candidate
    return ""


def _company_from_meta(soup: BeautifulSoup) -> str:
    meta_candidates = [
        ('meta[property="og:site_name"]', "content"),
        ('meta[name="application-name"]', "content"),
        ('meta[name="twitter:site"]', "content"),
    ]
    for selector, attr in meta_candidates:
        tag = soup.select_one(selector)
        if tag:
            candidate = _clean_company_name(tag.get(attr, "").lstrip("@"))
            if _looks_like_company(candidate):
                return candidate
    return ""


def _company_from_page_text(soup: BeautifulSoup) -> str:
    selectors = [
        '[data-testid*="company"]',
        '[class*="company"]',
        '[class*="employer"]',
        '[class*="organization"]',
        '[itemprop="hiringOrganization"]',
    ]
    for selector in selectors:
        for tag in soup.select(selector):
            candidate = _clean_company_name(tag.get_text(" ", strip=True))
            if _looks_like_company(candidate):
                return candidate
    return ""


def _company_from_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    host = re.sub(r"^www\.", "", host)
    if any(platform in host for platform in ("greenhouse", "lever.co", "ashbyhq", "workable", "jobstash", "ycombinator", "news.ycombinator")):
        return ""
    parts = host.split(".")
    if not parts:
        return ""
    candidate = _clean_company_name(parts[0].replace("-", " ").replace("_", " ").title())
    return candidate if _looks_like_company(candidate) else ""


def _ddg_search(query: str, max_results: int = 30) -> list:
    """
    Search for job URLs using Bing HTML (primary) with a raw DDG fallback.

    WHY BING:
      DuckDuckGo blocks all datacenter/Docker IP ranges at the TCP layer —
      the SYN packet never receives a response regardless of library used.
      Bing does not apply the same blanket block to Docker containers.

    BING RESULT FORMAT:
      Results are in <li class="b_algo"> elements.
      The primary link is the first <a href="..."> inside each result.
      Bing never wraps URLs in a redirect, so hrefs are direct.

    FALLBACK:
      Raw html.duckduckgo.com is kept as last resort. It will timeout from
      most Docker deployments but may work if the host IP is not blocked.
    """
    query = _sanitize_query(query)

    # ── Primary: Bing HTML ────────────────────────────────────────────────────
    try:
        bing_urls = []
        # Bing paginates with first=1, first=11, first=21, …
        for first in range(1, max(2, (max_results // 10) + 1) * 10, 10):
            r = requests.get(
                "https://www.bing.com/search",
                params={"q": query, "first": first},
                headers={
                    **HEADERS,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.bing.com/",
                },
                timeout=15,
            )
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            found_on_page = 0
            for li in soup.select("li.b_algo"):
                a = li.select_one("h2 > a") or li.select_one("a[href]")
                if not a:
                    continue
                href = a.get("href", "")
                if href.startswith("http") and href not in bing_urls:
                    bing_urls.append(href)
                    found_on_page += 1
                if len(bing_urls) >= max_results:
                    break
            if found_on_page == 0 or len(bing_urls) >= max_results:
                break
            time.sleep(1)   # polite inter-page delay

        if bing_urls:
            return bing_urls
        print(f"[search] Bing returned 0 results for {query!r}, trying fallback")
    except Exception as e:
        print(f"[search] Bing error for {query!r}: {e}, trying fallback")

    # ── Fallback: raw DuckDuckGo HTML ────────────────────────────────────────
    # NOTE: This times out from most Docker/VPS hosts (TCP-level block).
    #       Kept here only for cases where Bing is unreachable.
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={**HEADERS, "Accept-Language": "en-US,en;q=0.9"},
            timeout=10,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        urls = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "uddg=" in href:
                import urllib.parse
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = parsed.get("uddg", [href])[0]
            if href.startswith("http") and href not in urls:
                urls.append(href)
            if len(urls) >= max_results:
                break
        return urls
    except Exception as e:
        print(f"[search] DDG fallback also failed for {query!r}: {e}")

    return []


def _fetch_job_page(url: str) -> dict:
    """
    Fetch a job-posting URL and extract title, company, description, work_type.
    Returns {} on failure so callers can safely skip.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "html.parser")

        # ── Title ──────────────────────────────────────────────────────────
        title = ""
        for sel in ["h1.app-title", "h1", "h2", "title"]:
            tag = soup.select_one(sel)
            if tag and tag.get_text(strip=True):
                title = tag.get_text(strip=True)[:200]
                break

        # ── Company (use strongest signal available) ───────────────────
        company = ""
        for domain, meta in _ATS_META.items():
            if domain in url:
                m = re.search(meta["company_re"], url)
                if m:
                    company = _clean_company_name(m.group(1).replace("-", " ").title())
                break
        if not company:
            company = _company_from_json_ld(soup)
        if not company:
            company = _company_from_meta(soup)
        if not company:
            company = _company_from_page_text(soup)
        if not company:
            company = _company_from_title_patterns(title)
        if not company:
            company = _company_from_domain(url)

        # ── Description (grab all visible text from main/article/body) ──
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body = soup.find("main") or soup.find("article") or soup.body
        description = (body.get_text(" ", strip=True) if body else "")[:3000]

        if not title:
            return {}

        return dict(
            title=title,
            company=company or _clean_company_name(_first_word(title)),
            description=description,
            work_type=detect_work_type(title + " " + description[:500]),
            location=detect_location(description[:500]),
        )
    except Exception as e:
        print(f"[fetch_job_page] {url}: {e}")
        return {}


def scrape_ddg_site_search(max_combos_per_run: int = 20) -> list:
    """
    Autonomously scrape jobs by querying DuckDuckGo with site: operator.

    Strategy
    --------
    1.  Reads site_search_queries from config (list of "keyword site:domain" strings).
    2.  Cross-products each base query with config.keywords so every keyword you
        care about gets searched on every ATS platform.
    3.  Tracks every (query) in ddg_search_log; skips ones already searched today.
    4.  Processes up to max_combos_per_run new queries per scrape run.
    5.  For each matching URL, fetches the job page and extracts title/company/desc.

    Adding more keywords in Config → more searches generated automatically.
    Adding more entries to site_search_queries → covers more ATS boards.
    Result: each daily scrape explores a different slice → unlimited coverage over time.
    """
    cfg = db.get_config()
    base_queries = cfg.get("site_search_queries", DEFAULT_SITE_QUERIES)
    keywords = cfg.get("keywords", [])

    # Build combos: for each base "role remote site:domain", swap the first
    # token with each config keyword — or just use the base query as-is.
    combos = []
    for base in base_queries:
        combos.append(base)  # always include the base query itself
        # Also generate per-keyword variants if base has a site: token
        if "site:" in base:
            site_part = "site:" + base.split("site:")[-1].strip()
            site_part = re.sub(r"^site:https?://", "site:", site_part)  # strip http(s)
            for kw in keywords[:8]:  # cap at 8 to avoid explosion
                variant = f"{kw} remote {site_part}"
                if variant not in combos:
                    combos.append(variant)

    # Skip already-searched combos (per today)
    unsearched = [q for q in combos if not db.ddg_search_done_today(q)]
    to_run = unsearched[:max_combos_per_run]

    if not to_run:
        print("[ddg_site_search] all combos already searched today — nothing to do")
        return []

    print(f"[ddg_site_search] running {len(to_run)} search combos "
          f"({len(combos) - len(to_run)} skipped, already done today)")

    all_jobs = []
    for query in to_run:
        urls = _ddg_search(query)
        print(f"  query={query!r} → {len(urls)} URLs")
        new_jobs = []
        for url in urls:
            uid = _uid("ddg", url)
            if db.job_exists(uid):
                continue
            info = _fetch_job_page(url)
            if not info:
                continue
            new_jobs.append(dict(
                id=uid,
                source="ddg_site_search",
                url=url,
                posted_at="",
                **info,
            ))
            time.sleep(0.3)  # polite crawl delay between job pages

        db.log_ddg_search(query, len(new_jobs))
        all_jobs.extend(new_jobs)
        time.sleep(2)  # polite delay between DDG queries

    return all_jobs

# ── Main ──────────────────────────────────────────────────────────────────────

def run_scrape(sources=None):
    db.init_db()
    cfg = db.get_config()
    active = sources or ["hn_jobs", "hn_jobs_page", "web3career", "cryptorank", "dropstab", "ats", "ddg_site_search", "jobstash", "solana_jobs"]
    skip_titles = cfg.get("skip_title_patterns", [])
    raw = []

    if "hn_jobs" in active:
        j = scrape_hn_jobs(); print(f"  hn_jobs: {len(j)}"); raw += j
    if "hn_jobs_page" in active:
        j = scrape_hn_jobs_page(); print(f"  hn_jobs_page: {len(j)}"); raw += j
    if "web3career" in active:
        j = scrape_web3career(); print(f"  web3career: {len(j)}"); raw += j
    if "cryptorank" in active:
        j = scrape_cryptorank_funding(); print(f"  cryptorank: {len(j)}"); raw += j
    if "dropstab" in active:
        j = scrape_dropstab(); print(f"  dropstab: {len(j)}"); raw += j
    if "ats" in active:
        j = sources_ats.scrape_ats(); print(f"  ats: {len(j)}"); raw += j
    if "jobstash" in active:
        j = scrape_jobstash(); print(f"  jobstash: {len(j)}"); raw += j
    if "solana_jobs" in active:
        j = scrape_solana_jobs(); print(f"  solana_jobs: {len(j)}"); raw += j
    # if "ddg_site_search" in active:
    #     j = scrape_ddg_site_search(); print(f"  ddg_site_search: {len(j)}"); raw += j

    # 1. Title pre-filter — cheapest check, runs before everything else
    title_passed = [j for j in raw if passes_title_filter(j.get("title", ""), skip_titles)]
    title_dropped = len(raw) - len(title_passed)
    if title_dropped:
        print(f"[scrape] title filter dropped {title_dropped} non-relevant roles")

    # 2. Search-config filter (keywords, work type, location, YoE)
    filtered = [j for j in title_passed if passes_filters(j, cfg)]
    print(f"[scrape] {len(raw)} raw → {len(title_passed)} title-ok → {len(filtered)} pass filters, scoring...")

    # Skip jobs already in DB (no need to re-score)
    new_jobs = [j for j in filtered if not db.job_exists(j["id"])]
    print(f"[scrape] {len(new_jobs)} new jobs to score ({len(filtered) - len(new_jobs)} already in DB)")

    threshold = cfg.get("score_threshold", 60)
    now = _now_ist()

    # ── Save ALL new jobs immediately with status='unscored' ──────────────────
    # 'unscored' is the resume marker — on next run these get picked up again.
    for job in new_jobs:
        db.save_job({**job, "score": 0, "reason": "not yet scored",
                     "found_at": now, "status": "unscored"})

    # ── Also grab any jobs from previous runs that never got scored ───────────
    unscored_ids = db.get_unscored_job_ids()
    # Merge: new_jobs already in list, add previously-unscored ones from DB
    already_unscored = [j for j in filtered if j["id"] in unscored_ids
                        and j not in new_jobs]
    to_score_pool = new_jobs + already_unscored

    # ── Cap scoring per run (ollama is slow) ─────────────────────────────────
    MAX_SCORE_PER_RUN = int(os.environ.get("MAX_SCORE_PER_RUN", "200"))
    to_score = to_score_pool[:MAX_SCORE_PER_RUN]
    skipped = len(to_score_pool) - len(to_score)
    if skipped:
        print(f"[scrape] {skipped} jobs deferred to next run (cap={MAX_SCORE_PER_RUN})")

    surfaced = []
    batch_info = None

    if to_score:
        batch_info = _submit_batch_scoring(to_score, now)

        if not batch_info:
            # Provider returned None — no batch support, score synchronously
            for job in to_score:
                score, reason = score_job(job)
                status = "new" if score >= threshold else "filtered"
                db.update_job_score(job["id"], score, reason, status)
                if score >= threshold:
                    surfaced.append({**job, "score": score, "reason": reason})
        else:
            # Ollama batch is synchronous — it blocks until all workers finish,
            # so we can poll immediately and have real scores right away.
            # OpenAI / Anthropic batches are async — scores arrive later via scheduler.
            if llm.PROVIDER == "ollama":
                poll_pending_batches()
                # Re-read scored jobs from DB so surfaced reflects actual scores
                for job in to_score:
                    row = db.get_job(job["id"])
                    if row and row.get("score", 0) >= threshold:
                        surfaced.append(row)
            # For async providers, surfaced stays empty — the frontend will show
            # jobs once the scheduler polls and scores them.

    # ── Save rejected (failed filter) jobs ───────────────────────────────────
    for job in raw:
        if job not in filtered and not db.job_exists(job["id"]):
            reason = ("title filter (non-relevant role)"
                      if not passes_title_filter(job.get("title", ""), skip_titles)
                      else "filtered out (work type / location / keywords)")
            db.save_job({**job, "score": 0, "reason": reason,
                         "found_at": now, "status": "filtered"})

    surfaced.sort(key=lambda x: x.get("score", 0), reverse=True)
    result = {"total": len(raw), "filtered": len(filtered),
              "new": len(new_jobs), "unscored_resumed": len(already_unscored),
              "surfaced": surfaced, "threshold": threshold}
    if batch_info:
        result["batch"] = batch_info
    return result

# ── jobstash.xyz ──────────────────────────────────────────────────────────────

def scrape_jobstash(max_pages: int = 5) -> list:
    """Scrape jobstash.xyz — tries the public JSON API first, falls back to Playwright.

    API endpoint (unofficial but stable):
      GET https://api.jobstash.xyz/api/v1/jobs/list?page=N&limit=50
    Response shape:
      { "data": [ { "id", "title", "url", "organization": { "name" }, 
                    "tags": [...], "salary", "location", "timestamp" } ] }

    If the API shape changes, the Playwright fallback renders the /jobs page and
    picks job cards via [data-testid="job-card"] or the <article> selector that
    jobstash uses in its Next.js build.
    """
    jobs = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # ── Primary: JSON API ─────────────────────────────────────────────────────
    try:
        for page in range(1, max_pages + 1):
            r = requests.get(
                "https://api.jobstash.xyz/api/v1/jobs/list",
                params={"page": page, "limit": 50},
                headers={**HEADERS, "Accept": "application/json"},
                timeout=15,
            )
            if r.status_code != 200:
                print(f"[jobstash] API page {page} → HTTP {r.status_code}, stopping")
                break

            payload = r.json()
            # Accept both {"data": [...]} and a bare list at root
            items = payload.get("data") or payload if isinstance(payload, list) else []
            if not items:
                break  # no more pages

            new_on_page = 0
            for item in items:
                # Skip old postings
                ts = item.get("timestamp") or item.get("createdAt") or ""
                posted_at = ts[:10] if ts else ""
                if ts:
                    try:
                        job_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if job_date.tzinfo is None:
                            job_date = job_date.replace(tzinfo=timezone.utc)
                        if job_date < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass

                title   = (item.get("title") or "")[:200]
                company = (item.get("organization", {}) or {}).get("name", "") or _first_word(title)
                url     = item.get("url") or item.get("jobstashUrl") or ""
                if not url:
                    slug = item.get("shortUUID") or item.get("id") or ""
                    url  = f"https://jobstash.xyz/jobs/{slug}" if slug else ""

                if not title or not url:
                    continue

                # Tags become part of the description for keyword matching
                tags = " ".join(
                    t.get("name", t) if isinstance(t, dict) else str(t)
                    for t in (item.get("tags") or [])
                )
                location    = item.get("location") or detect_location(tags)
                description = f"{title} {tags}".strip()

                uid = _uid("js", url)
                if db.job_exists(uid):
                    continue

                jobs.append(dict(
                    id=uid, source="jobstash", title=title,
                    company=company[:80], url=url,
                    description=description,
                    work_type=detect_work_type(description),
                    location=location[:60],
                    posted_at=posted_at,
                ))
                new_on_page += 1

            if new_on_page == 0:
                break  # hit the already-seen horizon
            time.sleep(1)

        if jobs:
            print(f"  jobstash (API): {len(jobs)} jobs")
            return jobs
        print("[jobstash] API returned no usable jobs — trying Playwright fallback")

    except Exception as e:
        print(f"[jobstash] API error: {e} — trying Playwright fallback")

    # ── Fallback: Playwright (JS render) ─────────────────────────────────────
    # jobstash is a Next.js app; cards live inside <article> elements or elements
    # with data-testid="job-card". The <a href="/jobs/..."> inside each card has
    # the job slug. Title is in the first <h2> or <h3> inside the card.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page_ctx = browser.new_page(user_agent=HEADERS["User-Agent"])

            for page_num in range(1, max_pages + 1):
                url_page = f"https://jobstash.xyz/jobs?page={page_num}"
                print(f"  jobstash Playwright page {page_num}...")
                page_ctx.goto(url_page, timeout=30000)
                page_ctx.wait_for_timeout(3500)
                html = page_ctx.content()
                soup = BeautifulSoup(html, "html.parser")

                # jobstash uses <article> per job card or a wrapper div
                cards = (
                    soup.select("article[data-testid='job-card']") or
                    soup.select("article") or
                    soup.select("div[data-testid='job-card']") or
                    soup.select("[class*='JobCard'], [class*='job-card']")
                )
                if not cards:
                    break

                new_on_page = 0
                for card in cards:
                    a_el = card.select_one("a[href*='/jobs/']")
                    if not a_el:
                        continue
                    href = a_el.get("href", "")
                    if not href.startswith("http"):
                        href = "https://jobstash.xyz" + href

                    title_el = card.select_one("h2, h3, [class*='title']")
                    title    = (title_el.get_text(strip=True) if title_el else "")[:200]
                    if not title:
                        continue

                    company_el = card.select_one("[class*='company'], [class*='org']")
                    company    = (company_el.get_text(strip=True) if company_el else _first_word(title))[:80]

                    description = card.get_text(" ", strip=True)[:2000]

                    uid = _uid("js", href)
                    if db.job_exists(uid):
                        continue

                    jobs.append(dict(
                        id=uid, source="jobstash", title=title,
                        company=company, url=href,
                        description=description,
                        work_type=detect_work_type(description),
                        location=detect_location(description),
                        posted_at="",
                    ))
                    new_on_page += 1

                if new_on_page == 0:
                    break
            browser.close()
    except Exception as e:
        print(f"[jobstash] Playwright fallback error: {e}")

    print(f"  jobstash (Playwright): {len(jobs)} jobs")
    return jobs


# ── jobs.solana.com ───────────────────────────────────────────────────────────

def scrape_solana_jobs() -> list:
    """Scrape jobs.solana.com — a Greenhouse-backed board for the Solana ecosystem.

    The public Greenhouse JSON API (no auth required):
      GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
    jobs.solana.com's Greenhouse board token is inferred from the page embed or from
    the canonical Greenhouse URL (solana / solana-labs). We try both known tokens and
    fall back to Playwright scraping the rendered iframe if neither works.

    Greenhouse job shape:
      { "id", "title", "absolute_url", "location": { "name" },
        "updated_at", "content" (HTML description) }
    """
    jobs = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)  # Solana jobs stay up longer

    # Known Greenhouse board slugs for solana.com ecosystem
    GREENHOUSE_TOKENS = ["solana", "solanalabs", "solana-foundation"]

    # ── Primary: Greenhouse JSON API ─────────────────────────────────────────
    found_via_api = False
    for token in GREENHOUSE_TOKENS:
        try:
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                params={"content": "true"},
                headers={**HEADERS, "Accept": "application/json"},
                timeout=15,
            )
            if r.status_code != 200:
                continue  # try next token

            items = r.json().get("jobs", [])
            if not items:
                continue

            found_via_api = True
            for item in items:
                ts = item.get("updated_at") or ""
                posted_at = ts[:10] if ts else ""
                if ts:
                    try:
                        job_date = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if job_date.tzinfo is None:
                            job_date = job_date.replace(tzinfo=timezone.utc)
                        if job_date < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass

                title    = (item.get("title") or "")[:200]
                url      = item.get("absolute_url") or ""
                location = (item.get("location") or {}).get("name", "")[:60]
                # Strip HTML tags from description
                raw_html = item.get("content") or ""
                description = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)[:3000]

                if not title or not url:
                    continue

                uid = _uid("sol", url)
                if db.job_exists(uid):
                    continue

                jobs.append(dict(
                    id=uid, source="solana_jobs", title=title,
                    company="Solana Foundation",
                    url=url, description=description,
                    work_type=detect_work_type(f"{title} {location} {description[:300]}"),
                    location=location,
                    posted_at=posted_at,
                ))
            break  # got results from this token, stop trying others

        except Exception as e:
            print(f"[solana_jobs] Greenhouse token {token!r} error: {e}")
            continue

    if found_via_api:
        print(f"  solana_jobs (Greenhouse API): {len(jobs)} jobs")
        return jobs

    print("[solana_jobs] Greenhouse API failed — trying Playwright fallback")

    # ── Fallback: Playwright (renders the iframe embed) ──────────────────────
    # jobs.solana.com embeds a Greenhouse iframe or renders jobs server-side.
    # Selector notes: Greenhouse renders a <div class="opening"> per job with
    # an <a> (the title link) and a <span class="location">.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page_ctx = browser.new_page(user_agent=HEADERS["User-Agent"])
            page_ctx.goto("https://jobs.solana.com/jobs", timeout=30000)
            page_ctx.wait_for_timeout(4000)
            html = page_ctx.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Greenhouse HTML board layout — each job is a .opening div
        openings = (
            soup.select("div.opening") or
            soup.select("div[class*='job-post'], tr.job-post") or
            soup.select("[class*='opening'], [class*='job-listing']")
        )
        for op in openings:
            a = op.select_one("a[href]")
            if not a:
                continue
            title = a.get_text(strip=True)[:200]
            href  = a.get("href", "")
            if not href.startswith("http"):
                href = "https://jobs.solana.com" + href

            loc_el   = op.select_one(".location, [class*='location']")
            location = (loc_el.get_text(strip=True) if loc_el else "")[:60]

            uid = _uid("sol", href)
            if db.job_exists(uid):
                continue

            jobs.append(dict(
                id=uid, source="solana_jobs", title=title,
                company="Solana Foundation",
                url=href, description=f"{title} {location}".strip(),
                work_type=detect_work_type(f"{title} {location}"),
                location=location,
                posted_at="",
            ))
    except Exception as e:
        print(f"[solana_jobs] Playwright fallback error: {e}")

    print(f"  solana_jobs (Playwright): {len(jobs)} jobs")
    return jobs
