from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta

try:
    from . import db, llm, scraper
    from .discovery.registry import get_plugins
except ImportError:
    import db, llm, scraper
    from discovery.registry import get_plugins

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_PLUGINS = ["ollama_web", "ats", "hn", "web3", "manual"]

ROLE_FAMILY_ALIASES = {
    "ai_native": [
        "AI Engineer",
        "LLM Engineer",
        "RAG Engineer",
        "Applied AI Engineer",
        "AI Backend Engineer",
    ],
    "fde_solutions": [
        "Forward Deployed Engineer",
        "AI Solutions Engineer",
        "Solutions Engineer",
        "Implementation Engineer",
        "Customer Engineer",
    ],
    "devrel": [
        "Developer Advocate",
        "Developer Relations Engineer",
        "Developer Experience Engineer",
        "Technical Content Engineer",
    ],
    "backend_fullstack": [
        "Backend Engineer",
        "Fullstack Engineer",
        "Software Engineer",
        "Platform Engineer",
        "Developer Tools Engineer",
    ],
    "web3_infra": [
        "Rust Blockchain Engineer",
        "Protocol Engineer",
        "Web3 Backend Engineer",
        "Crypto Infrastructure Engineer",
        "Smart Contract Engineer",
    ],
}

DEFAULT_AVOID_TERMS = [
    "account executive",
    "sales development representative",
    "customer support",
    "customer success manager",
    "support engineer",
    "recruiter",
    "onsite only",
    "staff",
    "principal",
]


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item.strip())
    return output


def _fallback_role_families(prompt: str) -> list[str]:
    text = prompt.lower()
    families = []
    if any(token in text for token in ("ai", "llm", "rag", "langchain", "langgraph", "agent")):
        families.append("ai_native")
    if any(token in text for token in ("forward deployed", "solutions", "implementation", "customer engineer")):
        families.append("fde_solutions")
    if any(token in text for token in ("devrel", "developer advocate", "developer relations", "developer experience")):
        families.append("devrel")
    if any(token in text for token in ("backend", "fullstack", "software engineer", "platform", "infra", "developer tools")):
        families.append("backend_fullstack")
    if any(token in text for token in ("web3", "crypto", "blockchain", "solana", "smart contract", "protocol")):
        families.append("web3_infra")
    return families or ["backend_fullstack", "ai_native"]


def _fallback_plan(user_prompt: str) -> dict:
    role_families = _fallback_role_families(user_prompt)
    aliases = []
    for family in role_families:
        aliases.extend(ROLE_FAMILY_ALIASES.get(family, []))
    aliases = _dedupe_preserve(aliases)[:12]
    locations = ["remote", "india-friendly"] if "india" in user_prompt.lower() else ["remote"]
    queries = []
    for alias in aliases[:8]:
        queries.extend(
            [
                f'"{alias}" remote',
                f'"{alias}" site:jobs.ashbyhq.com',
                f'"{alias}" site:jobs.lever.co',
                f'"{alias}" site:job-boards.greenhouse.io',
            ]
        )
    return {
        "name": " + ".join(family.replace("_", " ").title() for family in role_families[:3]),
        "prompt": user_prompt,
        "role_families": role_families,
        "aliases": aliases,
        "avoid_terms": DEFAULT_AVOID_TERMS,
        "search_queries": _dedupe_preserve(queries)[:18],
        "enabled_plugins": list(DEFAULT_PLUGINS),
        "locations": locations,
        "max_yoe": 5,
        "metadata": {},
    }


def plan_campaign(user_prompt: str, existing_profile: str | None = None) -> dict:
    profile = existing_profile or db.get_profile()
    prompt = f"""Plan a reusable job search campaign.

Candidate profile:
{profile[:1800]}

User intent:
{user_prompt}

Return ONLY valid JSON with:
{{
  "name": "short campaign name",
  "role_families": ["ai_native", "fde_solutions", "devrel", "backend_fullstack", "web3_infra"],
  "aliases": ["Role Title"],
  "avoid_terms": ["avoid phrase"],
  "search_queries": ["search query"],
  "enabled_plugins": ["ollama_web", "ats", "hn", "web3", "manual"],
  "locations": ["remote", "india-friendly"],
  "max_yoe": 5
}}

Rules:
- Prefer remote and India-friendly when relevant.
- Avoid pure sales, support, recruiter, and very senior-only roles when user intent suggests that.
- Generate queries across multiple role families, not just one title.
- Do not perform web searching.
"""
    data = llm.chat_json(prompt, max_tokens=800, task="planner")
    planned = _fallback_plan(user_prompt)
    if isinstance(data, dict):
        for key in ("name", "role_families", "aliases", "avoid_terms", "search_queries", "enabled_plugins", "locations", "max_yoe"):
            if data.get(key):
                planned[key] = data[key]
    planned["prompt"] = user_prompt
    planned["role_families"] = _dedupe_preserve(planned.get("role_families", []))
    planned["aliases"] = _dedupe_preserve(planned.get("aliases", []))
    planned["avoid_terms"] = _dedupe_preserve(planned.get("avoid_terms", []) + DEFAULT_AVOID_TERMS)
    planned["search_queries"] = _dedupe_preserve(planned.get("search_queries", []))[:24]
    planned["enabled_plugins"] = [name for name in planned.get("enabled_plugins", DEFAULT_PLUGINS) if name]
    planned["locations"] = _dedupe_preserve(planned.get("locations", ["remote"]))
    planned["max_yoe"] = int(planned.get("max_yoe", 5) or 5)
    planned["metadata"] = planned.get("metadata", {})
    return planned


def create_campaign(user_prompt: str, existing_profile: str | None = None, overrides: dict | None = None) -> dict:
    planned = plan_campaign(user_prompt, existing_profile=existing_profile)
    if overrides:
        planned.update({k: v for k, v in overrides.items() if v is not None})
    now = _now_ist()
    campaign_id = hashlib.md5(f"{planned['name']}|{planned['prompt']}".encode()).hexdigest()[:16]
    campaign = {
        "id": campaign_id,
        "name": planned["name"],
        "prompt": planned["prompt"],
        "role_families": planned.get("role_families", []),
        "aliases": planned.get("aliases", []),
        "avoid_terms": planned.get("avoid_terms", []),
        "search_queries": planned.get("search_queries", []),
        "enabled_plugins": planned.get("enabled_plugins", DEFAULT_PLUGINS),
        "locations": planned.get("locations", ["remote"]),
        "max_yoe": planned.get("max_yoe", 5),
        "metadata": planned.get("metadata", {}),
        "enabled": 1,
        "created_at": now,
        "updated_at": now,
        "last_run": "",
    }
    db.save_campaign(campaign)
    return db.get_campaign(campaign_id)


def _title_matches_campaign(title: str, campaign: dict) -> bool:
    title_l = (title or "").lower()
    aliases = [alias.lower() for alias in campaign.get("aliases", [])]
    if not aliases:
        return True
    return any(alias in title_l for alias in aliases)


def _is_obvious_reject(title: str, text: str, campaign: dict) -> tuple[bool, list[str]]:
    haystack = f"{title} {text}".lower()
    red_flags = []
    for term in campaign.get("avoid_terms", []):
        if term.lower() in haystack:
            red_flags.append(term.lower())
    if re.search(r"\b(staff|principal|director|vp|head of)\b", haystack) and campaign.get("max_yoe", 5) <= 5:
        red_flags.append("very senior role")
    return bool(red_flags), _dedupe_preserve(red_flags)


def _passes_campaign_filters(job: dict, campaign: dict) -> tuple[bool, list[str]]:
    title = job.get("title", "")
    description = job.get("description", "")
    combined = f"{title} {description}".lower()
    if not _title_matches_campaign(title, campaign) and not any(alias.lower() in combined for alias in campaign.get("aliases", [])):
        return False, ["role mismatch"]
    hard_reject, red_flags = _is_obvious_reject(title, description, campaign)
    if hard_reject:
        return False, red_flags
    work_type = (job.get("work_type") or "").lower()
    if work_type == "onsite":
        return False, ["onsite only"]
    if "onsite" in combined or "in-office" in combined:
        return False, ["onsite only"]
    max_yoe = campaign.get("max_yoe")
    if max_yoe is not None:
        match = re.search(r"(\d+)\s*(?:\+|to|-|–)?\s*\d*\s*years?\s*(?:of\s*)?(?:experience|exp\b)", combined)
        if match and int(match.group(1)) > int(max_yoe):
            return False, [f"requires {match.group(1)} years"]
    return True, []


def _match_role_family(job: dict, campaign: dict) -> str:
    haystack = f"{job.get('title', '')} {job.get('description', '')}".lower()
    for family in campaign.get("role_families", []):
        aliases = ROLE_FAMILY_ALIASES.get(family, [])
        if any(alias.lower() in haystack for alias in aliases):
            return family
    return campaign.get("role_families", ["unknown"])[0] if campaign.get("role_families") else "unknown"


def _score_fit(job: dict, campaign: dict) -> dict:
    candidate_profile = db.get_profile()
    hard_reject, red_flags = _is_obvious_reject(job.get("title", ""), job.get("description", ""), campaign)
    if hard_reject:
        return {
            "score": 0,
            "reason": "rejected by hard filters",
            "fit_band": "reject",
            "matched_role_family": _match_role_family(job, campaign),
            "red_flags": red_flags,
        }

    schema_prompt = f"""Score this job against the candidate and campaign intent.

CANDIDATE:
{candidate_profile}

CAMPAIGN:
Prompt: {campaign.get("prompt", "")}
Role families: {", ".join(campaign.get("role_families", []))}
Avoid: {", ".join(campaign.get("avoid_terms", []))}

JOB:
Title: {job.get("title", "")}
Company: {job.get("company", "")}
Work type: {job.get("work_type", "")}
Location: {job.get("location", "")}
Description: {(job.get("description") or "")[:1600]}

Return ONLY valid JSON:
{{
  "score": 0,
  "reason": "short reason",
  "fit_band": "strong | maybe | weak | reject",
  "matched_role_family": "ai_native | fde_solutions | devrel | backend_fullstack | web3_infra | unknown",
  "red_flags": ["flag"]
}}

Rules:
- Score 0 for onsite-only, pure sales, pure support, or very senior-only mismatch.
- Keep reason under 120 characters.
- Use no markdown.
"""
    data = llm.chat_json(schema_prompt, max_tokens=180, task="score")
    score = int(data.get("score", 0)) if isinstance(data, dict) else 0
    reason = str(data.get("reason", "no reason"))[:120] if isinstance(data, dict) else "no reason"
    fit_band = str(data.get("fit_band", "")) if isinstance(data, dict) else ""
    matched_role_family = str(data.get("matched_role_family", "")) if isinstance(data, dict) else ""
    flags = data.get("red_flags", []) if isinstance(data, dict) else []
    if not fit_band:
        fit_band = "strong" if score >= 85 else "maybe" if score >= 70 else "weak" if score >= 50 else "reject"
    if not matched_role_family:
        matched_role_family = _match_role_family(job, campaign)
    if not isinstance(flags, list):
        flags = []
    return {
        "score": score,
        "reason": reason,
        "fit_band": fit_band,
        "matched_role_family": matched_role_family,
        "red_flags": _dedupe_preserve(flags),
    }


def _materialize_job(discovered: dict) -> dict | None:
    metadata_job = (discovered.get("metadata") or {}).get("job")
    if metadata_job:
        job = dict(metadata_job)
    else:
        fetched = scraper._fetch_job_page(discovered.get("url", ""))
        if not fetched:
            return None
        job = {
            "id": discovered.get("canonical_url", "") and hashlib.md5(discovered["canonical_url"].encode()).hexdigest()[:16],
            "source": discovered.get("source", ""),
            "title": fetched.get("title", ""),
            "company": fetched.get("company", ""),
            "url": discovered.get("url", ""),
            "description": fetched.get("description", discovered.get("snippet", "")),
            "work_type": fetched.get("work_type", "unspecified"),
            "location": fetched.get("location", ""),
            "posted_at": "",
        }
    if not job.get("id"):
        job["id"] = hashlib.md5(discovered.get("canonical_url", discovered.get("url", "")).encode()).hexdigest()[:16]
    if not scraper._looks_like_company(job.get("company", "")):
        better_company = scraper._company_from_title_patterns(discovered.get("title", "") or job.get("title", ""))
        if not better_company:
            better_company = scraper._company_from_domain(discovered.get("url", "") or job.get("url", ""))
        if better_company:
            job["company"] = better_company
    job["original_url"] = discovered.get("original_url", job.get("url", ""))
    job["canonical_url"] = discovered.get("canonical_url", job.get("url", ""))
    job["found_by_plugin"] = discovered.get("source", "")
    job["found_by_query"] = discovered.get("query", "")
    job["fetched_at"] = _now_ist()
    return job


def _save_filtered_job(job: dict, campaign: dict, campaign_id: str, started_at: str, pre_flags: list[str]):
    if not db.job_exists(job["id"]):
        db.save_job(
            {
                **job,
                "score": 0,
                "reason": ", ".join(pre_flags)[:120],
                "status": "filtered",
                "fit_band": "reject",
                "matched_role_family": _match_role_family(job, campaign),
                "red_flags": pre_flags,
                "metadata": {"campaign_id": campaign_id},
                "found_at": started_at,
            }
        )


def _run_plugin(plugin, campaign: dict, plugin_limit: int):
    items = plugin.discover(campaign, limit=plugin_limit)
    return plugin.name, items


def run_discovery_campaign(campaign_id: str, plugin_limit: int = 25) -> dict:
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    started_at = _now_ist()
    run_id = hashlib.md5(f"{campaign_id}:{started_at}".encode()).hexdigest()[:16]
    db.save_campaign_run(
        {
            "id": run_id,
            "campaign_id": campaign_id,
            "status": "in_progress",
            "started_at": started_at,
            "completed_at": "",
            "summary": {"campaign_id": campaign_id, "run_id": run_id, "status": "in_progress"},
        }
    )

    plugin_summary: dict[str, int] = {}
    plugin_errors: dict[str, str] = {}
    discovered = []
    seen = set()
    enabled_plugins = get_plugins(campaign.get("enabled_plugins", DEFAULT_PLUGINS))
    plugin_workers = min(max(len(enabled_plugins), 1), int(os.environ.get("CAMPAIGN_PLUGIN_WORKERS", "6")))

    with concurrent.futures.ThreadPoolExecutor(max_workers=plugin_workers) as executor:
        futures = {
            executor.submit(_run_plugin, plugin, campaign, plugin_limit): plugin.name
            for plugin in enabled_plugins
        }
        for future in concurrent.futures.as_completed(futures):
            plugin_name = futures[future]
            try:
                _, plugin_items = future.result()
                plugin_summary[plugin_name] = len(plugin_items)
                for item in plugin_items:
                    canonical = item.get("canonical_url") or item.get("url")
                    if not canonical or canonical in seen:
                        continue
                    seen.add(canonical)
                    discovered.append(item)
            except Exception as exc:
                plugin_summary[plugin_name] = 0
                plugin_errors[plugin_name] = str(exc)[:240]

    parsed = 0
    new_jobs = 0
    scored = 0
    surfaced = 0

    cfg = db.get_config()
    skip_titles = cfg.get("skip_title_patterns", [])
    threshold = cfg.get("score_threshold", 60)

    materialize_workers = min(max(len(discovered), 1), int(os.environ.get("CAMPAIGN_FETCH_WORKERS", "12")))
    materialized_jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=materialize_workers) as executor:
        futures = {executor.submit(_materialize_job, item): item for item in discovered}
        for future in concurrent.futures.as_completed(futures):
            try:
                job = future.result()
                if job:
                    materialized_jobs.append(job)
            except Exception:
                continue

    candidates_to_score = []
    for job in materialized_jobs:
        parsed += 1

        if not scraper.passes_title_filter(job.get("title", ""), skip_titles):
            continue

        allowed, pre_flags = _passes_campaign_filters(job, campaign)
        if not allowed:
            _save_filtered_job(job, campaign, campaign_id, started_at, pre_flags)
            db.add_campaign_result(campaign_id, run_id, job["id"], job.get("found_by_plugin", ""), job.get("found_by_query", ""), started_at)
            continue

        existing = db.get_job(job["id"])
        if not existing:
            new_jobs += 1
            candidates_to_score.append(job)
        else:
            if scraper._looks_like_company(job.get("company", "")) and not scraper._looks_like_company(existing.get("company", "")):
                db.update_job_company(job["id"], job["company"])
            if existing.get("score", 0) >= threshold:
                surfaced += 1
            db.add_campaign_result(campaign_id, run_id, job["id"], job.get("found_by_plugin", ""), job.get("found_by_query", ""), started_at)

    score_workers = min(max(len(candidates_to_score), 1), int(os.environ.get("CAMPAIGN_SCORE_WORKERS", "4")))
    with concurrent.futures.ThreadPoolExecutor(max_workers=score_workers) as executor:
        futures = {executor.submit(_score_fit, job, campaign): job for job in candidates_to_score}
        for future in concurrent.futures.as_completed(futures):
            job = futures[future]
            try:
                fit = future.result()
            except Exception as exc:
                fit = {
                    "score": 0,
                    "reason": f"score error: {str(exc)[:80]}",
                    "fit_band": "reject",
                    "matched_role_family": _match_role_family(job, campaign),
                    "red_flags": ["scoring failed"],
                }
            scored += 1
            status = "new" if fit["score"] >= threshold else "filtered"
            if fit["score"] >= threshold:
                surfaced += 1
            db.save_job(
                {
                    **job,
                    "score": fit["score"],
                    "reason": fit["reason"],
                    "status": status,
                    "fit_band": fit["fit_band"],
                    "matched_role_family": fit["matched_role_family"],
                    "red_flags": fit["red_flags"],
                    "metadata": {"campaign_id": campaign_id},
                    "found_at": started_at,
                }
            )
            db.add_campaign_result(campaign_id, run_id, job["id"], job.get("found_by_plugin", ""), job.get("found_by_query", ""), started_at)

    summary = {
        "campaign_id": campaign_id,
        "run_id": run_id,
        "raw_links_found": len(discovered),
        "jobs_parsed": parsed,
        "new_jobs": new_jobs,
        "scored": scored,
        "surfaced": surfaced,
        "plugin_summary": plugin_summary,
        "plugin_errors": plugin_errors,
    }
    db.save_campaign_run(
        {
            "id": run_id,
            "campaign_id": campaign_id,
            "status": "completed",
            "started_at": started_at,
            "completed_at": _now_ist(),
            "summary": summary,
        }
    )
    db.touch_campaign_last_run(campaign_id, _now_ist())
    return summary
