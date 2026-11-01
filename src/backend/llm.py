"""
Thin wrapper around OpenAI, Anthropic and Ollama so the rest of the code
doesn't care which provider is active.

.env config:
  MODEL_PROVIDER=ollama          # openai | anthropic | ollama
  MODEL_API_KEY=ollama           # not needed for ollama
  MODEL_NAME=nemotron-3-nano:4b  # any model pulled in Ollama
  TAILOR_MODEL=nemotron-3-nano:4b
  OLLAMA_BASE_URL=http://host.docker.internal:11434
"""
import os
import json
import re
from typing import Any

# Set LLM_VERBOSE=true in .env to see raw model output before JSON parsing
LLM_VERBOSE = os.environ.get("LLM_VERBOSE", "").lower() in ("1", "true", "yes")
PROVIDER = os.environ.get("MODEL_PROVIDER", "ollama").lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

# NOTE: MODEL and API_KEY are intentionally NOT module-level constants.
# tailor.py hot-swaps MODEL_NAME via os.environ at runtime for TAILOR_MODEL,
# so we must read them fresh inside each call.

def _get_model() -> str:
    return os.environ.get("MODEL_NAME", "nemotron-3-nano:4b")


def _get_api_key() -> str:
    return (
        os.environ.get("MODEL_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
        or "ollama"
    )


def _openai_base_url() -> str:
    return (os.environ.get("OPENAI_BASE_URL") or os.environ.get("MODEL_BASE_URL") or "").rstrip("/")


def _openai_client_kwargs() -> dict:
    base = _openai_base_url()
    return {"base_url": base} if base else {}


def _parse_think_value(raw: str | None) -> bool | str | None:
    if raw is None:
        return None
    val = str(raw).strip().lower()
    if not val:
        return None
    if val in ("0", "false", "no", "off"):
        return False
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("low", "medium", "high"):
        return val
    return None


def get_task_model(task: str | None = None) -> str:
    task = (task or "").strip().lower()
    default = _get_model()
    mapping = {
        "score": os.environ.get("SCORE_MODEL", default),
        "planner": os.environ.get("PLANNER_MODEL", default),
        "tailor": os.environ.get("TAILOR_MODEL", default),
        "research": os.environ.get("RESEARCH_MODEL", default),
    }
    return mapping.get(task, default)


def get_task_think(task: str | None = None) -> bool | str | None:
    task = (task or "").strip().lower()
    env_key = {
        "score": "SCORE_THINK",
        "planner": "PLANNER_THINK",
        "tailor": "TAILOR_THINK",
        "research": "RESEARCH_THINK",
    }.get(task, "DEFAULT_THINK")
    return _parse_think_value(os.environ.get(env_key, os.environ.get("DEFAULT_THINK")))


def supports_native_json(model: str) -> bool:
    if ":cloud" in (model or "").lower():
        return os.environ.get("OLLAMA_CLOUD_NATIVE_JSON", "").lower() in ("1", "true", "yes")
    return True


# ── Public interface ──────────────────────────────────────────────────────────

def chat(
    prompt: str,
    max_tokens: int = 200,
    temperature: float = 0.3,
    *,
    model: str | None = None,
    think: bool | str | None = None,
    task: str | None = None,
) -> str:
    """Send a single-turn prompt, return the assistant text."""
    if PROVIDER == "anthropic":
        return _anthropic(prompt, max_tokens, temperature, model=model, task=task)
    if PROVIDER == "ollama":
        return _ollama(
            prompt,
            max_tokens,
            temperature,
            model=model,
            think=think,
            task=task,
        )
    return _openai(prompt, max_tokens, temperature, model=model, task=task)


def chat_json(
    prompt: str,
    max_tokens: int = 200,
    *,
    model: str | None = None,
    think: bool | str | None = None,
    task: str | None = None,
) -> dict:
    """Like chat() but enforces JSON output and parses the result.
    Returns {} on failure so callers always get a dict.
    """
    if PROVIDER == "ollama":
        selected_model = model or get_task_model(task)
        raw = _ollama(
            prompt,
            max_tokens,
            temperature=0.3,
            json_mode=supports_native_json(selected_model),
            model=selected_model,
            think=think,
            task=task,
        )
    else:
        json_prompt = (
            f"{prompt}\n\nReturn ONLY valid JSON. No markdown fences, no commentary."
        )
        raw = chat(
            json_prompt,
            max_tokens=max_tokens,
            temperature=0.1,
            model=model,
            think=think,
            task=task,
        )

    if LLM_VERBOSE:
        preview = (raw or "").replace("\n", " ").strip()
        print(f"  [llm:raw]   {preview}")

    raw = re.sub(r"^```[a-z]*\n?", "", raw or "")
    raw = re.sub(r"\n?```$", "", raw).strip()

    try:
        return json.loads(raw)
    except Exception as e:
        if LLM_VERBOSE:
            print(f"  [llm:parse_fail]  {e}  →  {raw[:200]}")
        return {}


# ── Provider implementations ──────────────────────────────────────────────────

def _openai(prompt, max_tokens, temperature, *, model=None, task=None):
    from openai import OpenAI
    client = OpenAI(api_key=_get_api_key(), **_openai_client_kwargs())
    resp = client.chat.completions.create(
        model=model or get_task_model(task),
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def _anthropic(prompt, max_tokens, temperature, *, model=None, task=None):
    import anthropic
    client = anthropic.Anthropic(api_key=_get_api_key())
    msg = client.messages.create(
        model=model or get_task_model(task),
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _ollama(
    prompt,
    max_tokens,
    temperature: float = 0.3,
    json_mode: bool = False,
    *,
    model: str | None = None,
    think: bool | str | None = None,
    task: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """
    Call a locally-running Ollama instance.

    Key behavior:
    - Model is selected per task instead of mutating MODEL_NAME globally.
    - `think` is only passed when explicitly configured.
    - Native JSON mode is opt-in per selected model.
    """
    from ollama import Client
    client = Client(host=OLLAMA_BASE_URL)
    selected_model = model or get_task_model(task)
    selected_think = think if think is not None else get_task_think(task)

    options: dict[str, Any] = {
        "temperature": temperature,
    }
    if max_tokens:
        options["num_predict"] = max_tokens
    if num_ctx:
        options["num_ctx"] = num_ctx

    kwargs: dict[str, Any] = dict(
        model=selected_model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
        options=options,
    )
    if selected_think is not None:
        kwargs["think"] = selected_think

    if json_mode:
        # Constrains Ollama's output to valid JSON grammar — works on any model
        kwargs["format"] = "json"

    resp = client.chat(**kwargs)
    return (resp.message.content or "").strip()


# ── Batch scoring ─────────────────────────────────────────────────────────────

def create_scoring_batch(jobs: list, candidate_profile: str) -> str | None:
    """Submit jobs for batch scoring. Returns batch_id or None."""
    if not jobs:
        return None
    if PROVIDER == "anthropic":
        return _create_anthropic_batch(jobs, candidate_profile)
    if PROVIDER == "openai":
        # Third-party OpenAI-compatible endpoints generally do not implement the
        # Batch API; fall back to synchronous scoring via the caller's fallback.
        if _openai_base_url():
            return None
        return _create_openai_batch(jobs, candidate_profile)
    if PROVIDER == "ollama":
        return _create_ollama_batch(jobs, candidate_profile)
    return None


def _create_ollama_batch(jobs, candidate_profile):
    """
    Run concurrent scoring requests against a local Ollama instance.
    Worker count controlled by OLLAMA_BATCH_WORKERS (default 4).
    Returns a LOCAL_BATCH_DONE: string so poll_batch() resolves instantly.
    """
    import concurrent.futures

    max_workers = int(os.environ.get("OLLAMA_BATCH_WORKERS", "4"))
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_job = {
            executor.submit(
                _ollama,
                _build_score_prompt(job, candidate_profile),
                80,     # max_tokens
                0.1,    # temperature
                json_mode=supports_native_json(get_task_model("score")),
                task="score",
            ): job
            for job in jobs
        }
        for future in concurrent.futures.as_completed(future_to_job):
            job = future_to_job[future]
            custom_id = job.get("id")
            try:
                raw_text = future.result()
                raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text).strip()
                data = json.loads(raw_text)
                results.append({
                    "custom_id": custom_id,
                    "score": int(data.get("score", 0)),
                    "reason": str(data.get("reason", ""))[:120],
                })
            except Exception as e:
                results.append({
                    "custom_id": custom_id,
                    "score": 0,
                    "reason": f"Ollama error: {str(e)[:80]}",
                })

    return f"LOCAL_BATCH_DONE:{json.dumps(results)}"


def _create_anthropic_batch(jobs, candidate_profile):
    import anthropic
    client = anthropic.Anthropic(api_key=_get_api_key())
    reqs = []
    for job in jobs:
        prompt = _build_score_prompt(job, candidate_profile)
        reqs.append({
                "custom_id": job["id"],
                "params": {
                "model": get_task_model("score"),
                "max_tokens": 80,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
        })
    batch = client.messages.batches.create(requests=reqs)
    return batch.id


def _create_openai_batch(jobs, candidate_profile):
    """OpenAI Batch API: write JSONL → upload → create batch → return batch_id."""
    import tempfile
    from openai import OpenAI
    client = OpenAI(api_key=_get_api_key())

    lines = []
    for job in jobs:
        prompt = _build_score_prompt(job, candidate_profile)
        lines.append(json.dumps({
            "custom_id": job["id"],
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": get_task_model("score"),
                "max_tokens": 80,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
        }))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("\n".join(lines))
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as f:
            uploaded = client.files.create(file=f, purpose="batch")
        batch = client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
        )
        return batch.id
    finally:
        import os as _os
        _os.unlink(tmp_path)


# ── Batch polling ─────────────────────────────────────────────────────────────

def poll_batch(batch_id: str, provider: str | None = None) -> dict | None:
    """Check batch status. Returns {status, results} or None."""
    prov = (provider or PROVIDER).lower()
    if prov == "anthropic":
        return _poll_anthropic_batch(batch_id)
    if prov == "openai":
        return _poll_openai_batch(batch_id)
    if prov == "ollama":
        return _poll_ollama_batch(batch_id)
    return None


def _poll_ollama_batch(batch_id: str) -> dict | None:
    """Ollama batches complete synchronously; results are embedded in batch_id."""
    if batch_id.startswith("LOCAL_BATCH_DONE:"):
        try:
            results_json = batch_id[len("LOCAL_BATCH_DONE:"):]
            results = json.loads(results_json)
            return {"status": "completed", "results": results}
        except Exception as e:
            print(f"[poll_ollama_batch] failed to parse embedded results: {e}")
            return {"status": "completed", "results": []}
    return {"status": "in_progress", "results": []}


def _poll_anthropic_batch(batch_id):
    import anthropic
    client = anthropic.Anthropic(api_key=_get_api_key())
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        return {"status": "in_progress", "results": []}

    results = []
    for entry in client.messages.batches.results(batch_id):
        custom_id = entry.custom_id
        score, reason = 0, ""
        if entry.result.type == "succeeded":
            raw_text = entry.result.message.content[0].text.strip()
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text).strip()
            try:
                data = json.loads(raw_text)
                score = int(data.get("score", 0))
                reason = str(data.get("reason", ""))[:120]
            except Exception:
                reason = "parse error"
        else:
            reason = f"batch error: {entry.result.type}"
        results.append({"custom_id": custom_id, "score": score, "reason": reason})
    return {"status": "completed", "results": results}


def _poll_openai_batch(batch_id):
    from openai import OpenAI
    client = OpenAI(api_key=_get_api_key())
    batch = client.batches.retrieve(batch_id)

    if batch.status in ("validating", "in_progress", "finalizing"):
        return {"status": "in_progress", "results": []}
    if batch.status in ("failed", "expired", "cancelled"):
        return {"status": batch.status, "results": []}

    if not batch.output_file_id:
        return {"status": "completed", "results": []}

    content = client.files.content(batch.output_file_id).text
    results = []
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            custom_id = entry.get("custom_id", "")
            score, reason = 0, ""
            body = entry.get("response", {}).get("body", {})
            choices = body.get("choices", [])
            if choices:
                raw_text = choices[0].get("message", {}).get("content", "").strip()
                raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text).strip()
                try:
                    data = json.loads(raw_text)
                    score = int(data.get("score", 0))
                    reason = str(data.get("reason", ""))[:120]
                except Exception:
                    reason = "parse error"
            results.append({"custom_id": custom_id, "score": score, "reason": reason})
        except json.JSONDecodeError:
            continue
    return {"status": "completed", "results": results}


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_score_prompt(job: dict, candidate_profile: str) -> str:
    desc = (job.get("description") or "")[:1200]
    return f"""Score this job for the candidate (0-100).

CANDIDATE:
{candidate_profile}

JOB:
Title: {job.get('title', '?')}
Company: {job.get('company', '?')}
Work type: {job.get('work_type', '?')}
Location: {job.get('location', '?')}
Description: {desc}

Rules:
- Score 0 if the role requires physical presence (onsite/in-office) anywhere
- Score 0 if it requires 5+ years experience for a junior/mid candidate
- Score based on tech stack overlap, seniority match, remote availability

Reply ONLY valid JSON: {{"score": <int>, "reason": "<max 100 chars>"}}"""
