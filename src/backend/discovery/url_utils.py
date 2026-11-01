from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "gh_jid", "gh_src")


def normalize_url(url: str) -> dict:
    raw = (url or "").strip()
    if not raw:
        return {"original_url": "", "canonical_url": "", "job_id": ""}

    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not any(k.lower().startswith(prefix) for prefix in TRACKING_PREFIXES)
    ]
    path = parsed.path.rstrip("/") or "/"
    canonical = urlunparse(
        (
            parsed.scheme.lower() or "https",
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query_pairs, doseq=True),
            "",
        )
    )
    job_id = hashlib.md5(canonical.encode()).hexdigest()[:16]
    return {"original_url": url, "canonical_url": canonical, "job_id": job_id}
