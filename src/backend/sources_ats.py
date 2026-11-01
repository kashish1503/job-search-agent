"""
ATS direct scraping — Greenhouse, Lever, Ashby.

All three platforms expose public JSON APIs with no auth required.
Company slugs are discovered from:
  1. A hardcoded seed list of known web3/tech companies
  2. HN "Who is Hiring" comment text (auto-extracted each scrape)
  3. GitHub community lists (poteto/hiring-without-whiteboards, remoteintech)
     — fetched at most once per week, tracked in config table

Entry point: scrape_ats() — uses asyncio.run() + aiohttp for parallel fan-out.
"""

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

import requests
from bs4 import BeautifulSoup

try:
    from . import db
except ImportError:
    import db

IST = timezone(timedelta(hours=5, minutes=30))

# ── Seed company lists ────────────────────────────────────────────────────────
# Format: (slug, display_name)
# Small seed list for instant first-run results. Common Crawl discovery
# will add ~3,900 companies within the first week automatically.

GREENHOUSE_SEEDS = [
    ("coinbase", "Coinbase"), ("ripple", "Ripple"), ("chainalysis", "Chainalysis"),
    ("fireblocks", "Fireblocks"), ("consensys", "ConsenSys"),
    ("chainlink-labs", "Chainlink Labs"), ("optimism", "Optimism"),
    ("celestia", "Celestia"), ("starkware", "StarkWare"),
    ("aptos-labs", "Aptos Labs"), ("mystenlab", "Mysten Labs"),
    ("alchemyplatform", "Alchemy"), ("dydx", "dYdX"),
    ("anthropic", "Anthropic"), ("scale", "Scale AI"),
    ("cloudflare", "Cloudflare"), ("supabase", "Supabase"),
    ("stripe", "Stripe"), ("notion", "Notion"),
]

LEVER_SEEDS = [
    ("opensea", "OpenSea"), ("uniswap", "Uniswap Labs"),
    ("polygon", "Polygon"), ("aave", "Aave"), ("0x", "0x"),
    ("immutablex", "Immutable X"), ("1inch", "1inch"),
    ("wintermute-trading", "Wintermute"), ("paradigm", "Paradigm"),
    ("animoca-brands", "Animoca Brands"), ("blockworks", "Blockworks"),
    ("brave", "Brave"), ("replit", "Replit"), ("langchain", "LangChain"),
    ("fly", "Fly.io"), ("render", "Render"),
]

ASHBY_SEEDS = [
    ("vercel", "Vercel"), ("linear", "Linear"), ("bun", "Bun"),
    ("deno", "Deno"), ("prisma", "Prisma"), ("hasura", "Hasura"),
    ("ens", "ENS"), ("gitcoin", "Gitcoin"), ("safe", "Safe"),
    ("scroll", "Scroll"), ("zksync", "zkSync"),
    ("eigenlabs", "EigenLayer"), ("flashbots", "Flashbots"),
    ("ethereum-foundation", "Ethereum Foundation"),
    ("uniswap-foundation", "Uniswap Foundation"),
]


def _uid(platform: str, slug: str) -> str:
    return hashlib.md5(f"{platform}:{slug}".encode()).hexdigest()[:16]


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def seed_ats_companies():
    """Insert seed companies into ats_companies table (skips existing entries)."""
    for slug, name in GREENHOUSE_SEEDS:
        cid = _uid("greenhouse", slug)
        if not db.ats_company_exists(cid):
            db.save_ats_company({"id": cid, "platform": "greenhouse", "slug": slug,
                                 "company_name": name, "discovered_via": "seed"})
    for slug, name in LEVER_SEEDS:
        cid = _uid("lever", slug)
        if not db.ats_company_exists(cid):
            db.save_ats_company({"id": cid, "platform": "lever", "slug": slug,
                                 "company_name": name, "discovered_via": "seed"})
    for slug, name in ASHBY_SEEDS:
        cid = _uid("ashby", slug)
        if not db.ats_company_exists(cid):
            db.save_ats_company({"id": cid, "platform": "ashby", "slug": slug,
                                 "company_name": name, "discovered_via": "seed"})


# ── Company discovery from text ───────────────────────────────────────────────

_ATS_URL_PATTERNS = [
    (re.compile(r'job-boards\.greenhouse\.io/([A-Za-z0-9_-]+)', re.I), "greenhouse"),
    (re.compile(r'boards\.greenhouse\.io/([A-Za-z0-9_-]+)', re.I), "greenhouse"),
    (re.compile(r'boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)', re.I), "greenhouse"),
    (re.compile(r'jobs\.lever\.co/([A-Za-z0-9_-]+)', re.I), "lever"),
    (re.compile(r'api\.lever\.co/v0/postings/([A-Za-z0-9_-]+)', re.I), "lever"),
    (re.compile(r'jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)', re.I), "ashby"),
    (re.compile(r'api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9_-]+)', re.I), "ashby"),
]


def extract_ats_from_text(text: str) -> list:
    """Return list of (platform, slug) tuples found in arbitrary text."""
    found = []
    seen = set()
    for pattern, platform in _ATS_URL_PATTERNS:
        for m in pattern.finditer(text):
            slug = m.group(1).rstrip("/").lower()
            key = (platform, slug)
            if key not in seen:
                seen.add(key)
                found.append(key)
    return found


def discover_from_hn_text(text: str):
    """Extract ATS URLs from HN comment text and save new companies to DB."""
    for platform, slug in extract_ats_from_text(text):
        cid = _uid(platform, slug)
        if not db.ats_company_exists(cid):
            db.save_ats_company({
                "id": cid, "platform": platform, "slug": slug,
                "company_name": slug,  # will be updated when fetched
                "discovered_via": "hn_whoishiring",
            })


def discover_from_github_lists():
    """
    Discover company slugs from external sources: Common Crawl + GitHub lists.
    Runs at most once per week (guarded by config key 'ats_discovery_last_run').
    """
    conn = __import__("sqlite3").connect(db.DB_PATH)
    row = conn.execute(
        "SELECT value FROM config WHERE key = 'ats_discovery_last_run'"
    ).fetchone()
    conn.close()

    if row:
        last_run = row[0]
        try:
            dt = datetime.fromisoformat(last_run)
            if datetime.now(dt.tzinfo) - dt < timedelta(days=7):
                return  # already ran this week
        except Exception:
            pass

    _fetch_common_crawl_slugs()
    _fetch_hiring_without_whiteboards()
    _fetch_remoteintech()

    conn = __import__("sqlite3").connect(db.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES ('ats_discovery_last_run', ?)",
        (_now_ist(),)
    )
    conn.commit()
    conn.close()
    print("[ats_discovery] all external sources refreshed")


# ── Common Crawl slug discovery ───────────────────────────────────────────────

_CC_DOMAINS = [
    ("jobs.lever.co", "lever", re.compile(r'co,lever,jobs\)/([a-z0-9_-]+)')),
    ("boards.greenhouse.io", "greenhouse", re.compile(r'io,greenhouse,boards\)/([a-z0-9_-]+)')),
    ("job-boards.greenhouse.io", "greenhouse", re.compile(r'io,greenhouse,job-boards\)/([a-z0-9_-]+)')),
    ("jobs.ashbyhq.com", "ashby", re.compile(r'com,ashbyhq,jobs\)/([a-z0-9_-]+)')),
]

_SKIP_SLUGS = frozenset([
    "api", "static", "css", "js", "fonts", "images", "embed", "inclusion",
    "favicon", "sitemap", "robots", "assets", "_next", "apply", "about",
])


def _get_latest_cc_index() -> str:
    """Get the latest Common Crawl index ID."""
    try:
        resp = requests.get(
            "http://index.commoncrawl.org/collinfo.json",
            timeout=10, headers={"User-Agent": "openclaw/1.0"},
        )
        indices = resp.json()
        if indices:
            return indices[0]["id"]
    except Exception:
        pass
    return "CC-MAIN-2025-08"  # known-good fallback


def _fetch_common_crawl_slugs():
    """
    Query Common Crawl index to discover every company slug across
    Greenhouse, Lever, and Ashby — typically ~3,900 unique companies.
    """
    cc_index = _get_latest_cc_index()
    total_added = 0

    for domain, platform, pattern in _CC_DOMAINS:
        try:
            url = f"http://index.commoncrawl.org/{cc_index}-index"
            resp = requests.get(
                url,
                params={"url": f"{domain}/*", "output": "json", "limit": 50000, "fl": "urlkey"},
                timeout=60, headers={"User-Agent": "openclaw/1.0"},
            )
            slugs = set()
            for line in resp.text.strip().split("\n"):
                if not line:
                    continue
                try:
                    data = __import__("json").loads(line)
                    urlkey = data.get("urlkey", "")
                except Exception:
                    continue
                m = pattern.match(urlkey)
                if m:
                    s = m.group(1)
                    if len(s) >= 2 and s not in _SKIP_SLUGS:
                        slugs.add(s)

            added = 0
            for slug in slugs:
                cid = _uid(platform, slug)
                if not db.ats_company_exists(cid):
                    db.save_ats_company({
                        "id": cid, "platform": platform, "slug": slug,
                        "company_name": slug,
                        "discovered_via": "commoncrawl",
                    })
                    added += 1
            total_added += added
            print(f"[ats_discovery] CC {domain}: {len(slugs)} slugs found, +{added} new")
        except Exception as e:
            print(f"[ats_discovery] CC {domain} failed: {e}")

    print(f"[ats_discovery] Common Crawl total: +{total_added} new companies")


def _fetch_hiring_without_whiteboards():
    """
    poteto/hiring-without-whiteboards has a companies.json with getAJob URLs.
    We extract Greenhouse/Lever/Ashby slugs from those URLs.
    """
    url = "https://raw.githubusercontent.com/poteto/hiring-without-whiteboards/main/data/companies.json"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "openclaw/1.0"})
        companies = resp.json()
        added = 0
        for company in companies:
            get_a_job = company.get("getAJob", "") or ""
            name = company.get("name", "") or ""
            for platform, slug in extract_ats_from_text(get_a_job):
                cid = _uid(platform, slug)
                if not db.ats_company_exists(cid):
                    db.save_ats_company({
                        "id": cid, "platform": platform, "slug": slug,
                        "company_name": name, "discovered_via": "github_hww",
                    })
                    added += 1
        print(f"[ats_discovery] hiring-without-whiteboards: +{added} new companies")
    except Exception as e:
        print(f"[ats_discovery] hiring-without-whiteboards failed: {e}")


def _fetch_remoteintech():
    """
    remoteintech/remote-jobs README.md has company career links inline.
    Extract ATS slugs from those links.
    """
    url = "https://raw.githubusercontent.com/remoteintech/remote-jobs/main/README.md"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "openclaw/1.0"})
        added = 0
        for platform, slug in extract_ats_from_text(resp.text):
            cid = _uid(platform, slug)
            if not db.ats_company_exists(cid):
                db.save_ats_company({
                    "id": cid, "platform": platform, "slug": slug,
                    "company_name": slug, "discovered_via": "github_remoteintech",
                })
                added += 1
        print(f"[ats_discovery] remoteintech: +{added} new companies")
    except Exception as e:
        print(f"[ats_discovery] remoteintech failed: {e}")


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    return BeautifulSoup(html_text, "html.parser").get_text(separator=" ", strip=True)[:2000]


def _parse_date(raw) -> str:
    """Best-effort ISO date string from various timestamp formats."""
    if not raw:
        return ""
    if isinstance(raw, int):
        # Lever uses milliseconds
        try:
            return datetime.utcfromtimestamp(raw / 1000).strftime("%Y-%m-%d")
        except Exception:
            return ""
    if isinstance(raw, str):
        return raw[:10]
    return ""


# ── Async ATS fetchers ────────────────────────────────────────────────────────

HEADERS = {"User-Agent": "openclaw/1.0 (job-hunter-bot)"}


async def _fetch_greenhouse(session: "aiohttp.ClientSession", slug: str, company_name: str) -> list:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            raw_jobs = data.get("jobs", [])
    except Exception:
        return []

    jobs = []
    for j in raw_jobs:
        title = (j.get("title") or "").strip()
        if not title:
            continue
        location_name = (j.get("location") or {}).get("name", "") or ""
        # work_type from location field
        lt = location_name.lower()
        if "hybrid" in lt:
            work_type = "hybrid"
        elif "remote" in lt:
            work_type = "remote"
        elif any(w in lt for w in ["onsite", "on-site", "in-office"]):
            work_type = "onsite"
        else:
            work_type = "unspecified"
        desc = _strip_html(j.get("content", ""))
        job_url = j.get("absolute_url", "") or f"https://boards.greenhouse.io/{slug}/jobs/{j.get('id','')}"
        uid = hashlib.md5(f"gh:{slug}:{j.get('id','')}" .encode()).hexdigest()[:16]
        jobs.append({
            "id": uid, "source": "greenhouse",
            "title": title[:200], "company": company_name or slug,
            "url": job_url, "description": desc,
            "work_type": work_type, "location": location_name[:100],
            "posted_at": _parse_date(j.get("updated_at")),
        })
    return jobs


async def _fetch_lever(session: "aiohttp.ClientSession", slug: str, company_name: str) -> list:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            postings = await resp.json(content_type=None)
            if not isinstance(postings, list):
                return []
    except Exception:
        return []

    jobs = []
    for j in postings:
        title = (j.get("text") or "").strip()
        if not title:
            continue
        cats = j.get("categories") or {}
        # Lever has workplaceType in newer postings; fall back to location/commitment
        wt_raw = (j.get("workplaceType") or cats.get("location", "")).lower()
        if "hybrid" in wt_raw:
            work_type = "hybrid"
        elif "remote" in wt_raw:
            work_type = "remote"
        elif any(w in wt_raw for w in ["onsite", "on-site", "in-office"]):
            work_type = "onsite"
        else:
            work_type = "unspecified"
        commitment = cats.get("commitment", "")
        if commitment.lower() == "internship":
            work_type = work_type  # keep, title filter handles intern titles
        desc = (j.get("descriptionPlain") or _strip_html(j.get("description", "")))[:2000]
        job_url = j.get("hostedUrl", "") or f"https://jobs.lever.co/{slug}/{j.get('id','')}"
        uid = hashlib.md5(f"lv:{slug}:{j.get('id','')}" .encode()).hexdigest()[:16]
        jobs.append({
            "id": uid, "source": "lever",
            "title": title[:200], "company": company_name or slug,
            "url": job_url, "description": desc,
            "work_type": work_type, "location": (cats.get("location", ""))[:100],
            "posted_at": _parse_date(j.get("createdAt")),
        })
    return jobs


async def _fetch_ashby(session: "aiohttp.ClientSession", slug: str, company_name: str) -> list:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            postings = data.get("jobPostings", [])
    except Exception:
        return []

    jobs = []
    for j in postings:
        title = (j.get("title") or "").strip()
        if not title:
            continue
        wt_raw = (j.get("workplaceType") or "").lower()
        is_remote = j.get("isRemote", False)
        if "hybrid" in wt_raw:
            work_type = "hybrid"
        elif is_remote or "remote" in wt_raw:
            work_type = "remote"
        elif any(w in wt_raw for w in ["onsite", "on-site", "onsite"]):
            work_type = "onsite"
        else:
            work_type = "unspecified"
        desc = (j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml", "")))[:2000]
        job_url = j.get("externalLink", "") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id','')}"
        uid = hashlib.md5(f"ab:{slug}:{j.get('id','')}" .encode()).hexdigest()[:16]
        jobs.append({
            "id": uid, "source": "ashby",
            "title": title[:200], "company": company_name or slug,
            "url": job_url, "description": desc,
            "work_type": work_type, "location": (j.get("locationName", ""))[:100],
            "posted_at": _parse_date(j.get("publishedDate")),
        })
    return jobs


async def _fetch_company_jobs(session, company: dict) -> list:
    """Dispatch to the right platform fetcher and update last_fetched."""
    platform = company["platform"]
    slug = company["slug"]
    name = company.get("company_name", slug)

    if platform == "greenhouse":
        jobs = await _fetch_greenhouse(session, slug, name)
    elif platform == "lever":
        jobs = await _fetch_lever(session, slug, name)
    elif platform == "ashby":
        jobs = await _fetch_ashby(session, slug, name)
    else:
        return []

    db.mark_ats_fetched(company["id"], _now_ist())
    return jobs


async def _fetch_all_async(companies: list) -> list:
    connector = aiohttp.TCPConnector(limit=30, limit_per_host=3)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        results = await asyncio.gather(
            *[_fetch_company_jobs(session, c) for c in companies],
            return_exceptions=True,
        )
    jobs = []
    for r in results:
        if isinstance(r, list):
            jobs.extend(r)
    return jobs


# ── Main entry point ──────────────────────────────────────────────────────────

# Max companies to fetch per scrape run. With ~3,900 discovered companies,
# this ensures each run takes ~2-5 minutes instead of 30+. Companies are
# fetched in staleness order (oldest first), so the full list rotates over
# several days.
MAX_COMPANIES_PER_RUN = 500


def refresh_ats_registry(force: bool = False) -> dict:
    """
    Refresh ATS company discovery separately from interactive campaign runs.
    This can be called on a schedule or manually when you want broader coverage.
    """
    if not _AIOHTTP_AVAILABLE:
        return {"refreshed": False, "reason": "aiohttp not installed"}
    db.init_db()
    seed_ats_companies()
    if force:
        conn = __import__("sqlite3").connect(db.DB_PATH)
        conn.execute("DELETE FROM config WHERE key = 'ats_discovery_last_run'")
        conn.commit()
        conn.close()
    before = db.count_ats_companies()
    discover_from_github_lists()
    after = db.count_ats_companies()
    return {"refreshed": True, "before": before, "after": after, "added": max(0, after - before)}


def scrape_ats(
    *,
    refresh_registry: bool = True,
    max_companies: int | None = None,
) -> list:
    """
    Fetch jobs from all active ATS companies.
    Returns a flat list of raw job dicts (not yet filtered or scored).
    """
    if not _AIOHTTP_AVAILABLE:
        print("[ats] aiohttp not installed, skipping ATS scrape")
        return []

    db.init_db()
    seed_ats_companies()
    if refresh_registry:
        discover_from_github_lists()

    companies = db.list_ats_companies(active_only=True)
    if not companies:
        print("[ats] no companies to fetch")
        return []

    company_cap = max_companies or MAX_COMPANIES_PER_RUN
    total = len(companies)
    batch = companies[:company_cap]
    if total > company_cap:
        print(f"[ats] {total} stale companies, fetching batch of {len(batch)} (oldest first)")
    else:
        print(f"[ats] fetching {total} companies in parallel...")

    jobs = asyncio.run(_fetch_all_async(batch))
    print(f"[ats] raw jobs fetched: {len(jobs)} from {len(batch)} companies ({total} total registered)")
    return jobs
