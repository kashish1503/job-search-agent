"""Offline verification for the ported scraping layer. No network calls."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="watch-test-"))
os.environ["DB_PATH"] = str(TMP / "jobs.db")

BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
sys.path.insert(0, str(BACKEND))

import db  # noqa: E402
from scraping import adapters, feeds, registry  # noqa: E402
from scraping.config import watch_config  # noqa: E402
from scraping.fetch import fetch_company_result  # noqa: E402
from scraping.lock import RunAlreadyActive, RunLock  # noqa: E402
from scraping.models import Job, SourceResult  # noqa: E402

PASS = []
FAIL = []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  ok  {name}")
    except Exception as exc:
        FAIL.append((name, exc))
        print(f" FAIL {name}: {type(exc).__name__}: {exc}")


class FakeResponse:
    def __init__(self, text="", payload=None, status=200, url="https://example.com/careers"):
        self.text = text
        self._payload = payload
        self.status_code = status
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            return json.loads(self.text)
        return self._payload


class FakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, url, params=None, **kwargs):
        self.calls.append((url, params))
        for key, response in self.routes.items():
            if key in url:
                return response(params or {}) if callable(response) else response
        return FakeResponse(status=404)


# ── 1. JSON-LD ────────────────────────────────────────────────────────────────

LD_HTML = """
<html><body>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"JobPosting","title":"Senior AI Engineer",
  "hiringOrganization":{"name":"Acme"},
  "jobLocation":{"@type":"Place","address":{"addressLocality":"Bengaluru","addressCountry":"IN"}},
  "datePosted":"2026-10-01","url":"https://acme.com/jobs/1?utm_source=x",
  "description":"Build LLM systems.","baseSalary":{"value":{"minValue":10,"maxValue":20,"unitText":"YEAR"}}}
]}
</script>
</body></html>
"""


def test_jsonld():
    jobs = adapters.jsonld_jobs(LD_HTML, "Acme", "https://acme.com/jobs")
    assert len(jobs) == 1, jobs
    job = jobs[0]
    assert job.title == "Senior AI Engineer"
    assert "Bengaluru" in job.location
    assert "10" in job.salary_text
    assert job.to_row()["work_type"] in ("remote", "hybrid", "onsite", "unspecified")


# ── 2. html_cards ─────────────────────────────────────────────────────────────


def test_html_cards():
    html = """
    <html><body><p>We have 2 open positions</p>
    <ul>
      <li><a href="/careers/backend-engineer">Backend Engineer</a>
          <span>Remote, India</span></li>
      <li><a href="/careers/ml-engineer">ML Engineer</a>
          <span>Bengaluru</span></li>
      <li><a href="/about">About us</a></li>
    </ul></body></html>
    """
    client = FakeClient({"careers": FakeResponse(html, url="https://acme.com/careers")})

    async def go():
        return await adapters.html_cards(
            client, "https://acme.com/careers", "Acme", r"/careers/[^/?#]+"
        )

    jobs, declared = asyncio.run(go())
    assert declared == 2, declared
    assert len(jobs) == 2, [j.title for j in jobs]
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].url.startswith("https://acme.com/careers/")
    assert "India" in jobs[0].location


# ── 3. next_data ──────────────────────────────────────────────────────────────


def test_next_data():
    payload = {
        "props": {
            "pageProps": {
                "openings": [
                    {"id": "a1", "title": "Platform Engineer", "location": "Pune"},
                    {"id": "a2", "title": "Data Engineer", "location": "Remote"},
                    {"id": "a3", "title": "QA Engineer", "location": "Noida"},
                ]
            }
        }
    }
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )
    client = FakeClient({"careers": FakeResponse(html, url="https://acme.com/careers")})

    async def go():
        return await adapters.next_data(client, "https://acme.com/careers", "Acme")

    jobs, expected = asyncio.run(go())
    assert expected == 3, expected
    assert len(jobs) == 3
    assert {j.title for j in jobs} == {"Platform Engineer", "Data Engineer", "QA Engineer"}


# ── 4. generic fallback ───────────────────────────────────────────────────────


def test_generic_declares_no_openings():
    html = "<html><body><h1>Careers</h1><p>There are no current openings available.</p></body></html>"
    client = FakeClient({"careers": FakeResponse(html)})

    async def go():
        return await adapters.generic(client, "https://acme.com/careers", "Acme")

    jobs, expected = asyncio.run(go())
    assert jobs == [] and expected == 0


def test_generic_links():
    html = """
    <html><body>
    <a href="/jobs/1">Senior Backend Engineer</a>
    <a href="/jobs/2">Product Designer</a>
    <a href="/about">About</a>
    </body></html>
    """
    client = FakeClient({"careers": FakeResponse(html)})

    async def go():
        return await adapters.generic(client, "https://acme.com/careers", "Acme")

    jobs, _ = asyncio.run(go())
    titles = {j.title for j in jobs}
    assert "Senior Backend Engineer" in titles
    assert "About" not in titles


# ── 5. YC feed ────────────────────────────────────────────────────────────────


def test_yc_feed():
    payload = [
        {
            "id": 1,
            "title": "Founding Engineer",
            "url": "/companies/acme/jobs/abc-founding-engineer",
            "location": "Bengaluru, India",
            "companyName": "Acme",
            "salaryRange": "20-30 LPA",
        },
        {
            "id": 2,
            "title": "US Only Role",
            "url": "/companies/x/jobs/y",
            "location": "Remote (US only)",
            "companyName": "X",
        },
        {
            "id": 3,
            "title": "Remote Engineer",
            "url": "/companies/y/jobs/z",
            "location": "Remote (Worldwide)",
            "companyName": "Y",
        },
    ]
    raw = '{"jobPostings":' + json.dumps(payload) + "}"
    html = "&lt;script&gt;" + raw.replace('"', "&quot;") + "&lt;/script&gt;"
    client = FakeClient({"ycombinator.com/jobs": FakeResponse(html)})

    async def go():
        return await feeds.ycombinator(client, ["India", "Remote"])

    jobs, expected, completeness = asyncio.run(go())
    assert expected == 3, expected
    assert completeness == "bounded"
    titles = {j.title for j in jobs}
    assert "Founding Engineer" in titles
    assert "Remote Engineer" in titles
    assert "US Only Role" not in titles
    assert all(j.url.startswith("https://www.ycombinator.com/companies/") for j in jobs)


# ── 6. remoteok feed ──────────────────────────────────────────────────────────


def test_remoteok():
    payload = [
        {"legal": "header"},
        {
            "id": "9",
            "position": "Backend Engineer",
            "company": "Acme",
            "url": "https://remoteok.com/jobs/9",
            "description": "<p>Build <b>APIs</b></p>",
            "location": "Worldwide",
            "date": "2026-10-01T00:00:00Z",
            "salary_min": 100,
            "salary_max": 200,
        },
    ]
    client = FakeClient({"remoteok.com/api": FakeResponse(payload=payload)})

    async def go():
        return await feeds.remoteok(client)

    jobs, _ = asyncio.run(go())
    assert len(jobs) == 1
    assert jobs[0].description == "Build APIs", repr(jobs[0].description)
    assert jobs[0].remote is True
    assert "USD" in jobs[0].salary_text


# ── 7. hiring-post RSS gates ──────────────────────────────────────────────────

RSS = """<?xml version="1.0"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item>
  <title>We are hiring: AI Engineer</title>
  <link>https://www.linkedin.com/posts/alice_hiring-activity-1</link>
  <description>We are hiring an AI Engineer in Bengaluru. Send your resume.</description>
  <pubDate>Sat, 31 Oct 2026 10:00:00 GMT</pubDate>
</item>
<item>
  <title>We are hiring: AI Engineer</title>
  <link>https://www.linkedin.com/posts/bob_hiring-activity-2</link>
  <description>We are hiring in India. Earn $50 per hour, easy money!</description>
</item>
<item>
  <title>We are hiring: Chef</title>
  <link>https://www.linkedin.com/posts/carol_hiring-activity-3</link>
  <description>We are hiring a chef in Mumbai.</description>
</item>
<item>
  <title>We are hiring: AI Engineer</title>
  <link>https://example.com/not-linkedin</link>
  <description>We are hiring an AI Engineer in India.</description>
</item>
</channel></rss>
"""


def test_hiring_posts():
    jobs = feeds.parse_hiring_post_feed(RSS, "feed-1", ["python"])
    assert len(jobs) == 1, [j.title for j in jobs]
    assert jobs[0].source == "hiring_post"
    assert jobs[0].raw["trust"] == "unverified"


# ── 8. completeness verdicts ──────────────────────────────────────────────────


def test_completeness():
    verified = SourceResult("A", "u", "working", "GreenhouseAPI", jobs=[Job("g", "1", "A", "T", "u")], expected_jobs=1)
    assert verified.completeness == "verified" and verified.coverage_ratio == 1.0

    partial = SourceResult("A", "u", "working", "GreenhouseAPI", jobs=[Job("g", "1", "A", "T", "u")], expected_jobs=4)
    assert partial.completeness == "partial" and partial.needs_attention

    bounded = SourceResult("A", "u", "working", "YCJobs", jobs=[Job("yc", "1", "A", "T", "u")], expected_jobs=10, completeness="bounded")
    assert bounded.completeness == "bounded" and not bounded.needs_attention

    structured = SourceResult("A", "u", "working", "LeverAPI", jobs=[Job("l", "1", "A", "T", "u")])
    assert structured.completeness == "structured"

    failed = SourceResult("A", "u", "failed", "generic_html", jobs=[], error="boom")
    assert failed.completeness == "unverified" and failed.needs_attention


# ── 9. Job row shape ──────────────────────────────────────────────────────────


def test_job_row():
    job = Job(
        source="greenhouse",
        source_job_id="42",
        company="Acme",
        title="Backend Engineer",
        url="https://boards.greenhouse.io/acme/jobs/42?utm_source=x&gh_jid=42",
        location="Remote - India",
        posted_at="2026-10-01T12:00:00Z",
        row_id=adapters.md5_uid("gh:acme:42"),
    )
    row = job.to_row()
    required = {"id", "source", "title", "company", "url", "description", "work_type", "location", "posted_at"}
    assert required <= set(row), required - set(row)
    assert row["id"] == adapters.md5_uid("gh:acme:42")
    assert "utm_source" not in row["url"] and "gh_jid" not in row["url"]
    assert row["posted_at"] == "2026-10-01"
    assert row["work_type"] == "remote"
    assert row["metadata"]["content_hash"] == job.content_hash


def test_ats_ids_match_legacy():
    import hashlib

    legacy = hashlib.md5("gh:acme:42".encode()).hexdigest()[:16]
    assert adapters.md5_uid("gh:acme:42") == legacy
    assert adapters.md5_uid("lv:acme:x") == hashlib.md5("lv:acme:x".encode()).hexdigest()[:16]
    assert adapters.md5_uid("ab:acme:y") == hashlib.md5("ab:acme:y".encode()).hexdigest()[:16]


# ── 10. dispatcher tiers ──────────────────────────────────────────────────────


def test_dispatch_greenhouse():
    payload = {"jobs": [{"id": 7, "title": "SWE", "absolute_url": "https://boards.greenhouse.io/acme/jobs/7", "location": {"name": "Remote"}}]}
    client = FakeClient({"boards-api.greenhouse.io": FakeResponse(payload=payload)})
    row = {"company": "Acme", "careers_url": "https://job-boards.greenhouse.io/acme", "kind": "auto"}

    result = asyncio.run(fetch_company_result(client, row, watch_config({})))
    assert result.status == "working", result
    assert result.parser == "GreenhouseAPI"
    assert result.jobs[0].row_id == adapters.md5_uid("gh:acme:7")


def test_dispatch_falls_back():
    # Adapter is recognised (greenhouse) but its API 404s; the HTML page has JSON-LD.
    client = FakeClient({
        "boards-api.greenhouse.io": FakeResponse(status=404),
        "job-boards.greenhouse.io": FakeResponse(LD_HTML, url="https://job-boards.greenhouse.io/acme"),
    })
    row = {"company": "Acme", "careers_url": "https://job-boards.greenhouse.io/acme", "kind": "auto"}

    result = asyncio.run(fetch_company_result(client, row, watch_config({})))
    assert result.status == "fallback", result
    assert result.parser == "generic_html"
    assert len(result.jobs) == 1
    assert "404" in result.error or "HTTP" in result.error


def test_dispatch_blocked():
    client = FakeClient({"acme.com": FakeResponse(status=403)})
    row = {"company": "Acme", "careers_url": "https://acme.com/careers", "kind": "auto"}

    result = asyncio.run(fetch_company_result(client, row, watch_config({})))
    assert result.status == "blocked", result
    assert result.jobs == []


def test_collect_feed_shapes():
    from scraping.fetch import _collect_feeds

    async def two_tuple():
        return [Job("remoteok", "1", "Acme", "Backend", "https://x/1")], None

    async def three_tuple():
        return [Job("yc", "2", "Acme", "Frontend", "https://x/2")], 10, "bounded"

    async def broken():
        raise RuntimeError("feed down")

    async def go():
        return await _collect_feeds([
            (asyncio.create_task(two_tuple()), "RemoteOK", "https://remoteok.com/api", "RemoteOKAPI"),
            (asyncio.create_task(three_tuple()), "Y Combinator", "https://yc.com", "YCJobs"),
            (asyncio.create_task(broken()), "Broken", "https://b.com", "BadFeed"),
        ])

    results = asyncio.run(go())
    by_company = {r.company: r for r in results}
    assert by_company["RemoteOK"].status == "working"
    assert by_company["RemoteOK"].completeness == "bounded"
    assert by_company["Y Combinator"].completeness == "bounded"
    assert by_company["Broken"].status == "failed"
    assert "feed down" in by_company["Broken"].error


def test_hydration_cap():
    from scraping.fetch import hydrate_jobs

    jobs = [
        Job("sitemap", str(i), "Acme", "Engineer", f"https://acme.com/j/{i}")
        for i in range(3)
    ]
    client = FakeClient({
        "acme.com": FakeResponse("<html><body><main>Full description text</main></body></html>")
    })
    cfg = watch_config({"watch": {"hydrate_max_jobs": 1}})
    asyncio.run(hydrate_jobs(client, jobs, cfg))
    assert len(client.calls) == 1, client.calls
    assert jobs[0].description.startswith("Full description")
    assert jobs[1].description == ""


# ── 11. config, registry, lock, db ────────────────────────────────────────────


def test_config_merge():
    cfg = watch_config({"keywords": ["python"], "watch": {"max_companies_per_run": 5, "feeds": {"yc": {"enabled": False}}}})
    assert cfg["max_companies_per_run"] == 5
    assert cfg["feeds"]["yc"]["enabled"] is False
    assert cfg["feeds"]["remoteok"]["enabled"] is True  # untouched default survives

    # Mutating one result must not leak into the next call's defaults.
    cfg["feeds"]["remoteok"]["enabled"] = False
    again = watch_config({})
    assert again["feeds"]["remoteok"]["enabled"] is True


def test_registry_extra_urls():
    db.init_db()
    cfg = watch_config({"watch": {"extra_company_urls": [{"url": "https://acme.com/careers"}], "max_companies_per_run": 10}})
    rows = registry.build_rows(cfg, limit=10)
    extras = [r for r in rows if r["careers_url"] == "https://acme.com/careers"]
    assert len(extras) == 1
    assert extras[0]["company"] == "Acme"


def test_lock():
    path = TMP / "run.lock"
    with RunLock(path):
        try:
            with RunLock(path):
                raise AssertionError("second lock should fail")
        except RunAlreadyActive:
            pass
    with RunLock(path):
        pass  # released correctly


def test_db_health():
    db.init_db()
    rows = [
        {"company": "Acme", "careers_url": "https://acme.com", "status": "working",
         "parser": "GreenhouseAPI", "jobs_found": 12, "duration_ms": 100, "error": "",
         "expected_jobs": 12, "coverage_ratio": 1.0, "completeness": "verified"},
        {"company": "Broken", "careers_url": "https://broken.com", "status": "failed",
         "parser": "none", "jobs_found": 0, "duration_ms": 50, "error": "boom",
         "expected_jobs": None, "coverage_ratio": None, "completeness": "unverified"},
    ]
    saved = db.save_source_health("run1", rows)
    assert len(saved) == 2
    # Second run drops Acme from 12 to 2 -> suspicious_drop
    db.save_source_health("run2", [
        {"company": "Acme", "careers_url": "https://acme.com", "status": "working",
         "parser": "GreenhouseAPI", "jobs_found": 2, "duration_ms": 90, "error": "",
         "expected_jobs": None, "coverage_ratio": None, "completeness": "structured"},
    ])
    latest = db.list_source_health()
    acme = [r for r in latest if r["company"] == "Acme"][0]
    assert acme["completeness"] == "suspicious_drop", acme
    summary = db.source_health_summary()
    assert summary["run_id"] == "run2"
    assert summary["sources"] == 1
    assert db.latest_source_health_run() == "run2"


for name, fn in list(globals().items()):
    if name.startswith("test_") and callable(fn):
        check(name, fn)

print()
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for name, exc in FAIL:
        print(f"  {name}: {type(exc).__name__}: {exc}")
    sys.exit(1)
