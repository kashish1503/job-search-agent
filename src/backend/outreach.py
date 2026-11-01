"""
outreach.py — LinkedIn cold-email outreach module for OpenClaw

How scraping works:
  ScraperAPI is used to fetch Google search results for LinkedIn profiles.
  Query: site:linkedin.com/in "Engineering Manager" "stripe.com" -jobs -job
  This returns LinkedIn profile URLs + names from Google snippets.

No LinkedIn login required. ScraperAPI handles IP rotation + JS rendering.
"""

import os
import re
import time
import json
import smtplib
import hashlib
import sqlite3
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "/app/data/jobs.db")


# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_outreach_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS outreach_contacts (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            first_name  TEXT,
            last_name   TEXT,
            title       TEXT,
            company     TEXT,
            email       TEXT,
            linkedin_url TEXT DEFAULT '',
            email_pattern TEXT DEFAULT '',
            status      TEXT DEFAULT 'new',
            scraped_at  TEXT,
            sent_at     TEXT DEFAULT '',
            reply       INTEGER DEFAULT 0,
            notes       TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS outreach_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT UNIQUE,
            subject     TEXT,
            body        TEXT,
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS outreach_config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    # Seed a default template if none exist
    existing = conn.execute("SELECT COUNT(*) FROM outreach_templates").fetchone()[0]
    if existing == 0:
        from datetime import datetime
        conn.execute("""
            INSERT INTO outreach_templates (name, subject, body, created_at) VALUES (?, ?, ?, ?)
        """, (
            "Default Cold Outreach",
            "Quick question about {{company}}",
            """Hi {{first_name}},

I came across your profile and was impressed by your work at {{company}}.

I'm a full-stack engineer (React/TypeScript, Node, Python) with experience building scalable products. I'm currently exploring new opportunities and would love to learn more about what your team is working on.

Would you be open to a quick 15-minute chat?

Best,
{{sender_name}}""",
            datetime.utcnow().isoformat()
        ))
    conn.commit()
    conn.close()


# ─── Email pattern generator ─────────────────────────────────────────────────

def generate_email(first: str, last: str, domain: str, pattern: str) -> str:
    f = first.lower().strip()
    l = last.lower().strip()
    f1 = f[0] if f else ""
    l1 = l[0] if l else ""
    patterns = {
        "firstname.lastname": f"{f}.{l}@{domain}",
        "f.lastname":         f"{f1}.{l}@{domain}",
        "firstnamelastname":  f"{f}{l}@{domain}",
        "firstname_lastname": f"{f}_{l}@{domain}",
        "firstname":          f"{f}@{domain}",
        "flastname":          f"{f1}{l}@{domain}",
    }
    return patterns.get(pattern, f"{f}.{l}@{domain}")


def split_name(full_name: str):
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return parts[0] if parts else "", ""


# ─── ScraperAPI scraping ──────────────────────────────────────────────────────

def scrape_linkedin_people(
    company: str,
    designation: str,
    location: str,
    email_domain: str,
    pages: int,
    scraper_api_key: str,
    email_pattern: str,
    provider: str = "serper",
) -> dict:
    """
    Scrape LinkedIn profiles via Google using one of three providers.
    Providers: "serper" (Serper.dev), "scraperapi" (ScraperAPI), "hunter" (Hunter.io)
    Returns {"contacts": [...], "errors": [...]}
    """
    if provider == "hunter":
        return _scrape_via_hunter(company, designation, email_domain, email_pattern, pages, scraper_api_key)
    elif provider == "scraperapi":
        return _scrape_via_scraperapi(company, designation, location, email_domain, pages, scraper_api_key, email_pattern)
    else:  # default: serper
        return _scrape_via_serper(company, designation, location, email_domain, pages, scraper_api_key, email_pattern)


def _build_linkedin_query(company: str, designation: str, location: str) -> str:
    location_str = f' "{location}"' if location.strip() else ""
    return f'site:linkedin.com/in "{designation}" "{company}"{location_str}'


def _scrape_via_serper(company, designation, location, email_domain, pages, api_key, email_pattern) -> dict:
    """
    Serper.dev — best free option: 2,500 free searches on signup.
    Returns clean structured JSON — no HTML parsing needed.
    Sign up: https://serper.dev
    """
    contacts = []
    errors = []
    query = _build_linkedin_query(company, designation, location)

    for page in range(pages):
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": 10, "start": page * 10},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            organic = data.get("organic", [])

            for item in organic:
                title = item.get("title", "")
                link = item.get("link", "")
                if "linkedin.com/in/" not in link:
                    continue
                name, title_role = _parse_linkedin_title(title)
                first, last = split_name(name)
                if not first or not last:
                    continue
                email = generate_email(first, last, email_domain, email_pattern)
                cid = hashlib.md5(email.encode()).hexdigest()[:12]
                from datetime import datetime
                contacts.append({
                    "id": cid, "name": name, "first_name": first, "last_name": last,
                    "title": title_role or designation, "company": company,
                    "email": email, "linkedin_url": link,
                    "email_pattern": email_pattern, "status": "new",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
        except requests.exceptions.RequestException as e:
            errors.append(f"Serper page {page+1}: {e}")
            break
        if page < pages - 1:
            time.sleep(1.0)

    return {"contacts": _dedup(contacts), "errors": errors}


def _scrape_via_scraperapi(company, designation, location, email_domain, pages, api_key, email_pattern) -> dict:
    """ScraperAPI — scrapes Google HTML. 7-day trial."""
    contacts = []
    errors = []
    query = _build_linkedin_query(company, designation, location)

    for page in range(pages):
        try:
            resp = requests.get(
                "https://api.scraperapi.com/",
                params={
                    "api_key": api_key,
                    "url": f"https://www.google.com/search?q={requests.utils.quote(query)}&start={page*10}&num=10",
                    "render": "false", "country_code": "us",
                },
                timeout=30,
            )
            resp.raise_for_status()
            parsed = _parse_google_linkedin_results(resp.text, company, designation, email_domain, email_pattern)
            contacts.extend(parsed)
        except requests.exceptions.RequestException as e:
            errors.append(f"ScraperAPI page {page+1}: {e}")
            break
        if page < pages - 1:
            time.sleep(1.5)

    return {"contacts": _dedup(contacts), "errors": errors}


def _scrape_via_hunter(company, designation, email_domain, email_pattern, pages, api_key) -> dict:
    """
    Hunter.io domain search — directly finds VERIFIED emails for a company.
    No LinkedIn scraping needed. 25 free domain searches/month.
    Sign up: https://hunter.io
    """
    contacts = []
    errors = []
    per_page = 10

    for page in range(pages):
        try:
            resp = requests.get(
                "https://api.hunter.io/v2/domain-search",
                params={
                    "domain": email_domain,
                    "api_key": api_key,
                    "limit": per_page,
                    "offset": page * per_page,
                    "seniority": "senior,executive,director,vp",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            emails_data = data.get("emails", [])

            if not emails_data:
                if page == 0:
                    errors.append(f"No emails found for domain: {email_domain}")
                break

            from datetime import datetime
            for item in emails_data:
                first = (item.get("first_name") or "").strip()
                last = (item.get("last_name") or "").strip()
                if not first or not last:
                    continue
                # Hunter gives us the real email directly
                email = item.get("value", generate_email(first, last, email_domain, email_pattern))
                title = item.get("position") or designation
                name = f"{first} {last}"
                li_url = ""
                for src in item.get("sources", []):
                    if "linkedin.com" in src.get("uri", ""):
                        li_url = src["uri"]
                        break
                cid = hashlib.md5(email.encode()).hexdigest()[:12]
                contacts.append({
                    "id": cid, "name": name, "first_name": first, "last_name": last,
                    "title": title, "company": company, "email": email,
                    "linkedin_url": li_url, "email_pattern": "verified",
                    "status": "new", "scraped_at": datetime.utcnow().isoformat(),
                })
        except requests.exceptions.RequestException as e:
            errors.append(f"Hunter page {page+1}: {e}")
            break
        if page < pages - 1:
            time.sleep(0.5)

    return {"contacts": _dedup(contacts), "errors": errors}


def _dedup(contacts: list) -> list:
    seen = set()
    out = []
    for c in contacts:
        if c["email"] not in seen:
            seen.add(c["email"])
            out.append(c)
    return out


def _parse_linkedin_title(title: str):
    """Parse 'John Smith - Engineering Manager at Stripe | LinkedIn'"""
    title = title.replace("| LinkedIn", "").replace("- LinkedIn", "").strip()
    # Remove " at Company" suffix from role
    title = re.sub(r' at [^\-|]+', '', title)
    parts = [p.strip() for p in re.split(r' [-–|] ', title)]
    name = parts[0] if parts else ""
    role = parts[1] if len(parts) > 1 else ""
    return name, role


def _parse_google_linkedin_results(html: str, company: str, designation: str, domain: str, pattern: str) -> list:
    """Extract name, title, LinkedIn URL from Google HTML.

    Uses position-based pairing: for each h3 result title, look backwards in the
    HTML for the nearest LinkedIn URL within a search-result block (~2000 chars).
    This avoids the index-drift bug caused by extra LinkedIn URLs elsewhere on the
    page (navigation, footer, cited links, etc.).
    """
    from datetime import datetime
    results = []

    def clean_html(s):
        return re.sub(r'<[^>]+>', '', s).strip()

    def parse_title_line(text):
        text = text.replace("| LinkedIn", "").replace("- LinkedIn", "").strip()
        parts = [p.strip() for p in text.split(" - ")]
        name = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else designation
        return name, title

    # ── Step 1: Find all h3 result-title positions ────────────────────────────
    # Google uses class "LC20lb" for result titles; also catch any h3 as fallback.
    h3_re = re.compile(r'<h3[^>]*>(.*?)</h3>', re.DOTALL | re.IGNORECASE)

    # ── Step 2: Find all LinkedIn profile URL positions ───────────────────────
    # Match both direct hrefs and Google's /url?q= redirect format.
    url_re = re.compile(
        r'href="(?:/url\?q=)?(https?://(?:www\.)?linkedin\.com/in/[\w\-]+)[^"]*"',
        re.IGNORECASE,
    )
    # Build a sorted list of (position, url) so we can do nearest-lookup
    all_urls = [(m.start(), m.group(1)) for m in url_re.finditer(html)]

    used_urls: set = set()

    for h3_match in h3_re.finditer(html):
        h3_pos = h3_match.start()
        h3_text = clean_html(h3_match.group(1))
        name, title = parse_title_line(h3_text)
        if not name:
            continue
        first, last = split_name(name)
        if not first or not last:
            continue

        # Find the nearest LinkedIn URL that appears BEFORE this h3
        # but within a reasonable search-result block window (~2000 chars).
        best_url = ""
        for url_pos, url in reversed(all_urls):  # reversed = start from closest
            if url_pos < h3_pos and (h3_pos - url_pos) <= 2000:
                if url not in used_urls:
                    best_url = url
                    break

        if best_url in used_urls:
            best_url = ""
        if best_url:
            used_urls.add(best_url)

        email = generate_email(first, last, domain, pattern)
        contact_id = hashlib.md5(email.encode()).hexdigest()[:12]
        results.append({
            "id": contact_id,
            "name": name,
            "first_name": first,
            "last_name": last,
            "title": title,
            "company": company,
            "email": email,
            "linkedin_url": best_url,
            "email_pattern": pattern,
            "status": "new",
            "scraped_at": datetime.utcnow().isoformat(),
        })

    return results


# ─── DB operations ────────────────────────────────────────────────────────────

def save_contacts(contacts: list) -> int:
    """Insert contacts, skip duplicates. Returns count inserted."""
    conn = get_conn()
    inserted = 0
    for c in contacts:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO outreach_contacts
                (id, name, first_name, last_name, title, company, email,
                 linkedin_url, email_pattern, status, scraped_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                c["id"], c["name"], c["first_name"], c["last_name"],
                c["title"], c["company"], c["email"], c["linkedin_url"],
                c["email_pattern"], c["status"], c["scraped_at"],
            ))
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted


def get_contacts(status: Optional[str] = None, company: Optional[str] = None) -> list:
    conn = get_conn()
    q = "SELECT * FROM outreach_contacts WHERE 1=1"
    params = []
    if status:
        q += " AND status = ?"
        params.append(status)
    if company:
        q += " AND company LIKE ?"
        params.append(f"%{company}%")
    q += " ORDER BY scraped_at DESC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return rows


def update_contact_status(contact_id: str, status: str, sent_at: str = ""):
    conn = get_conn()
    conn.execute(
        "UPDATE outreach_contacts SET status=?, sent_at=? WHERE id=?",
        (status, sent_at, contact_id)
    )
    conn.commit()
    conn.close()


def delete_contact(contact_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM outreach_contacts WHERE id=?", (contact_id,))
    conn.commit()
    conn.close()


# ─── Templates ────────────────────────────────────────────────────────────────

def get_templates() -> list:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM outreach_templates ORDER BY id").fetchall()]
    conn.close()
    return rows


def save_template(name: str, subject: str, body: str) -> int:
    from datetime import datetime
    conn = get_conn()
    conn.execute("""
        INSERT INTO outreach_templates (name, subject, body, created_at)
        VALUES (?,?,?,?)
        ON CONFLICT(name) DO UPDATE SET subject=excluded.subject, body=excluded.body
    """, (name, subject, body, datetime.utcnow().isoformat()))
    conn.commit()
    tid = conn.execute("SELECT id FROM outreach_templates WHERE name=?", (name,)).fetchone()[0]
    conn.close()
    return tid


def delete_template(template_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM outreach_templates WHERE id=?", (template_id,))
    conn.commit()
    conn.close()


# ─── Email sending ────────────────────────────────────────────────────────────

def render_template(template: str, contact: dict, sender_name: str) -> str:
    t = template
    t = t.replace("{{name}}", contact.get("name", ""))
    t = t.replace("{{first_name}}", contact.get("first_name", ""))
    t = t.replace("{{last_name}}", contact.get("last_name", ""))
    t = t.replace("{{company}}", contact.get("company", ""))
    t = t.replace("{{title}}", contact.get("title", ""))
    t = t.replace("{{sender_name}}", sender_name)
    return t


def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    sender_name: str,
    to_email: str,
    subject: str,
    body: str,
) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{smtp_user}>"
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[outreach] email send error: {e}")
        return False


def send_bulk(
    contact_ids: list,
    template_id: int,
    smtp_config: dict,
    sender_name: str,
    delay_seconds: float = 3.0,
) -> dict:
    """
    Send emails to a list of contact_ids using a template.
    Returns {"sent": N, "failed": N, "errors": [...]}
    """
    from datetime import datetime, timezone

    templates = {t["id"]: t for t in get_templates()}
    tpl = templates.get(template_id)
    if not tpl:
        return {"sent": 0, "failed": 0, "errors": [f"Template {template_id} not found"]}

    conn = get_conn()
    contacts = {
        r["id"]: dict(r)
        for r in conn.execute(
            f"SELECT * FROM outreach_contacts WHERE id IN ({','.join('?'*len(contact_ids))})",
            contact_ids
        ).fetchall()
    }
    conn.close()

    sent = 0
    failed = 0
    errors = []

    for cid in contact_ids:
        contact = contacts.get(cid)
        if not contact:
            errors.append(f"Contact {cid} not found")
            failed += 1
            continue

        subject = render_template(tpl["subject"], contact, sender_name)
        body = render_template(tpl["body"], contact, sender_name)

        ok = send_email(
            smtp_config["host"],
            smtp_config["port"],
            smtp_config["user"],
            smtp_config["password"],
            sender_name,
            contact["email"],
            subject,
            body,
        )

        now = datetime.now(timezone.utc).isoformat()
        if ok:
            update_contact_status(cid, "sent", now)
            sent += 1
        else:
            errors.append(f"Failed: {contact['email']}")
            failed += 1

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return {"sent": sent, "failed": failed, "errors": errors}