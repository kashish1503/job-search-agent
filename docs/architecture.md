# OpenClaw Architecture

How the React frontend, FastAPI backend, SQLite store, LLM providers, and external job sources fit together.

> Render these diagrams on GitHub, in VS Code with the Markdown Preview Mermaid extension, or at <https://mermaid.live>.

---

## 1. System architecture and frontend/backend interaction

Solid arrows are request/response paths. Dotted arrows are static serving or read-only mounts.

```mermaid
flowchart LR
  subgraph FE["FRONTEND - React SPA in the browser"]
    direction TB
    UI["Pages and components<br/>Jobs - Campaigns - Resumes<br/>Journal - Interview - Outreach - Config"]
    CLIENT["api.js<br/>fetch wrapper around /api"]
    UI -->|"click, form submit, tab switch"| CLIENT
  end

  HTTP{{"HTTP boundary<br/>JSON over /api/*<br/>same origin in prod, CORS :5173 in dev"}}

  subgraph BE["BACKEND - FastAPI app on port 8000"]
    direction TB
    ROUTES["main.py<br/>REST routes, Pydantic models,<br/>static SPA serving"]
    SCHED["APScheduler<br/>08:00 IST scrape<br/>5 min batch poll"]
    CAMPAIGNS["campaigns.py<br/>planner, filters,<br/>fit scoring, run orchestration"]
    DISC["discovery/registry.py<br/>ollama_web - ats - manual"]
    SCRAPER["scraper.py + sources_ats.py<br/>fetch, parse, title/config filters,<br/>scrape runs and batch polling"]
    TAILOR["tailor.py<br/>LaTeX edit, latexmk, ZIP"]
    OUTREACH["outreach.py<br/>contacts, templates, SMTP"]
    LLM["llm.py<br/>provider abstraction,<br/>task-based model routing"]
  end

  subgraph DATA["DATA AND FILES"]
    direction TB
    DB[("SQLite jobs.db<br/>jobs - campaigns - runs - results<br/>variants - journal - config<br/>outreach - llm_batches")]
    RES_SRC["resume/<br/>source LaTeX project<br/>read-only"]
    RES_OUT["data/resumes/<br/>generated PDF + ZIP artifacts"]
    ENV[".env + environment<br/>provider, models, API keys,<br/>DB_PATH, RESUME_DIR"]
  end

  subgraph EXT["EXTERNAL SERVICES"]
    direction TB
    ATS_EXT["ATS job boards<br/>Greenhouse - Lever - Ashby - Workable"]
    JOBPAGES["Job pages<br/>JobStash + company career sites"]
    OLLAMA_WEB["Ollama web search API"]
    LLM_API["LLM runtime<br/>local Ollama / OpenAI / Anthropic"]
    MAIL["SMTP server"]
    PEOPLE["People-data APIs<br/>Serper / ScraperAPI / Hunter"]
  end

  %% Frontend to backend
  CLIENT <-->|"GET /api/jobs<br/>POST /api/jobs/{id}/status"| HTTP
  CLIENT <-->|"GET, POST /api/campaigns<br/>POST /api/campaigns/{id}/run<br/>POST /api/discovery/run"| HTTP
  CLIENT <-->|"POST /api/tailor<br/>GET /api/variants/*"| HTTP
  CLIENT <-->|"CRUD /api/outreach/*<br/>POST /api/interview/answer"| HTTP
  HTTP <-->|"route to handler<br/>return JSON"| ROUTES

  %% Backend routing
  ROUTES --> CAMPAIGNS
  ROUTES --> SCRAPER
  ROUTES --> TAILOR
  ROUTES --> OUTREACH
  ROUTES -->|"journal diff, interview answers,<br/>template generation"| LLM
  ROUTES --> DB

  %% Scheduler
  SCHED -->|"daily scrape +<br/>batch polling"| SCRAPER

  %% Core pipelines
  CAMPAIGNS -->|"discover(campaign)"| DISC
  CAMPAIGNS -->|"fetch job pages for URLs"| SCRAPER
  CAMPAIGNS -->|"score fit"| LLM
  CAMPAIGNS --> DB

  DISC -->|"ATS board fetch"| SCRAPER
  DISC -->|"web search queries"| OLLAMA_WEB
  DISC -.->|"manual URLs from campaign"| CAMPAIGNS

  SCRAPER -->|"ATS + JobStash + job pages"| JOBPAGES
  SCRAPER -->|"batch scoring"| LLM
  SCRAPER --> DB

  TAILOR -->|"edit prompt + resume files"| LLM
  TAILOR -.->|"read only"| RES_SRC
  TAILOR -->|"write variant"| RES_OUT
  TAILOR --> DB

  OUTREACH -->|"find contacts"| PEOPLE
  OUTREACH -->|"send bulk email"| MAIL
  OUTREACH --> DB

  %% External calls
  SCRAPER --> ATS_EXT
  OLLAMA_WEB --> OLLAMA_API
  LLM -->|"chat / chat_json / batches"| LLM_API
  ENV -.->|"provider + keys + models"| LLM

  %% Static frontend serving
  ROUTES -.->|"serves dist/index.html and /assets"| UI

  classDef frontend fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
  classDef backend fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef data fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef external fill:#f3e8ff,stroke:#9333ea,color:#581c87
  classDef boundary fill:#f8fafc,stroke:#334155,color:#0f172a

  class UI,CLIENT frontend
  class ROUTES,SCHED,CAMPAIGNS,DISC,SCRAPER,TAILOR,OUTREACH,LLM backend
  class DB,RES_SRC,RES_OUT,ENV data
  class ATS_EXT,JOBPAGES,OLLAMA_WEB,LLM_API,MAIL,PEOPLE external
  class HTTP boundary
```

### Reading the diagram

- The browser never talks to SQLite, ATS boards, or the LLM directly. Everything goes through `api.js` and the `/api` HTTP boundary.
- `main.py` is the only entry point. It validates requests with Pydantic models, calls a service module, and returns JSON.
- `campaigns.py` is the orchestration layer for discovery. It fans work out to discovery plugins, materializes job pages, applies deterministic filters, and asks `llm.py` to score fit.
- `llm.py` is the single choke point for model calls. Scoring, planning, tailoring, interview answers, and outreach templates all route through it, with per-task model selection.
- SQLite is the system of record. Resume PDFs and ZIPs live on disk under `data/resumes/`.
- In production the React build is served by FastAPI from `src/frontend/dist`. In development Vite runs on `:5173` and CORS allows that origin.

---

## 2. Campaign discovery: request/response sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as React SPA
    participant API as FastAPI /api
    participant CE as campaigns.py
    participant PL as Discovery plugin
    participant EXT as ATS / web / job pages
    participant LLM as llm.py + provider
    participant DB as SQLite

    U->>FE: Write prompt, choose plugins, click Run
    alt Save a reusable campaign
        FE->>API: POST /api/campaigns
        API->>CE: create_campaign(prompt, overrides)
        CE->>LLM: plan_campaign()
        LLM-->>CE: name, aliases, queries, locations, max_yoe
        CE->>DB: INSERT campaign
        API-->>FE: campaign JSON
        FE->>API: POST /api/campaigns/{id}/run
    else Quick Run Prompt
        FE->>API: POST /api/discovery/run
        API->>CE: create_campaign() then run_discovery_campaign()
    end

    API->>CE: run_discovery_campaign(campaign_id)
    CE->>DB: INSERT campaign_run status=in_progress

    loop each enabled plugin, in a thread pool
        CE->>PL: discover(campaign, limit)
        PL->>EXT: search or fetch ATS job URLs
        EXT-->>PL: URLs or job metadata
        PL-->>CE: normalized, deduplicated candidates
    end

    loop each discovered URL
        CE->>EXT: fetch job page when metadata is missing
        EXT-->>CE: title, company, description, work type
        CE->>CE: deterministic filters
        Note over CE: title match, avoid terms,<br/>onsite-only, seniority cap, YoE cap

        alt Candidate fails hard filters
            CE->>DB: INSERT job status=filtered
            CE->>DB: INSERT campaign_result
        else Candidate passes filters
            CE->>LLM: score(profile, campaign, job)
            LLM-->>CE: score, reason, fit_band,<br/>matched_role_family, red_flags
            CE->>DB: INSERT job status=new or filtered
            CE->>DB: INSERT campaign_result
        end
    end

    CE->>DB: UPDATE campaign_run with summary
    CE-->>API: summary
    API-->>FE: summary JSON
    FE->>API: GET /api/campaigns/{id}/results
    API->>DB: SELECT campaign, last run, results
    API-->>FE: results JSON
    FE-->>U: Render score cards, fit bands, red flags
```

**Key API calls**

| User action | Frontend call | Backend handler | Service |
|---|---|---|---|
| Load queue | `GET /api/jobs?status=new` | `get_jobs` | `db.list_jobs` |
| Load all results | `GET /api/jobs/all` | `get_all_jobs` | `db.list_all_jobs` |
| Open a job | `GET /api/jobs/{id}` | `get_job` | `db.get_job` |
| Apply / skip | `POST /api/jobs/{id}/status` | `update_job_status` | `db.set_status` |
| Create campaign | `POST /api/campaigns` | `post_campaign` | `campaigns.create_campaign` |
| Run campaign | `POST /api/campaigns/{id}/run` | `run_campaign` | `campaigns.run_discovery_campaign` |
| Quick run | `POST /api/discovery/run` | `run_prompt_discovery` | `campaigns.create_campaign` + run |
| Inspect run | `GET /api/campaigns/{id}/results` | `get_campaign_results` | `db.get_campaign_results` |
| Archive / restore | `POST /api/campaigns/{id}/archive` or `/restore` | matching route | `db.set_campaign_enabled` |
| Manual scrape | `POST /api/scrape` | `start_scrape` | `scraper.run_scrape` in background |
| Scrape status | `GET /api/scrape/status` | `scrape_status` | in-memory state |
| Batch poll | `POST /api/batches/poll` | `poll_batches` | `scraper.poll_pending_batches` |

---

## 3. Resume tailoring: request/response sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as React SPA
    participant API as FastAPI
    participant T as tailor.py
    participant DB as SQLite
    participant FS as resume/ + data/resumes/
    participant LLM as LLM provider

    U->>FE: Click Tailor on a job, or paste a URL / JD
    FE->>API: POST /api/tailor { job_id | url | raw_jd }
    API->>T: tailor(...)
    T->>FS: load_resume_files() from read-only resume/
    alt Tailor from saved job
        T->>DB: get_job(job_id)
        Note over T: reuse stored score and description
    else Tailor from URL
        T->>T: fetch_jd(url)
    else Tailor from pasted JD
        T->>T: use raw_jd directly
    end

    opt Fit check when not forced
        T->>LLM: check_fit(profile, job)
        LLM-->>T: score + reason
        alt score below FIT_THRESHOLD
            T-->>API: { fit_warning: true, score, reason }
            API-->>FE: 200 with fit_warning
            FE-->>U: Show warning and "Tailor anyway"
            U->>FE: Tailor anyway
            FE->>API: POST /api/tailor { force: true }
        end
    end

    T->>LLM: build_prompt(jd, title, company, resume files)
    LLM-->>T: JSON containing edited .tex files
    T->>T: keep only editable targets
    T->>FS: write variant folder
    T->>FS: latexmk compile PDF
    T->>FS: ZIP the project for Overleaf
    T->>DB: INSERT resume_variant
    T-->>API: variant_id, paths, changed_files
    API-->>FE: JSON result
    FE-->>U: Preview, download PDF, download ZIP
```

**Generated artifacts**

| Artifact | Path | Served by |
|---|---|---|
| Edited LaTeX project | `data/resumes/<company>_<timestamp>/` | filesystem |
| Compiled PDF | `<variant>/resume.pdf` | `GET /api/variants/{id}/pdf` |
| ZIP for Overleaf | `<variant>.zip` | `GET /api/variants/{id}/zip` |
| Variant metadata | SQLite `resume_variants` | `GET /api/variants` |

---

## 4. Background scraping and batch scoring

```mermaid
sequenceDiagram
    autonumber
    participant SCH as APScheduler
    participant SC as scraper.py
    participant ATS as ATS / JobStash
    participant LLM as llm.py
    participant DB as SQLite
    participant FE as React SPA

    SCH->>SC: daily 08:00 IST run_scrape()
    SC->>DB: read config and candidate profile
    SC->>ATS: fetch ATS boards and JobStash jobs
    ATS-->>SC: raw job records
    SC->>SC: title pre-filter
    SC->>SC: config filters - keywords, work type,<br/>location, YoE
    SC->>DB: save new jobs status=unscored
    SC->>LLM: create_scoring_batch(jobs, profile)
    alt Provider supports async batches
        LLM-->>SC: batch_id
        loop every 5 minutes
            SCH->>SC: poll_pending_batches()
            SC->>LLM: poll_batch(batch_id)
            LLM-->>SC: results or in_progress
            SC->>DB: update score and status
        end
    else Local Ollama or unsupported provider
        LLM-->>SC: synchronous scores
        SC->>DB: update score and status
    end
    FE->>SC: GET /api/scrape/status
    SC-->>FE: running flag, last result, last run
```

---

## 5. Layer responsibilities

| Layer | Files | Responsibility |
|---|---|---|
| UI | `src/frontend/src/pages/*`, `components/*` | Tabs, forms, cards, modals, local view state |
| API client | `src/frontend/src/api.js` | One `fetch` wrapper; all backend calls go through it |
| HTTP API | `src/backend/main.py` | Routing, validation, error mapping, SPA serving, scheduler startup |
| Campaign engine | `src/backend/campaigns.py` | Prompt-to-campaign planning, plugin fan-out, filters, fit scoring, run summaries |
| Discovery | `src/backend/discovery/*` | Plugin interface and concrete plugins |
| Scraping | `src/backend/scraper.py`, `sources_ats.py` | Fetching, parsing, dedupe, title/config filters, batch polling |
| LLM gateway | `src/backend/llm.py` | Provider abstraction, JSON mode, task-specific models, batching |
| Tailoring | `src/backend/tailor.py` | Constrained LaTeX edits, PDF compile, ZIP packaging, variants |
| Outreach | `src/backend/outreach.py` | Contact discovery, templates, bulk SMTP send |
| Persistence | `src/backend/db.py` | Schema, migrations, all SQLite reads/writes |

---

## 6. Notes and caveats

- The plugin registry currently registers three plugins: `ollama_web`, `ats`, and `manual`. Older docs also mention `hn` and `web3`; the corresponding scrapers still exist in `scraper.py` but are not registered as campaign plugins.
- `run_scrape()` currently executes ATS and JobStash sources; the DuckDuckGo site-search branch is commented out.
- `api.js` still exports `startBatchScore`, `stopBatchScore`, and `getBatchScoreStatus`, but `main.py` has no `/api/batch-score/*` routes. The working batch endpoints are `GET /api/batches` and `POST /api/batches/poll`.
- Campaign creation and scoring are synchronous HTTP requests from the browser's point of view. Long runs can take a while; the UI disables the action while waiting.
- The source resume tree is mounted read-only. Only the variant output directory is writable.
