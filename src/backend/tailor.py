import hashlib
import os
import re
import json
import subprocess
import zipfile
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

import db
import llm

IST = timezone(timedelta(hours=5, minutes=30))
RESUME_DIR = os.environ.get("RESUME_DIR", "/app/resume")
RESUME_OUT_DIR = "/app/data/resumes"

TAILOR_TARGETS = {
    "sections/summary.tex",      # <--- was summary.tex
    "sections/experience.tex",
    "sections/skills.tex",
    "sections/projects.tex",
    "sections/achievements.tex",
    # "sections/security.tex",
}

COPY_ONLY = {
    "resume.tex", "_header.tex", "TLCresume.sty",
    "sections/education.tex", "sections/certifications.tex", "sections/por.tex",
    "sections/security.tex",
}



def build_prompt(jd, title, company, files):
    target_content = {k: v for k, v in files.items() if k in TAILOR_TARGETS}
    files_block = "\n\n".join(
        f"### FILE: {path}\n```latex\n{content}\n```"
        for path, content in target_content.items()
    )
    return f"""You are a LaTeX resume editor. Your only output is a single raw JSON object. Nothing else.

═══════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════
Tailor the resume files below for this specific job opening.

JOB TITLE : {title}
COMPANY   : {company}

JOB DESCRIPTION (first 1500 chars):
{jd[:1500]}

RESUME FILES TO EDIT:
{files_block}

═══════════════════════════════════════════════════════
TAILORING RULES  (what to change)
═══════════════════════════════════════════════════════
1. sections/summary.tex  — Rewrite the summary to speak directly to this role.
   Match tone and keywords from the JD. Do NOT invent experience that is not
   already in the resume.

2. sections/experience.tex  — Reorder bullet points so the most relevant
   experience for this role appears first within each job block.
   Do NOT change company names, job titles, or dates.
   Do NOT add or remove entire job blocks.

3. sections/skills.tex  — Reorder skill groups so the most relevant appear
   first. Do NOT add skills not already in the file. Remove, add or deprioritise Web3 Skills if the JD is non-Web3, and vice versa.

4. sections/projects.tex  — Pick EXACTLY 4 projects most relevant to this JD.
   Remove the entire \\resumeProjectHeading block (heading + \\resumeItemListStart
   ... \\resumeItemListEnd) for every project NOT in your top 4.
   Do NOT edit the content of kept projects. Do NOT touch the \\section header
   or surrounding \\vspace commands.

5. sections/achievements.tex  — Reorder so most relevant achievements appear
   first. Do NOT add or remove items.

6. Only return files that you actually changed. If a file needs no changes,
   omit it from the JSON entirely.

═══════════════════════════════════════════════════════
JSON FORMAT RULES  (read every rule — violations cause hard failures)
═══════════════════════════════════════════════════════
RULE 1 — OUTPUT ONLY JSON.
  Your entire response must be a single JSON object.
  No markdown code fences (no ```json or ```).
  No preamble, no explanation, no trailing text after the closing brace.
  First character of your response: {{
  Last character of your response: }}

RULE 2 — BACKSLASH ESCAPING.
  Inside a JSON string, every single backslash MUST be written as two
  backslashes. This applies to ALL LaTeX commands without exception.
  WRONG : "\\textbf{{foo}}"
  CORRECT: "\\\\textbf{{foo}}"
  WRONG : "\\begin{{itemize}}"
  CORRECT: "\\\\begin{{itemize}}"
  WRONG : "\\item foo"
  CORRECT: "\\\\item foo"
  If you write a single backslash inside a JSON string, the parser will throw
  a JSONDecodeError and your entire response will be rejected.

RULE 3 — NEWLINES INSIDE STRINGS.
  JSON string values cannot contain literal line breaks.
  Every line break in the LaTeX source MUST be represented as the two-character
  escape sequence: \\n
  WRONG : "line one
line two"
  CORRECT: "line one\\nline two"

RULE 4 — DOUBLE BRACES IN LATEX.
  LaTeX uses {{}} for command arguments, e.g. \\textbf{{word}}, \\section{{Title}}.
  These double braces are valid JSON string content. Do NOT change them.

RULE 5 — NO TRUNCATION.
  Every file you include in the JSON must contain the COMPLETE file content.
  Never cut off mid-file. If you are running out of output space, remove a
  file from the JSON entirely rather than returning it truncated.

RULE 6 — VALID JSON ONLY.
  Before finalising your response, mentally verify:
  - Every opening {{ has a matching closing }}
  - Every opening " has a matching closing "
  - No trailing comma after the last key-value pair
  - No unescaped control characters (tabs, newlines) inside string values

RESPONSE SHAPE:
{{
  "sections/summary.tex": "...complete file content with all backslashes doubled and newlines as \\\\n...",
  "sections/projects.tex": "...complete file content..."
}}"""


# ─── Replacement prompt string for apply_edits() ─────────────────────────────
# Replace the prompt = f"""...""" block inside apply_edits() with this.

APPLY_EDITS_PROMPT_TEMPLATE = """You are a LaTeX resume editor. Your only output is a single raw JSON object. Nothing else.

═══════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════
Apply the user's requested changes to the resume files below.

USER INSTRUCTIONS:
{instructions}

RESUME FILES:
{files_block}

═══════════════════════════════════════════════════════
EDITING RULES  (what you may and may not do)
═══════════════════════════════════════════════════════
1. Apply ONLY the changes the user explicitly requested. Nothing else.
2. Do NOT invent skills, tools, or experience not already in the resume.
3. Do NOT change company names, job titles, or dates.
4. Do NOT reformat or reorder content that the user did not ask to change.
5. Keep ALL LaTeX commands intact — do not simplify or replace them.
6. For projects.tex: if the user asks to pick N projects, remove the entire
   \\resumeProjectHeading block (heading + \\resumeItemListStart ...
   \\resumeItemListEnd) for every project not selected. Do NOT touch the
   \\section header or surrounding \\vspace commands.
7. For layout: do NOT add random \\vspace, \\newpage, or blank lines unless
   the user specifically asked for spacing fixes. Trust the existing layout.
8. Only return files that actually changed. Omit unchanged files entirely.

═══════════════════════════════════════════════════════
JSON FORMAT RULES  (violations cause hard failures on the client)
═══════════════════════════════════════════════════════
RULE 1 — OUTPUT ONLY JSON.
  Your entire response must be a single JSON object.
  No markdown fences. No preamble. No trailing text.
  First character: {{   Last character: }}

RULE 2 — BACKSLASH ESCAPING.
  Every backslash in LaTeX MUST be doubled inside a JSON string.
  \\textbf   → \\\\textbf
  \\begin    → \\\\begin
  \\item     → \\\\item
  \\section  → \\\\section
  A single backslash inside a JSON string is a JSONDecodeError.

RULE 3 — NEWLINES.
  No literal line breaks inside JSON string values.
  Represent every line break as: \\n

RULE 4 — COMPLETE FILES ONLY.
  Every file in the JSON must contain its COMPLETE content.
  Never truncate. If you cannot fit a file, omit it entirely.

RULE 5 — VALID JSON.
  Verify before responding:
  - Matching braces and quotes
  - No trailing comma after last key-value pair
  - No unescaped control characters in strings

RESPONSE SHAPE:
{{"sections/summary.tex": "...complete content...", "sections/projects.tex": "...complete content..."}}"""


# ─── Replacement prompt string for refine_variant() ──────────────────────────
# Replace the prompt = f"""...""" block inside refine_variant() with this.

REFINE_VARIANT_PROMPT_TEMPLATE = """You are a LaTeX resume editor. Your only output is a single raw JSON object. Nothing else.

═══════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════
Apply this feedback to the current resume variant.

FEEDBACK:
{feedback}

CURRENT RESUME FILES:
{files_block}

═══════════════════════════════════════════════════════
RULES
═══════════════════════════════════════════════════════
1. Apply ONLY the changes described in the feedback.
2. Do NOT invent skills, tools, or experience not already in the resume.
3. Do NOT change company names, job titles, or dates.
4. Keep ALL LaTeX commands intact.
5. Only return files that actually changed. Omit unchanged files.

═══════════════════════════════════════════════════════
JSON FORMAT RULES  (violations cause hard failures on the client)
═══════════════════════════════════════════════════════
RULE 1 — OUTPUT ONLY JSON. No markdown fences, no preamble, no trailing text.
  First character: {{   Last character: }}

RULE 2 — BACKSLASH ESCAPING.
  Every backslash in LaTeX MUST be doubled inside JSON strings.
  \\textbf → \\\\textbf  |  \\begin → \\\\begin  |  \\item → \\\\item
  A single backslash inside a JSON string causes a JSONDecodeError.

RULE 3 — NEWLINES.
  No literal newlines inside JSON string values. Use \\n instead.

RULE 4 — COMPLETE FILES ONLY.
  Include the full content of every changed file. Never truncate.

RULE 5 — VALID JSON.
  Matching braces/quotes, no trailing comma, no unescaped control characters.

RESPONSE SHAPE:
{{"sections/summary.tex": "...complete content..."}}"""

def _repair_latex_json(raw: str) -> str:
    """
    Best-effort repair of common LLM mistakes when embedding LaTeX inside JSON.

    Problems seen in the wild:
    1. LLM emits a single backslash instead of \\\\ (raw \\ in the JSON string),
       so sequences like \\textbf, \\section, \\begin appear as bare control chars.
    2. LLM uses actual newlines inside a JSON string value instead of \\n.
    3. Response is truncated – the JSON is simply cut off; we can't fix this,
       but we log a clear message so the caller knows to raise max_tokens.
    """
    # If it already parses, nothing to do.
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # Strategy: locate each string value and fix un-escaped content inside it.
    # We do this by re-serializing via a regex that operates on the raw text.
    #
    # Pass 1: fix literal (unescaped) newlines inside JSON string values.
    # A JSON string value spans from an opening " (not preceded by \) to the
    # matching closing " (not preceded by \).  Newlines inside it are illegal.
    def _fix_newlines(m):
        # m.group(0) is the whole matched string literal including the quotes
        inner = m.group(1)
        inner = inner.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
        return '"' + inner + '"'

    # Regex: match a JSON string token (simplified – handles most real output)
    repaired = re.sub(
        r'"((?:[^"\\]|\\.)*)"',
        _fix_newlines,
        raw,
        flags=re.DOTALL,
    )

    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        pass

    # If still broken, return original so the caller gets the real error
    return raw


def apply_edits(instructions: str, variant_name: str = "") -> dict:
    """Apply free-form resume edit instructions (no job context needed)."""
    files = load_resume_files()
    if not files:
        return {"error": f"No resume files found at {RESUME_DIR}. Check volume mount."}
    if not instructions.strip():
        return {"error": "instructions must not be empty"}

    target_content = {k: v for k, v in files.items() if k in TAILOR_TARGETS}
    files_block = "\n\n".join(
        f"### FILE: {path}\n```latex\n{content}\n```"
        for path, content in target_content.items()
    )

    prompt = APPLY_EDITS_PROMPT_TEMPLATE.format(
        instructions=instructions.strip(),
        files_block=files_block,
    )

    raw = llm.chat(prompt, max_tokens=16000, temperature=0.35, task="tailor")

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    raw = _repair_latex_json(raw)

    try:
        updated_files = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"LLM returned invalid JSON: {e}\n{raw[:200]}"}

    updated_files = {k: v for k, v in updated_files.items() if k in TAILOR_TARGETS}
    if not updated_files:
        return {"error": "LLM returned no changed files. Try rephrasing your instructions."}

    os.makedirs(RESUME_OUT_DIR, exist_ok=True)
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M")
    label = re.sub(r"[^\w\-]", "_", (variant_name or "manual_edit").lower())[:30]
    out_dir = os.path.join(RESUME_OUT_DIR, f"{label}_{ts}")
    os.makedirs(os.path.join(out_dir, "sections"), exist_ok=True)

    for rel_path in set(files) | set(updated_files):
        content = updated_files.get(rel_path) or files.get(rel_path, "")
        out_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    zip_path = make_zip(out_dir, label)
    pdf_path, compile_log = compile_pdf(out_dir)

    variant_id = hashlib.md5(f"{label}_{ts}".encode()).hexdigest()[:16]
    db.save_variant({
        "id": variant_id,
        "job_id": "",
        "company": "",
        "title": variant_name or "Manual edit",
        "variant_name": variant_name or f"edit_{ts}",
        "out_dir": out_dir,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "job_score": 0,
        "created_at": datetime.now(IST).isoformat(),
    })

    return {
        "variant_id": variant_id,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "compile_log": compile_log if not pdf_path else None,
    }


def refine_variant(variant_id: str, feedback: str) -> dict:
    """Apply feedback to an already-tailored variant and produce a new one."""
    variant = db.get_variant(variant_id)
    if not variant:
        return {"error": f"Variant {variant_id} not found"}

    out_dir = variant.get("out_dir", "")
    if not out_dir or not os.path.isdir(out_dir):
        return {"error": "Variant output directory not found on disk"}

    # Load files from the tailored variant (not master) so we iterate on what was already changed
    files = {}
    for rel_path in list(TAILOR_TARGETS) + list(COPY_ONLY):
        abs_path = os.path.join(out_dir, rel_path)
        if os.path.exists(abs_path):
            with open(abs_path) as f:
                files[rel_path] = f.read()

    if not files:
        return {"error": "No LaTeX files found in variant directory"}

    target_content = {k: v for k, v in files.items() if k in TAILOR_TARGETS}
    files_block = "\n\n".join(
        f"### FILE: {path}\n```latex\n{content}\n```"
        for path, content in target_content.items()
    )
    prompt = REFINE_VARIANT_PROMPT_TEMPLATE.format(
        feedback=feedback.strip(),
        files_block=files_block,
    )
    raw = llm.chat(prompt, max_tokens=16000, temperature=0.35, task="tailor")

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    raw = _repair_latex_json(raw)

    try:
        updated_files = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"LLM returned invalid JSON: {e}\n{raw[:200]}"}

    updated_files = {k: v for k, v in updated_files.items() if k in TAILOR_TARGETS}
    if not updated_files:
        return {"error": "LLM returned no changed files. Try rephrasing your feedback."}

    ts = datetime.now(IST).strftime("%Y%m%d_%H%M")
    # Strip any previous timestamp suffix to keep directory names clean
    base_label = re.sub(r"_\d{8}_\d{4}(_r\d{8}_\d{4})*$", "", os.path.basename(out_dir))[:30]
    new_out_dir = os.path.join(RESUME_OUT_DIR, f"{base_label}_r{ts}")
    os.makedirs(os.path.join(new_out_dir, "sections"), exist_ok=True)

    for rel_path in set(files) | set(updated_files):
        content = updated_files.get(rel_path) or files.get(rel_path, "")
        out_path = os.path.join(new_out_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    zip_path = make_zip(new_out_dir, base_label)
    pdf_path, compile_log = compile_pdf(new_out_dir)

    new_variant_id = hashlib.md5(f"{base_label}_r{ts}".encode()).hexdigest()[:16]
    db.save_variant({
        "id": new_variant_id,
        "job_id": variant.get("job_id", ""),
        "company": variant.get("company", ""),
        "title": variant.get("title", ""),
        "variant_name": f"{variant.get('variant_name', 'variant')}_r{ts}",
        "out_dir": new_out_dir,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "job_score": variant.get("job_score", 0),
        "created_at": datetime.now(IST).isoformat(),
    })

    return {
        "variant_id": new_variant_id,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "company": variant.get("company", ""),
        "changed_files": list(updated_files.keys()),
        "compile_log": compile_log if not pdf_path else None,
    }


def fetch_jd(url):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:3000]
    except Exception as e:
        return f"Could not fetch: {e}"


def load_resume_files():
    files = {}
    if not os.path.isdir(RESUME_DIR):
        return files
    for rel_path in [*TAILOR_TARGETS, *COPY_ONLY]:
        abs_path = os.path.join(RESUME_DIR, rel_path)
        if os.path.exists(abs_path):
            with open(abs_path) as f:
                files[rel_path] = f.read()
    return files



def make_zip(out_dir, company):
    """Zip the output folder so it can be uploaded directly to Overleaf."""
    zip_path = out_dir + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, fnames in os.walk(out_dir):
            for fname in fnames:
                abs_path = os.path.join(root, fname)
                arcname = os.path.relpath(abs_path, out_dir)
                zf.write(abs_path, arcname)
    return zip_path


def compile_pdf(out_dir: str) -> tuple[str, str]:
    """Run latexmk to compile resume.tex to PDF. Returns (pdf_path, error_log)."""
    resume_tex = os.path.join(out_dir, "resume.tex")
    if not os.path.exists(resume_tex):
        return "", "resume.tex not found"
    try:
        result = subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-outdir=.", "resume.tex"],
            cwd=out_dir,
            capture_output=True,
            timeout=60,
            text=True,
        )
        pdf_path = os.path.join(out_dir, "resume.pdf")
        if os.path.exists(pdf_path):
            return pdf_path, ""
        return "", f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    except Exception as e:
        return "", str(e)


FIT_THRESHOLD = 35  # below this score, warn before tailoring


def check_fit(jd: str, title: str, company: str) -> tuple[int, str]:
    """Quick scoring call to assess fit before running the full tailor prompt."""
    candidate_profile = db.get_profile()
    data = llm.chat_json(
        f"""Score this job for the candidate (0-100).

CANDIDATE:
{candidate_profile}

JOB:
Title: {title}
Company: {company}
Description: {jd[:1000]}

Rules:
- Score 0 if role requires physical presence (onsite/in-office)
- Score 0 if requires 5+ years experience for a 2-year candidate
- Score based on tech stack overlap, seniority match, remote availability

Reply ONLY valid JSON: {{"score": <int>, "reason": "<max 120 chars>"}}""",
        max_tokens=80,
        task="score",
    )
    return int(data.get("score", 0)), str(data.get("reason", "no reason returned"))[:120]


def tailor(job_id=None, url=None, raw_jd=None, variant_name="", force=False):
    files = load_resume_files()
    if not files:
        return {"error": f"No resume files found at {RESUME_DIR}. Check volume mount."}

    if job_id:
        job = db.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}
        title, company = job["title"], job["company"]
        jd = job["description"] if len(job["description"]) > 200 else fetch_jd(job["url"])
        job_score = job.get("score", 0)
        # Use existing score if already computed, otherwise run a fresh fit check
        existing_score = job.get("score", -1)
        if existing_score >= 0:
            fit_score, fit_reason = existing_score, job.get("reason", "")
        else:
            fit_score, fit_reason = check_fit(jd, title, company)
    elif url:
        title, company = "Role", url.split("/")[2] if url.count("/") >= 2 else "company"
        jd = fetch_jd(url)
        job_score = 0
        if force:
            fit_score, fit_reason = 100, "forced"
        else:
            fit_score, fit_reason = check_fit(jd, title, company)

    elif raw_jd:
        title, company, jd = "Role", "Company", raw_jd
        job_score = 0
        if force:
            fit_score, fit_reason = 100, "forced"
        else:
            fit_score, fit_reason = check_fit(jd, title, company)
    else:
        return {"error": "Need job_id, url, or raw_jd"}

    # Warn if poor fit, unless the user explicitly forced past the warning
    if fit_score < FIT_THRESHOLD and not force:
        return {
            "fit_warning": True,
            "score": fit_score,
            "reason": fit_reason,
        }

    prompt = build_prompt(jd, title, company, files)

    raw = llm.chat(prompt, max_tokens=16000, temperature=0.35, task="tailor")

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    raw = _repair_latex_json(raw)

    try:
        updated_files = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"LLM returned invalid JSON: {e}\n{raw[:200]}"}

    updated_files = {k: v for k, v in updated_files.items() if k in TAILOR_TARGETS}

    # Write output folder
    os.makedirs(RESUME_OUT_DIR, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", company.lower())[:30]
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M")
    out_dir = os.path.join(RESUME_OUT_DIR, f"{safe}_{ts}")
    os.makedirs(os.path.join(out_dir, "sections"), exist_ok=True)

    for rel_path in set(files) | set(updated_files):
        content = updated_files.get(rel_path) or files.get(rel_path, "")
        out_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    zip_path = make_zip(out_dir, company)

    pdf_path, compile_log = compile_pdf(out_dir)

    variant_id = hashlib.md5(f"{company}_{ts}".encode()).hexdigest()[:16]

    db.save_variant({
        "id": variant_id,
        "job_id": job_id or "",
        "company": company,
        "title": title,
        "variant_name": variant_name or f"{safe}_{ts}",
        "out_dir": out_dir,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "job_score": job_score,
        "created_at": datetime.now(IST).isoformat(),
    })

    return {
        "variant_id": variant_id,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "out_dir": out_dir,
        "company": company,
        "title": title,
        "changed_files": list(updated_files.keys()),
        "compile_log": compile_log if not pdf_path else None,
    }
