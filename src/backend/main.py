"""
OpenClaw — FastAPI backend
Run: uvicorn src.backend.main:app --reload --port 8000
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Load .env from the project root (works both locally and in Docker if you
# mount a .env file). override=False means real env vars take precedence.
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=False)

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add src/backend to path so imports work
sys.path.insert(0, str(Path(__file__).parent))
import db
import scraper as scraper_mod
import tailor as tailor_mod
import llm
import outreach as outreach_mod
import campaigns as campaigns_mod
import sources_ats as sources_ats_mod

from apscheduler.schedulers.asyncio import AsyncIOScheduler

IST = timezone(timedelta(hours=5, minutes=30))
candidate_interview_kb = """
Resume/Job Application Questions



Our mission is to accelerate the world’s transition to an open and secure financial system. Could you please tell me how you identify with that mission?*
I got into security because I believe web3 only works if it's actually secure. Too many protocols launch with preventable vulnerabilities that cost users millions. I want to be part of the infrastructure and the team that makes it harder for developers to make those mistakes. An open financial system means nothing if the code underneath is a liability. That's where I want to contribute. Security isn't just a feature but the need of the hour for any blockchain/ web3 protocols to be viable long term. 


How would you describe your knowledge of smart contract security?*

I’ve participated in public contests and  private audits at Nethermind, Shieldify, and GuildAudits. I originally started with Solidity as my main language, but went through Rektoff's Rust bootcamp which opened up Solana auditing for me. From there I picked up Soroban.
At Nethermind, I worked on re-staking protocols, bridges, governance modules, AA paymasters, oracle systems, vaults, etc, across Solidity and Cairo. At Shieldify, I audited GameFi and LP protocols. With Guild Audits, I reviewed NFT protocols. On Code4rena, I've participated in multiple contests covering oracles, token vesting, marketplaces, etc.
I've also worked on Solana through the MetaLend engagement, which gave me hands-on experience with Rust-based smart contracts and their specific failure modes. That experience translates directly to understanding Soroban, which I've audited in public contests.


What's the most interesting smart contract vulnerability you've discovered or encountered in your work?*

Here are my most notable findings from private and public audits
—-
I audited this in a public contest where the oracle’s price update model was built as a massive, monolithic transaction that forces all 1,000 asset prices into a single payload. This design creates a huge 48KB update that consumes nearly 40% of Stellar’s transaction and ledger limits, making it incredibly expensive and risky during network congestion. Because the contract processes everything at once instead of just the assets that changed, it faces a high risk of being deprioritized or rejected during gas price surges, which would stop the oracle from updating and leave integrated protocols with stale data.
—-
I found this in a private audit, the game creation function initialized the game state using the full, original bet amount instead of the net amount left over after fees were deducted. Since the liquidity pool only received the remaining funds but the payout logic calculated winnings based on the larger gross figure, the contract would overpay users and lead to insolvency.
—-
Another one, in the same audit, where the claim function trusted a user-provided token address instead of validating it against the original token or using the token address from the pool, that was used to create the game. Because the contract uses this arbitrary input to select which liquidity pool to pay out from, a player can claim by swapping a low-value asset with high-value asset like WETH and claim any token of their liking from the pool.

How do you use AI in your personal and professional life? *

Professionally, I use AI to understand new codebases faster, ideate and brainstorm attack vectors, spin up proof of concepts to verify if something is actually exploitable before I spend hours on it. It cuts down the time I actually spend manually writing POCs and verifying claims.
Personal side is different. I use it kind of like a Life coach and accountability partner for fitness and health related stuff. I dropped about 14 kilos over the past year, not entirely because of AI but it played a solid role in helping me think through and make myself accountable for my actions. No AI fitness apps, purely stuff like ChatGPT etc


—



Tell us about a something you have you have built that had to handle significant scale or complexity. What was the architecture and what trade-offs did you make?

I recently engineered an automated execution engine designed to process real-time predictive data streams and trigger complex system actions asynchronously. The system's primary complexity stemmed from the need for a delegated permission model, allowing an autonomous agentic layer to execute high-stakes operations on behalf of users without requiring manual intervention for every transaction.

Orchestration layer built with TS and LangGraph that utilized real time price predictive data for decision making.

Due to the failure in contractor's core functioning API, I architected a low level payload generator from ground up. This involved construction of complex hex payloads, and cryptographic signatures to ensure the blockchain virtual machine accepted the agent's decision for trades.
The core architectural tradeoffs we made were making the smart contracts related to the product, protocol agnostic, so it had to depend on the correct execution payload that I mentioned above since, the smart contract itself had no guardrails and relied on the backend supplied hex calldata. This was done so the contractor organization saved thousands of dollars on security audits, since only the initial protocol agnostic vault would have to be audited for security instead of all the new modules


Describe a time you had to debug a production issue across multiple services or layers of a distributed system. How did you approach it and what was the outcome?

While working as a Developer and Solutions Engineer at BuildBear, I wore hats for multiple roles, including those of helping our clients to unblock the issues that caused hindrances in their development cycle. Our client reported a critical blocker for Uniswap V2 (Automated Market Maker) which they were closely building with, and simulating its mainnet states with BuildBear (BuildBear in a nutshell, provided mainnet forks in sandbox environment so clients can deploy their dApps and predict their product's working closely). 
The mainnet has real liquidity and money flowing in and out of contracts and some contracts (protocols) block these features of receiving funds directly in their contract, so the client wanted to manipulate the liquidity (to simulate mainnet price movements) on the sandbox state to be able to continue their development cycle. But the protocol, product worked with would reject token transfers unless they came from a whitelisted source.
I was assigned to work on providing a solution to the client.
Firstly, I confirmed if it was an issue on BuildBear's end, once that was confirmed then, I dug deeper into client's report of constant tx reverts, which revealed the issue above.
Once I pin-point the issue, I researched and developed a work around, that would help client, unblock their issue. The solution was a intermediate contract that would receive the funds and then self-destruct (self destruct in ethereum virtual machine is a way of force feeding contract balances), this helped them burn and mint new liquidity showcasing price movements that projected mainnet's state. I tested this solution extensively on BuildBear and baked the bytecode into the solution itself so the client need only run the script on their part to interact with BuildBear and sync mainnet state for their contracts to work


What aspects of the cryptocurrency industry appeal to you, and how do they align with your career goals?*

The most appealing aspect of cryptocurrency is the shift from traditional assets as well as speculative assets to foundational utility of crypto assets. We are currently in the infrastructural development era of blockchain, where the success of users depends entirely on the rigidity in infrastructure and abstraction of the developer experience. My aim is to serve as a force multiplier for builders by creating high performance tooling that makes on chain integration as seamless as traditional web services. If I get a chance to work at Alchemy I won't be starting from zero, I will actually be continuing my contribution to developer experience and community tooling from BuildBear, where I worked at Web3 Solutions Engineer


What aspects of startup culture resonate with you, and how do you believe they align with your working style?*

I thrive in startup environments because they prioritize impact over optics and provide the autonomy to solve problems at their root. For example during my term at BuildBear even though my title said Solutions Engineer I wore multiple hats from tester, QA Engineer, to DevRel and Developer. It's a great thing because I got to learn a lot about the company and product much more than I would have just working on my role. This autonomy and freedom is what I value the most in a startup culture


— What excites you about joining LiFi?Joining LI.FI is an exciting prospect because it represents the logical next step in my journey of mastering cross-chain infrastructure and automated deployment at scale. Having previously spearheaded the LI.FI bridge plugin for protocol teams while at BuildBear Labs, I have witnessed the complexity that LiFi extracts from the users firsthand. Furthermore I have been using jumper.xyz (jumper.exchange) for my decentralized portfolio and I am yet to find a better tool to do so. Having said that, something I use daily and getting a chance to build it excites me the mostWhat is your experience dealing with integrators?In my recent Solutions Engineering and DevRel role for BuildBear Labs, I served as the technical bridge for external teams integrating our protocols into their applications. I have experience working with Batua (by Pimlico), Across Bridge, LIFI, Chainlink, Uniswap, GMX , Simbolik, Sentio, etc as they were custom plugin for BuildBear particularly, they wouldn't work out of the box with foundry/wagmi frontends.
So I served as technical go-to for integrations and partner solutions around these products and their plugins 
You can check the starter tutorials for these plugins here:
https://www.buildbear.io/docs/tutorials

—-

I’ve worked as Technical writer and Solutions engineer at BuildBear labs, and my primary focus was to find ways to integrate Buildbear into products for companies and clients. So I have experience writing technical documentation as well developing MVPs and POCs from ground up. My most notable write ups and the most impactful ones were Across Bridge and LiFi tutorial, praised by Philipp Zentner himself (https://x.com/_buildbear/status/1915201523832750202?s=46) and drove partnership opportunity for BuildBear as well
Apart from that I have been working as a Web3 Security Researcher for almost a year now and I’ve done several audits with Nethermind, Kann Audits, Shieldify, RadCipher, GuildAudits.
My technical writing experience from BuildBear is further enhanced by security research and I’ve developed a knack for learning and research like never before and it keeps on improving. All of these translate to secure development and solutions engineering for clients

"""


# In-memory scrape state
_scrape_state = {"running": False, "last_result": None, "last_run": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    outreach_mod.init_outreach_tables()
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(_scheduled_scrape, trigger="cron", hour=8, minute=0)
    scheduler.add_job(_poll_batches_bg, trigger="interval", minutes=5, id="batch_poll")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="OpenClaw", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _scheduled_scrape():
    await _run_scrape_bg(None)


async def _run_scrape_bg(sources):
    _scrape_state["running"] = True
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: scraper_mod.run_scrape(sources)
        )
        _scrape_state["last_result"] = result
        _scrape_state["last_run"] = datetime.now(IST).isoformat()
    finally:
        _scrape_state["running"] = False


async def _poll_batches_bg():
    """Called every 5 min by scheduler to check pending LLM batches."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scraper_mod.poll_pending_batches)


# ── Pydantic models ───────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str


class ScrapeRequest(BaseModel):
    sources: Optional[list] = None


class TailorRequest(BaseModel):
    job_id: Optional[str] = None
    url: Optional[str] = None
    raw_jd: Optional[str] = None
    variant_name: Optional[str] = ""
    force: bool = False


class JournalEntry(BaseModel):
    entry: str


class CampaignCreateRequest(BaseModel):
    prompt: str
    name: Optional[str] = None
    enabled_plugins: Optional[list[str]] = None
    max_yoe: Optional[int] = None
    locations: Optional[list[str]] = None


class DiscoveryRunRequest(BaseModel):
    prompt: str
    enabled_plugins: Optional[list[str]] = None


class ATSRefreshRequest(BaseModel):
    force: bool = False


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def get_jobs(status: str = "new", limit: int = 20, offset: int = 0):
    jobs = db.list_jobs(status=status, limit=limit, offset=offset)
    total = db.count_jobs(status=status)
    return {"jobs": jobs, "total": total}


@app.get("/api/jobs/all")
def get_all_jobs(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
    status: Optional[str] = None,
):
    jobs = db.list_all_jobs(limit=limit, offset=offset, source=source, status=status)
    total = db.count_all_jobs(source=source, status=status)
    return {"jobs": jobs, "total": total}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/status")
def update_job_status(job_id: str, body: StatusUpdate):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    allowed = {"applied", "skipped", "new", "tailored"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    db.set_status(job_id, body.status)
    return {"ok": True}


# ── Scrape ────────────────────────────────────────────────────────────────────

@app.post("/api/scrape")
async def start_scrape(body: ScrapeRequest, background_tasks: BackgroundTasks):
    if _scrape_state["running"]:
        return {"status": "already_running"}
    background_tasks.add_task(_run_scrape_bg, body.sources)
    return {"status": "started"}


@app.get("/api/scrape/status")
def scrape_status():
    return {
        "running": _scrape_state["running"],
        "last_result": _scrape_state["last_result"],
        "last_run": _scrape_state["last_run"],
    }


# ── Batches ───────────────────────────────────────────────────────────────────

@app.get("/api/batches")
def list_batches():
    pending = db.get_pending_batches()
    return {"pending": pending, "count": len(pending)}


@app.post("/api/batches/poll")
async def poll_batches(background_tasks: BackgroundTasks):
    """Trigger immediate batch polling (also runs every 5 min automatically)."""
    background_tasks.add_task(_poll_batches_bg)
    return {"status": "polling"}


# ── Tailor ────────────────────────────────────────────────────────────────────

@app.post("/api/tailor")
def run_tailor(body: TailorRequest):
    if not body.job_id and not body.url and not body.raw_jd:
        raise HTTPException(status_code=400, detail="Provide job_id, url, or raw_jd")
    result = tailor_mod.tailor(
        job_id=body.job_id,
        url=body.url,
        raw_jd=body.raw_jd,
        variant_name=body.variant_name or "",
        force=body.force,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


# ── Resume editor ────────────────────────────────────────────────────────────

class ResumeEditRequest(BaseModel):
    instructions: str
    variant_name: Optional[str] = ""


@app.post("/api/resume/edit")
def resume_edit(body: ResumeEditRequest):
    if not body.instructions.strip():
        raise HTTPException(status_code=400, detail="instructions must not be empty")
    result = tailor_mod.apply_edits(
        instructions=body.instructions,
        variant_name=body.variant_name or "",
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


# ── Variants ──────────────────────────────────────────────────────────────────

class RefineRequest(BaseModel):
    feedback: str


@app.post("/api/variants/{variant_id}/refine")
def refine_variant(variant_id: str, body: RefineRequest):
    if not body.feedback.strip():
        raise HTTPException(status_code=400, detail="feedback must not be empty")
    result = tailor_mod.refine_variant(variant_id, body.feedback)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@app.get("/api/variants")
def list_variants():
    return {"variants": db.list_variants(limit=50)}


@app.get("/api/variants/{variant_id}/zip")
def get_variant_zip(variant_id: str):
    variant = db.get_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    zip_path = variant.get("zip_path", "")
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Zip file not found")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=os.path.basename(zip_path),
    )


@app.get("/api/variants/{variant_id}/pdf")
def get_variant_pdf(variant_id: str):
    variant = db.get_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    pdf_path = variant.get("pdf_path", "")
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found or not compiled")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path),
    )


# ── Funded companies ──────────────────────────────────────────────────────────

@app.get("/api/funded")
def get_funded(limit: int = 20):
    return {"companies": db.list_funded(limit=limit)}


# ── Journal ───────────────────────────────────────────────────────────────────

@app.get("/api/journal")
def get_journal(limit: int = 30, offset: int = 0):
    entries = db.get_journal_entries(limit=limit, offset=offset)
    return {"entries": entries}


@app.post("/api/journal")
def add_journal(body: JournalEntry):
    if not body.entry.strip():
        raise HTTPException(status_code=400, detail="entry must not be empty")
    created_at = datetime.now(IST).isoformat()
    db.add_journal_entry(body.entry.strip(), created_at)
    return {"ok": True, "created_at": created_at}


# ── Resume diff ───────────────────────────────────────────────────────────────

@app.post("/api/resumediff")
def resume_diff():
    entries = db.get_journal_entries(limit=30)
    if not entries:
        raise HTTPException(status_code=422, detail="No journal entries yet. Add entries first.")
    journal_text = "\n".join(
        f"[{e['created_at'][:10]}] {e['entry']}" for e in reversed(entries)
    )
    prompt = f"""You are an expert Resume Advisor specializing in Full Stack Engineering and AI Development.

    Below are the user's recent work journal entries:

    {journal_text}

    The user's current resume is focused on Full Stack Development, specifically:
    - AI & RAG Systems: Building and deploying "Tessera" (RAG agent) on Vercel.
    - Backend & Rust: Developing Rust Rocket and Axum-based services, including real-time chat rooms.
    - Frontend & Dashboards: Creating the Covalent Vibe Dashboard using Next.js and Tailwind CSS.
    - DevRel/Solutions Engineering: Technical documentation and developer advocacy at BuildBear.

    Based on the journal entries, suggest specific resume updates:

    1. NEW BULLET POINTS: Provide exact LaTeX \item text for the "Projects" or "Experience" sections. Focus on engineering challenges, performance metrics, and deployment (Vercel, Railway).
    2. STRENGTHENING EXISTING BULLETS: Suggest ways to improve current bullet points by adding quantifiable results (e.g., latency reduction in RAG pipelines or API response times).
    3. TECHNICAL SKILLS: Identify new frameworks, libraries (e.g., LangChain, Axum, Rocket), or tools mentioned in the journal that should be added to the "Technical Skills" section.

    CRITICAL CONSTRAINT: Do not include or suggest updates related to Web3 security audits, smart contract vulnerabilities, or bug bounty hunting. This resume is strictly for Full Stack and AI Engineering roles.

    Format your response as a clear numbered list."""
    suggestions = llm.chat(prompt, max_tokens=800, temperature=0.4)
    return {"suggestions": suggestions}


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return db.get_config()


@app.put("/api/config")
def put_config(body: Dict[str, Any]):
    db.set_config(body)
    return {"ok": True}


# ── Candidate profile ─────────────────────────────────────────────────────────

class ProfileBody(BaseModel):
    profile: str


@app.get("/api/profile")
def get_profile():
    return {"profile": db.get_profile()}


@app.put("/api/profile")
def put_profile(body: ProfileBody):
    if not body.profile.strip():
        raise HTTPException(status_code=400, detail="profile must not be empty")
    db.set_profile(body.profile.strip())
    return {"ok": True}


@app.post("/api/profile/sync-from-journal")
def sync_profile_from_journal():
    entries = db.get_journal_entries(limit=30)
    if not entries:
        raise HTTPException(status_code=422, detail="No journal entries yet.")
    journal_text = "\n".join(
        f"[{e['created_at'][:10]}] {e['entry']}" for e in reversed(entries)
    )
    current_profile = db.get_profile()
    prompt = f"""You are a resume advisor. Update this candidate profile with new skills and experience from their recent work journal.

CURRENT PROFILE:
{current_profile}

RECENT JOURNAL ENTRIES:
{journal_text}

INSTRUCTIONS:
- Add any new technologies, tools, or skills mentioned in the journal that aren't in the profile
- Update "Recent work" with notable accomplishments from the journal
- Keep all existing info that is still relevant
- Keep the same concise format — this text is used as context for AI job scoring
- Do NOT invent anything not mentioned in the journal or existing profile
- Return ONLY the updated profile text, no commentary

Updated profile:"""
    updated = llm.chat(prompt, max_tokens=600, temperature=0.2)
    return {"profile": updated.strip()}


@app.get("/api/sources")
async def get_sources():
    return db.get_distinct_sources()


# ── Campaigns ────────────────────────────────────────────────────────────────

@app.get("/api/campaigns")
def get_campaigns(include_archived: bool = False):
    if include_archived:
        return {"campaigns": db.list_campaigns(enabled_only=False)}
    return {"campaigns": db.list_campaigns(enabled_only=True)}


@app.post("/api/campaigns")
def post_campaign(body: CampaignCreateRequest):
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    overrides = {}
    if body.name:
        overrides["name"] = body.name.strip()
    if body.enabled_plugins is not None:
        overrides["enabled_plugins"] = body.enabled_plugins
    if body.max_yoe is not None:
        overrides["max_yoe"] = body.max_yoe
    if body.locations is not None:
        overrides["locations"] = body.locations
    campaign = campaigns_mod.create_campaign(body.prompt.strip(), overrides=overrides)
    return campaign


@app.post("/api/campaigns/{campaign_id}/run")
def run_campaign(campaign_id: str):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaigns_mod.run_discovery_campaign(campaign_id)


@app.post("/api/campaigns/{campaign_id}/archive")
def archive_campaign(campaign_id: str):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    db.set_campaign_enabled(campaign_id, False)
    return {"ok": True, "campaign_id": campaign_id, "archived": True}


@app.post("/api/campaigns/{campaign_id}/restore")
def restore_campaign(campaign_id: str):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    db.set_campaign_enabled(campaign_id, True)
    return {"ok": True, "campaign_id": campaign_id, "archived": False}


@app.get("/api/campaigns/{campaign_id}/results")
def get_campaign_results(campaign_id: str, limit: int = 50):
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "campaign": campaign,
        "last_run": db.get_latest_campaign_run(campaign_id),
        "results": db.get_campaign_results(campaign_id, limit=limit),
    }


@app.post("/api/discovery/run")
def run_prompt_discovery(body: DiscoveryRunRequest):
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    overrides = {}
    if body.enabled_plugins is not None:
        overrides["enabled_plugins"] = body.enabled_plugins
    campaign = campaigns_mod.create_campaign(body.prompt.strip(), overrides=overrides)
    summary = campaigns_mod.run_discovery_campaign(campaign["id"])
    return {"campaign": campaign, "summary": summary}


@app.post("/api/discovery/ats/refresh")
def refresh_ats_registry(body: ATSRefreshRequest):
    return sources_ats_mod.refresh_ats_registry(force=body.force)




# ── Interview Prep ────────────────────────────────────────────────────────────

class InterviewRequest(BaseModel):
    jd: str
    questions: list  # list of question strings


@app.post("/api/interview/answer")
def answer_interview_questions(body: InterviewRequest):
    """
    Given a job description and a list of questions from a hiring page,
    answer each question using the candidate's profile + resume files as context.

    The local LLM (Ollama) handles this — no external API needed.
    Resume context comes from:
      1. The candidate profile stored in the DB (always available).
      2. The .tex resume files in RESUME_DIR (if mounted — richer detail).
    """
    if not body.jd.strip():
        raise HTTPException(status_code=400, detail="jd must not be empty")
    questions = [q.strip() for q in body.questions if q.strip()]
    if not questions:
        raise HTTPException(status_code=400, detail="at least one question required")

    # ── Build resume context ──────────────────────────────────────────────────
    profile_text = db.get_profile()

    # Try to read .tex resume files for richer context (they contain full resume)
    resume_context = profile_text
    try:
        files = tailor_mod.load_resume_files()
        if files:
            combined = "\n\n".join(
                f"=== {rel_path} ===\n{content}"
                for rel_path, content in list(files.items())[:8]  # cap at 8 files
            )
            resume_context = f"CANDIDATE PROFILE:\n{profile_text}\n\nRESUME (LaTeX source):\n{combined}"
    except Exception:
        pass  # profile_text alone is the fallback

    # ── Answer each question ──────────────────────────────────────────────────
    jd_snippet = body.jd[:2500]  # cap JD length so prompt fits in context
    answers = []
    for q in questions:
        prompt = f"""You are helping a job candidate fill out a hiring application. Your job is to answer in their voice — not a polished, AI-sounding version of them.

=== CANDIDATE'S OWN WORDS (primary source) ===
The candidate has already answered several questions in their own natural language. These are their real answers, written by them:

{candidate_interview_kb}

=== RESUME / BACKGROUND (secondary source) ===
{resume_context[:3000]}

=== JOB DESCRIPTION (for tone calibration) ===
{jd_snippet}

=== QUESTION TO ANSWER ===
{q}

=== INSTRUCTIONS ===

Step 1 — Search the candidate's own answers above for anything directly relevant to this question.
  - If you find a strong match: base your answer on that content. Preserve their phrasing, sentence rhythm, and casual-but-grounded tone. You may lightly restructure for clarity but do NOT sanitize their voice into corporate language.
  - If you find a partial match: use the relevant part as your anchor and extend it using only what's in the resume. Do not invent.
  - If there is no relevant match in their own answers: answer using the resume only, in the same natural tone as their KB answers. Be honest if something is outside their direct experience — then pivot to the closest transferable skill.

Step 2 — Apply these rules to every answer:
  - First person, 2–5 sentences unless the question clearly demands more.
  - Specific and grounded. No vague claims like "I am passionate about X."
  - Do NOT invent experiences, projects, or skills not present in the sources above.
  - Match the candidate's natural voice: direct, confident, occasionally informal — not stiff.

Answer:"""
        answer = llm.chat(prompt, max_tokens=400, temperature=0.3)
        answers.append({"question": q, "answer": answer.strip()})

    return {"answers": answers}

# ── Static files (React SPA) — registered LAST so API routes always win ─────

FRONTEND_DIST = Path(__file__).parent.parent.parent / "src" / "frontend" / "dist"


@app.get("/api/resume/compile-test")
def resume_compile_test():
    """
    Dry-run: copies the master resume into a temp dir and compiles it with latexmk.
    No LLM involved. Use this to verify LaTeX packages and file mounts are correct.
    """
    import tempfile, shutil
    files = tailor_mod.load_resume_files()
    if not files:
        raise HTTPException(status_code=500, detail=f"No resume files found at {tailor_mod.RESUME_DIR}")

    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "sections"), exist_ok=True)
        for rel_path, content in files.items():
            out = os.path.join(tmp, rel_path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w") as f:
                f.write(content)

        pdf_path, log = tailor_mod.compile_pdf(tmp)
        if pdf_path:
            return {"ok": True, "files_loaded": list(files.keys())}
        return {
            "ok": False,
            "files_loaded": list(files.keys()),
            "log": log[-3000:],   # last 3000 chars of latexmk output
        }

# ═══════════════════════════════════════════════════════════════════════════════
# OUTREACH ROUTES — paste these into main.py (after existing imports/models)
# Also add:  import outreach as outreach_mod
# And in lifespan: outreach_mod.init_outreach_tables()
# ═══════════════════════════════════════════════════════════════════════════════

# ── Pydantic models ───────────────────────────────────────────────────────────

class ScrapeOutreachRequest(BaseModel):
    company: str
    designation: str
    location: str = ""
    email_domain: str
    pages: int = 3
    email_pattern: str = "firstname.lastname"
    provider: str = "serper"


class OutreachTemplateRequest(BaseModel):
    name: str
    subject: str
    body: str


class SendBulkRequest(BaseModel):
    contact_ids: list
    template_id: int
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    sender_name: str
    delay_seconds: float = 3.0


class ContactStatusUpdate(BaseModel):
    status: str


# ── Routes ────────────────────────────────────────────────────────────────────

_PROVIDER_ENV = {
    "serper":     "SERPER_API_KEY",
    "scraperapi": "SCRAPERAPI_KEY",
    "hunter":     "HUNTER_API_KEY",
}


@app.get("/api/outreach/providers")
def get_outreach_providers():
    """Return which scraper providers have their API key configured in env."""
    return {
        provider: bool(os.environ.get(env_var))
        for provider, env_var in _PROVIDER_ENV.items()
    }


@app.post("/api/outreach/scrape")
async def scrape_outreach(req: ScrapeOutreachRequest):
    """Kick off a LinkedIn people scrape. API key is read from server env vars."""
    env_var = _PROVIDER_ENV.get(req.provider, "SERPER_API_KEY")
    api_key = os.environ.get(env_var, "")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"{env_var} is not set. Add it to your .env / docker-compose environment.",
        )

    # Capture locals so the lambda is safe inside run_in_executor
    _company     = req.company
    _designation = req.designation
    _location    = req.location
    _domain      = req.email_domain
    _pages       = req.pages
    _pattern     = req.email_pattern
    _provider    = req.provider
    _key         = api_key

    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: outreach_mod.scrape_linkedin_people(
            company=_company,
            designation=_designation,
            location=_location,
            email_domain=_domain,
            pages=_pages,
            scraper_api_key=_key,
            email_pattern=_pattern,
            provider=_provider,
        ),
    )
    saved = outreach_mod.save_contacts(result["contacts"])
    return {
        "scraped": len(result["contacts"]),
        "saved": saved,
        "errors": result["errors"],
    }


@app.get("/api/outreach/contacts")
def get_outreach_contacts(status: str = "", company: str = ""):
    return outreach_mod.get_contacts(
        status=status or None,
        company=company or None,
    )


@app.patch("/api/outreach/contacts/{contact_id}")
def update_outreach_contact(contact_id: str, body: ContactStatusUpdate):
    outreach_mod.update_contact_status(contact_id, body.status)
    return {"ok": True}


@app.delete("/api/outreach/contacts/{contact_id}")
def delete_outreach_contact(contact_id: str):
    outreach_mod.delete_contact(contact_id)
    return {"ok": True}


@app.post("/api/outreach/contacts/add")
def add_manual_contact(body: dict):
    """Manually add a single contact."""
    from datetime import datetime
    import hashlib
    first = body.get("first_name", "").strip()
    last = body.get("last_name", "").strip()
    company = body.get("company", "").strip()
    email = body.get("email", "").strip()
    if not email:
        domain = body.get("email_domain", "")
        pattern = body.get("email_pattern", "firstname.lastname")
        email = outreach_mod.generate_email(first, last, domain, pattern)
    cid = hashlib.md5(email.encode()).hexdigest()[:12]
    contact = {
        "id": cid,
        "name": f"{first} {last}".strip(),
        "first_name": first,
        "last_name": last,
        "title": body.get("title", ""),
        "company": company,
        "email": email,
        "linkedin_url": body.get("linkedin_url", ""),
        "email_pattern": body.get("email_pattern", ""),
        "status": "new",
        "scraped_at": datetime.utcnow().isoformat(),
    }
    outreach_mod.save_contacts([contact])
    return contact


@app.get("/api/outreach/templates")
def get_outreach_templates():
    return outreach_mod.get_templates()


@app.post("/api/outreach/templates")
def save_outreach_template(req: OutreachTemplateRequest):
    tid = outreach_mod.save_template(req.name, req.subject, req.body)
    return {"id": tid, "ok": True}


@app.delete("/api/outreach/templates/{template_id}")
def delete_outreach_template(template_id: int):
    outreach_mod.delete_template(template_id)
    return {"ok": True}


class GenerateTemplateRequest(BaseModel):
    context: str          # e.g. "targeting DeFi protocol engineering managers"
    tone: str = "professional"   # professional | casual | direct


@app.post("/api/outreach/templates/generate")
def generate_outreach_template(body: GenerateTemplateRequest):
    """Use local Ollama LLM to draft a cold-email template."""
    import json as _json, re as _re

    prompt = f"""You are writing a cold outreach email template for a job seeker.

CONTEXT: {body.context}
TONE: {body.tone}

The sender is a full-stack engineer specialising in AI agents (LangChain, LangGraph) and Web3/DeFi (Solidity, EVM, Arbitrum). They have shipped production RAG pipelines, autonomous trading agents, and smart contract integrations.

Generate ONE concise cold email. Rules:
- Subject: punchy, specific, max 10 words. Avoid generic openers like "Quick question".
- Body: 3–5 sentences. Open with a specific observation about their work or company. State one relevant thing the sender built. Close with a soft CTA ("Would you be open to a 15-min chat?").
- Use these template variables where natural: {{{{first_name}}}}, {{{{company}}}}, {{{{title}}}}, {{{{sender_name}}}}
- Sign off with "Best,\\n{{{{sender_name}}}}"

Return ONLY a raw JSON object — no markdown fences, no explanation:
{{"subject": "...", "body": "..."}}"""

    raw = llm.chat(prompt, max_tokens=700, temperature=0.75)

    # Extract the first {...} block from the response
    match = _re.search(r'\{.*\}', raw, _re.DOTALL)
    if not match:
        raise HTTPException(status_code=500, detail=f"LLM returned non-JSON: {raw[:300]}")
    try:
        data = _json.loads(match.group())
        return {"subject": data["subject"], "body": data["body"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"JSON parse failed: {exc} — raw: {raw[:300]}")


@app.post("/api/outreach/send")
async def send_outreach_bulk(req: SendBulkRequest):
    """Send emails to selected contacts. Runs in background thread (blocking SMTP)."""
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: outreach_mod.send_bulk(
            contact_ids=req.contact_ids,
            template_id=req.template_id,
            smtp_config={
                "host": req.smtp_host,
                "port": req.smtp_port,
                "user": req.smtp_user,
                "password": req.smtp_password,
            },
            sender_name=req.sender_name,
            delay_seconds=req.delay_seconds,
        )
    )
    return result


@app.post("/api/outreach/preview")
def preview_outreach_email(body: dict):
    """Render a template against a sample contact."""
    tpls = {t["id"]: t for t in outreach_mod.get_templates()}
    tpl = tpls.get(body.get("template_id"))
    if not tpl:
        raise HTTPException(404, "Template not found")
    sample = {
        "name": "Alex Johnson",
        "first_name": "Alex",
        "last_name": "Johnson",
        "company": body.get("company", "Stripe"),
        "title": "Engineering Manager",
    }
    return {
        "subject": outreach_mod.render_template(tpl["subject"], sample, body.get("sender_name", "You")),
        "body": outreach_mod.render_template(tpl["body"], sample, body.get("sender_name", "You")),
    }


# Mount /assets and SPA catch-all must come AFTER all API routes so that
# FastAPI matches specific routes first (routes are evaluated in order).
if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(str(FRONTEND_DIST / "index.html"))
