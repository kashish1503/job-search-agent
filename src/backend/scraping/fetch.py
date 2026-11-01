"""Orchestration: dispatch, concurrency, deadlines, health and hydration.

This is the port of JobWatch's ``fetch_all`` / ``fetch_company_result`` pair,
adapted to the job-search-agent's existing data model.

The contract for one company URL is three tiers:

1. a specialized adapter when the URL or company is recognized;
2. JSON-LD / structured data on the page;
3. generic link extraction.

Whatever happens, the result is a ``SourceResult`` with a status and a
completeness verdict, and a failure on one portal never aborts the run.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from . import adapters, feeds, registry
from .config import watch_config
from .lock import RunAlreadyActive, RunLock
from .models import Job, SourceResult

try:
    from .. import db
except ImportError:  # running as a top-level module (scripts, tests)
    import db

IST = timezone(timedelta(hours=5, minutes=30))

# Feeds already ship descriptions, or live behind a login wall we must not hit.
NO_HYDRATE = {"linkedin", "hiring_post", "yc", "remoteok", "remotive", "arbeitnow"}


class _NoAdapter(Exception):
    """Raised when no specialized adapter matches this URL."""


def _log(message: str) -> None:
    print(f"[watch] {message}")


def _run_id() -> str:
    return datetime.now(IST).strftime("%Y%m%dT%H%M%S")


def _blocked_hint(error: str) -> bool:
    lowered = (error or "").lower()
    return any(
        token in lowered
        for token in ("403", "429", "captcha", "robots", "waf challenge", "http 202")
    )


async def _dispatch(client: httpx.AsyncClient, row: dict, cfg: dict):
    """Tier 1: the specialized extractor for this URL shape."""
    url = row["careers_url"]
    company = row["company"]
    kind = (row.get("kind") or "auto").lower()
    path_pattern = row.get("path_pattern") or ""

    if kind == "cards":
        jobs, expected = await adapters.html_cards(
            client, url, company, path_pattern or r"/jobs?/[^/?#]+"
        )
        return jobs, expected, "OfficialHTMLJobCards"
    if kind == "sitemap":
        jobs, expected = await adapters.sitemap(
            client, url, company, path_pattern or r"/careers?/[^/?#]+"
        )
        return jobs, expected, "Sitemap"
    if kind == "next_data":
        jobs, expected = await adapters.next_data(client, url, company)
        return jobs, expected, "EmbeddedJSON"

    platform, slug = adapters.ats_hint(url)
    if platform == "greenhouse":
        jobs, expected = await adapters.greenhouse(client, slug, company)
        return jobs, expected, "GreenhouseAPI"
    if platform == "lever":
        jobs, expected = await adapters.lever(client, slug, company)
        return jobs, expected, "LeverAPI"
    if platform == "ashby":
        jobs, expected = await adapters.ashby(client, slug, company)
        return jobs, expected, "AshbyAPI"
    if platform == "workable":
        jobs, expected = await adapters.workable(client, slug, company)
        return jobs, expected, "WorkableAPI"
    if platform == "smartrecruiters":
        jobs, expected = await adapters.smartrecruiters(client, slug, company)
        return jobs, expected, "SmartRecruitersAPI"
    if platform == "recruitee":
        jobs, expected = await adapters.recruitee(client, slug, company)
        return jobs, expected, "RecruiteeAPI"

    if adapters.is_amazon(url, company):
        jobs, expected = await adapters.amazon_india(client, company)
        return jobs, expected, "AmazonIndiaSearch"
    if adapters.is_google(url, company):
        filter_name = "DeepMind" if company.lower() == "google deepmind" else ""
        jobs, expected = await adapters.google_careers(client, company, company_filter=filter_name)
        return jobs, expected, "GoogleCareers"
    if adapters.is_stripe(url, company):
        jobs, expected = await adapters.stripe(client, company)
        return jobs, expected, "StripeNextData"

    raise _NoAdapter(url)


async def fetch_company_result(
    client: httpx.AsyncClient, row: dict, cfg: dict
) -> SourceResult:
    company = row["company"]
    url = row["careers_url"]
    kind = (row.get("kind") or "auto").lower()
    started = time.perf_counter()
    adapter_error = ""

    try:
        jobs, expected, parser = await _dispatch(client, row, cfg)
        return SourceResult(
            company=company,
            careers_url=url,
            status="working" if jobs else "empty",
            parser=parser,
            jobs=jobs,
            duration_ms=int((time.perf_counter() - started) * 1000),
            expected_jobs=expected,
        )
    except _NoAdapter:
        pass
    except Exception as exc:
        adapter_error = f"{type(exc).__name__}: {exc}"

    # Tier 2 + 3: structured data on the page, then every job-looking link.
    try:
        if kind == "sitemap":
            jobs, expected = await adapters.sitemap(
                client, url, company, row.get("path_pattern") or ""
            )
        elif kind == "cards":
            jobs, expected = await adapters.html_cards(
                client, url, company, row.get("path_pattern") or r"/jobs?/[^/?#]+"
            )
        else:
            jobs, expected = await adapters.generic(client, url, company)
        status = "fallback" if jobs else ("blocked" if _blocked_hint(adapter_error) else "empty")
        return SourceResult(
            company=company,
            careers_url=url,
            status=status,
            parser="generic_html",
            jobs=jobs,
            error=adapter_error,
            duration_ms=int((time.perf_counter() - started) * 1000),
            expected_jobs=expected,
        )
    except Exception as exc:
        error = "; ".join(x for x in (adapter_error, f"{type(exc).__name__}: {exc}") if x)
        status = "blocked" if _blocked_hint(error) else "failed"
        return SourceResult(
            company=company,
            careers_url=url,
            status=status,
            parser="none",
            jobs=[],
            error=error,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )


async def network_preflight(client: httpx.AsyncClient) -> bool:
    """Two or more independent hosts failing means the machine is offline."""
    probes = (
        "https://www.google.com/generate_204",
        "https://api.github.com",
        "https://api.telegram.org",
    )
    failures = 0
    for url in probes:
        try:
            await client.get(url, timeout=8)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            failures += 1
    return failures < 2


async def hydrate_jobs(client: httpx.AsyncClient, jobs: list[Job], cfg: dict) -> None:
    candidates = [job for job in jobs if job.source not in NO_HYDRATE]
    cap = int(cfg.get("hydrate_max_jobs", 400) or 0)
    if cap and len(candidates) > cap:
        _log(f"hydration capped at {cap} of {len(candidates)} jobs")
        candidates = candidates[:cap]
    if not candidates:
        return
    deadline = max(1, int(cfg.get("hydrate_deadline_seconds", 240)))
    try:
        await asyncio.wait_for(
            adapters.hydrate(
                client,
                candidates,
                min_chars=int(cfg.get("hydration_min_chars", 400)),
                concurrency=int(cfg.get("hydrate_concurrency", 8)),
            ),
            timeout=deadline,
        )
    except asyncio.TimeoutError:
        # Detail pages are a nice-to-have; list pages already gave us the jobs.
        _log(f"hydration deadline reached after {deadline}s; keeping short descriptions")


def _feed_tasks(client: httpx.AsyncClient, cfg: dict):
    feeds_cfg = cfg.get("feeds") or {}
    tasks = []

    yc = feeds_cfg.get("yc") or {}
    if yc.get("enabled", True):
        tasks.append(
            (
                asyncio.create_task(feeds.ycombinator(client, yc.get("locations"))),
                "Y Combinator",
                "https://www.ycombinator.com/jobs",
                "YCJobs",
            )
        )

    linkedin = feeds_cfg.get("linkedin") or {}
    if linkedin.get("enabled", True) and linkedin.get("queries"):
        tasks.append(
            (
                asyncio.create_task(feeds.linkedin(client, linkedin)),
                "LinkedIn Jobs (public search)",
                "https://www.linkedin.com/jobs/",
                "LinkedInGuestSearch",
            )
        )

    posts = feeds_cfg.get("hiring_posts") or {}
    if posts.get("enabled") and posts.get("feed_urls"):
        tasks.append(
            (
                asyncio.create_task(
                    feeds.hiring_posts(
                        client,
                        list(posts.get("feed_urls") or []),
                        (cfg.get("_keywords") or []),
                        int(posts.get("max_entries_per_feed", 100)),
                    )
                ),
                "LinkedIn Hiring Posts (public alerts)",
                "Google Alerts RSS",
                "PublicAlertFeed",
            )
        )

    if (feeds_cfg.get("remoteok") or {}).get("enabled", True):
        tasks.append(
            (
                asyncio.create_task(feeds.remoteok(client)),
                "RemoteOK",
                "https://remoteok.com/api",
                "RemoteOKAPI",
            )
        )
    if (feeds_cfg.get("remotive") or {}).get("enabled", True):
        tasks.append(
            (
                asyncio.create_task(feeds.remotive(client)),
                "Remotive",
                "https://remotive.com/api/remote-jobs",
                "RemotiveAPI",
            )
        )
    if (feeds_cfg.get("arbeitnow") or {}).get("enabled", True):
        tasks.append(
            (
                asyncio.create_task(feeds.arbeitnow(client)),
                "Arbeitnow",
                "https://arbeitnow.com/api/job-board-api",
                "ArbeitnowAPI",
            )
        )

    return tasks


async def _collect_feeds(feed_tasks) -> list[SourceResult]:
    results = []
    for task, company, url, parser in feed_tasks:
        try:
            value = await task
            if len(value) == 3:
                jobs, expected, completeness = value
            else:  # feeds that do not override the verdict
                jobs, expected = value
                completeness = "bounded"
            results.append(
                SourceResult(
                    company=company,
                    careers_url=url,
                    status="working" if jobs else "empty",
                    parser=parser,
                    jobs=jobs,
                    expected_jobs=expected,
                    completeness=completeness or "bounded",
                )
            )
        except Exception as exc:
            results.append(
                SourceResult(
                    company=company,
                    careers_url=url,
                    status="failed",
                    parser=parser,
                    jobs=[],
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


async def fetch_all(
    rows: list[dict], cfg: dict, include_feeds: bool = True
) -> tuple[list[Job], list[SourceResult]]:
    concurrency = max(1, int(cfg.get("source_concurrency", 12)))
    company_timeout = max(5, int(cfg.get("company_timeout_seconds", 90)))
    deadline = max(company_timeout, int(cfg.get("fetch_deadline_seconds", 900)))

    limits = httpx.Limits(
        max_connections=max(20, concurrency * 3),
        max_keepalive_connections=max(10, concurrency),
    )
    timeout = httpx.Timeout(30.0, connect=10.0)

    async with httpx.AsyncClient(
        headers=adapters.HTML_HEADERS,
        follow_redirects=True,
        timeout=timeout,
        limits=limits,
    ) as client:
        if not await network_preflight(client):
            return [], [
                SourceResult(
                    company="network",
                    careers_url="",
                    status="failed",
                    parser="preflight",
                    jobs=[],
                    error="network preflight failed: two or more independent hosts unreachable",
                )
            ]

        feed_tasks = _feed_tasks(client, cfg) if include_feeds else []
        if feed_tasks:
            _log(f"started {len(feed_tasks)} discovery feeds")

        semaphore = asyncio.Semaphore(concurrency)
        collected: dict[str, SourceResult] = {}

        async def one(row: dict):
            async with semaphore:
                try:
                    result = await asyncio.wait_for(
                        fetch_company_result(client, row, cfg), timeout=company_timeout
                    )
                except asyncio.TimeoutError:
                    result = SourceResult(
                        company=row.get("company", ""),
                        careers_url=row.get("careers_url", ""),
                        status="failed",
                        parser="timeout",
                        jobs=[],
                        error=f"source exceeded {company_timeout}s deadline",
                    )
                except Exception as exc:
                    result = SourceResult(
                        company=row.get("company", ""),
                        careers_url=row.get("careers_url", ""),
                        status="failed",
                        parser="none",
                        jobs=[],
                        error=f"{type(exc).__name__}: {exc}",
                    )
                collected[row.get("careers_url", "")] = result
                return result

        tasks = [asyncio.create_task(one(row)) for row in rows]
        completed = 0
        try:
            for future in asyncio.as_completed(tasks, timeout=deadline):
                result = await future
                completed += 1
                if completed % 25 == 0 or completed == len(tasks):
                    _log(
                        f"progress {completed}/{len(tasks)} latest={result.company} "
                        f"status={result.status}"
                    )
                elif result.needs_attention:
                    _log(
                        f"attention company={result.company} status={result.status} "
                        f"error={result.error[:160]}"
                    )
        except asyncio.TimeoutError:
            pending = [(task, row) for task, row in zip(tasks, rows) if not task.done()]
            _log(
                f"global deadline reached after {deadline}s; cancelling {len(pending)} "
                f"unfinished sources and keeping {len(collected)} completed results"
            )
            for task, _ in pending:
                task.cancel()
            await asyncio.gather(*(task for task, _ in pending), return_exceptions=True)
            for _, row in pending:
                key = row.get("careers_url", "")
                if key not in collected:
                    collected[key] = SourceResult(
                        company=row.get("company", ""),
                        careers_url=key,
                        status="failed",
                        parser="timeout",
                        jobs=[],
                        error=f"global source deadline reached after {deadline}s",
                    )

        results = list(collected.values())
        if feed_tasks:
            results.extend(await _collect_feeds(feed_tasks))

        jobs = [job for result in results for job in result.jobs]
        if jobs:
            candidates = [job for job in jobs if job.source not in NO_HYDRATE]
            if candidates:
                _log(f"hydrating short descriptions for {len(candidates)} jobs")
                await hydrate_jobs(client, candidates, cfg)

        return jobs, results


def run(
    limit: int | None = None,
    include_feeds: bool = True,
    refresh_registry: bool = True,
) -> dict:
    """Scrape everything and persist source health. Returns jobs + diagnostics."""
    db.init_db()
    search_config = db.get_config()
    cfg = watch_config(search_config)
    cfg["_keywords"] = list(search_config.get("keywords") or [])

    if not cfg.get("enabled", True):
        return {"skipped": "watch scraping disabled", "jobs": [], "sources": []}

    if refresh_registry:
        try:
            try:
                from .. import sources_ats
            except ImportError:  # imported as a top-level module
                import sources_ats

            sources_ats.seed_ats_companies()
        except Exception as exc:  # discovery is a bonus, never a blocker
            _log(f"registry seed skipped: {type(exc).__name__}: {exc}")

    rows = registry.build_rows(cfg, limit=limit)
    _log(f"targets companies={len(rows)} feeds={include_feeds}")
    run_id = _run_id()

    lock_path = Path(db.DB_PATH).parent / "scrape.run.lock"
    try:
        with RunLock(lock_path):
            jobs, results = asyncio.run(fetch_all(rows, cfg, include_feeds=include_feeds))
    except RunAlreadyActive as exc:
        _log(f"run skipped: {exc}")
        return {"skipped": str(exc), "jobs": [], "sources": []}

    unique = list({job.key: job for job in jobs}.values())
    health = db.save_source_health(
        run_id, [result.to_health_row(run_id) for result in results]
    )
    failures = sum(1 for item in health if item.get("status") in ("failed", "blocked"))
    _log(
        f"run={run_id} jobs={len(unique)} sources={len(results)} "
        f"failures={failures} health_rows={len(health)}"
    )
    return {
        "run_id": run_id,
        "jobs": unique,
        "sources": results,
        "health": health,
        "failures": failures,
    }


def scrape_jobs(limit: int | None = None, include_feeds: bool = True) -> list:
    """Entry point for ``scraper.run_scrape``; returns rows ready for ``save_job``."""
    result = run(limit=limit, include_feeds=include_feeds)
    return [job.to_row() for job in result.get("jobs", [])]


def last_health(run_id: str | None = None) -> list:
    return db.list_source_health(run_id)


def health_summary(run_id: str | None = None) -> dict:
    return db.source_health_summary(run_id)
