# Scraping layer (`watch` source)

A port of the JobWatch crawler's scraping mechanism, added as a new source next
to the existing ATS, jobstash, HN and DDG fetchers. Nothing in the old path was
removed; `scraper.run_scrape()` now accepts `"watch"` in its `sources` list and
includes it by default.

## Three-tier dispatch

Each target is a careers URL. For every URL the layer tries, in order:

| Tier | What happens | Code |
| --- | --- | --- |
| 1 | Specialized adapter for a recognised portal | `scraping/adapters.py` (`greenhouse`, `lever`, `ashby`, `workable`, `smartrecruiters`, `recruitee`, `amazon_india`, `google_careers`, `stripe`, `next_data`) |
| 2 | Structured data embedded in the page (JSON-LD, `__NEXT_DATA__`, sitemap) | `adapters.jsonld_jobs`, `adapters.next_data`, `adapters.sitemap` |
| 3 | Generic job-looking links, last resort | `adapters.generic` |

`scraping/fetch.py::_dispatch` picks tier 1. If it raises `_NoAdapter`, or the
adapter fails, `fetch_company_result` falls through to tier 2/3 and records the
adapter error. A broken portal never aborts the run.

## Per-source status and completeness

Every URL produces a `SourceResult` (`scraping/models.py`) and one row in the
new `source_health` table:

| Field | Meaning |
| --- | --- |
| `status` | `working`, `empty`, `fallback`, `blocked`, `failed` |
| `parser` | which adapter handled it (`LeverAPI`, `generic_html`, …) |
| `expected_jobs` | the total the portal itself declared, if any |
| `coverage_ratio` | `jobs_found / expected_jobs` |
| `completeness` | `verified`, `structured`, `bounded`, `bounded_partial`, `partial`, `unverified`, `suspicious_drop` |

`suspicious_drop` is set in `db.save_source_health` when a source previously
returned ≥10 jobs and now returns <50% without being `failed`/`blocked`. This is
what distinguishes "the company has no openings" from "we stopped being able to
read the company".

## Concurrency and deadlines

`fetch_all` sets a global `httpx.AsyncClient`, a semaphore of
`source_concurrency` (default 12), a per-company timeout (default 90s) and a
global deadline (default 900s). Past the deadline, unfinished tasks are
cancelled and recorded as `failed / timeout` instead of being lost.

A network preflight checks three independent hosts; two connection failures
return a single `network / failed` row and skip the run.

## JD hydration

Adapters return list-view rows with short descriptions. After collection,
`hydrate_jobs` fetches detail pages only for jobs under `hydration_min_chars`
(default 400), with its own concurrency limit. Hydration is capped
(`hydrate_max_jobs`, default 400) and bounded by `hydrate_deadline_seconds`
(default 240s), so a slow portal cannot hold the run open. Feeds that already
ship full descriptions (LinkedIn, YC, RemoteOK, Remotive, Arbeitnow, hiring
posts) are skipped.

## Discovery feeds

| Feed | Module | Notes |
| --- | --- | --- |
| Y Combinator | `feeds.ycombinator` | Parses the `jobPostings` JSON embedded in the jobs page; filters by location |
| LinkedIn guest search | `feeds.linkedin` | Public `jobs-guest` endpoint, bounded pagination and delay; 429/999 degrades to `bounded_partial` |
| Hiring posts | `feeds.hiring_posts` | Google Alerts RSS pointing at public LinkedIn posts, with role/location/spam gates |
| RemoteOK / Remotive / Arbeitnow | `feeds.remoteok`, `remotive`, `arbeitnow` | Public JSON APIs |

All feeds declare `bounded` completeness, so a short feed is not reported as a
broken source.

## Company targets

`scraping/registry.py` reuses the existing `ats_companies` table
(`platform` + `slug` → careers URL) and adds any `extra_company_urls` from
config. Rotation is tracked via `source_health`, so the legacy `ats` fetcher's
`last_fetched` column is untouched.

Greenhouse/Lever/Ashby rows use the same ids as `sources_ats`:

```
md5("gh:{slug}:{id}")[:16]   md5("lv:{slug}:{id}")[:16]   md5("ab:{slug}:{id}")[:16]
```

`run_scrape` dedupes `raw` by `id` before scoring, so running both sources
cannot score the same job twice.

## Configuration

Read from the existing `config.search` JSON blob under a `watch` key, with
defaults in `scraping/config.py`:

```json
{
  "watch": {
    "enabled": true,
    "max_companies_per_run": 300,
    "source_concurrency": 12,
    "company_timeout_seconds": 90,
    "fetch_deadline_seconds": 900,
    "hydrate_max_jobs": 400,
    "hydrate_deadline_seconds": 240,
    "extra_company_urls": [
      {"company": "Acme", "url": "https://acme.com/careers", "kind": "cards",
       "path_pattern": "/careers/[^/?#]+"}
    ],
    "feeds": {
      "yc": {"enabled": true, "locations": ["India", "Remote"]},
      "linkedin": {"enabled": true, "queries": ["ai engineer", "backend engineer"]},
      "remoteok": {"enabled": true},
      "remotive": {"enabled": true},
      "arbeitnow": {"enabled": true}
    }
  }
}
```

Environment overrides:

| Variable | Effect |
| --- | --- |
| `WATCH_ENABLED` | `false` disables the source even if selected |
| `WATCH_MAX_COMPANIES` | cap on companies per run |
| `WATCH_SOURCE_CONCURRENCY` | parallel portal fetches |
| `HIRING_POST_FEED_URLS` | comma/semicolon separated RSS URLs, enables hiring posts |
| `WATCH_MAX_COMPANIES_PER_CAMPAIGN` | cap used by the `watch` discovery plugin |
| `WATCH_CAMPAIGN_FEEDS` | `1` also runs public feeds inside a campaign |

`extra_company_urls[].kind` is `auto` (default), `cards`, `sitemap` or
`next_data`.

## API

`GET /api/source-health?run_id=&limit=` returns:

```json
{
  "summary": {"sources": 42, "working": 30, "empty": 5, "failed": 2, "verified": 18, "...": "..."},
  "sources": [{"company": "Acme", "status": "working", "completeness": "verified", "jobs_found": 12}],
  "attention": [{"company": "Broken", "status": "failed", "error": "HTTP 403"}]
}
```

Omit `run_id` for the latest run. `attention` is the short list worth acting on.

`GET /api/scrape/status` is unchanged; the watch source logs its health summary
into the scrape output as well.

## Files

```text
src/backend/scraping/
  __init__.py     public entry points (scrape_jobs, run, last_health)
  models.py       Job, SourceResult, completeness rules
  adapters.py     tier 1-3 extractors and hydration
  feeds.py        YC, LinkedIn, hiring posts, remote-job APIs
  registry.py     ats_companies + extra URLs -> targets
  config.py       defaults, merge, env overrides
  fetch.py        dispatch, concurrency, deadlines, health persistence
  lock.py         non-blocking run lock
src/backend/discovery/watch.py   "watch" campaign plugin
src/backend/db.py                source_health table + queries
tests/verify_scraping_offline.py offline verification (no network)
```

## Verification

```bash
python tests/verify_scraping_offline.py
```

Covers JSON-LD, HTML cards, `__NEXT_DATA__`, generic fallback, YC payload
parsing, RSS spam gates, completeness verdicts, ATS id compatibility, all three
dispatch tiers, config merge, lock contention and health persistence.
