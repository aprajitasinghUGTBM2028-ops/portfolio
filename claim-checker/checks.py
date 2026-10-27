"""
checks.py: deterministic logic. No network calls and no LLM calls in this file.

Everything a model says passes through functions here before a user sees it:
  - quotes are verified against the source text they claim to come from
  - "independent" is decided from domains, never by the model
  - scores and the verdict are computed from visible facts
  - hooks are validated (numbers must come from cited facts, self-reported
    numbers must be attributed, no unanswered questions)
"""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

STATUSES = (
    "OBSERVED",
    "INDEPENDENT",
    "CONTRADICTED",
    "UNCHECKED",
    "SITE_SAYS",
    "REEL_SAYS",
    "UNVERIFIABLE",
)

_PATH_TENANT = {"github.com", "gitlab.com", "x.com", "reddit.com", "medium.com",
                "dev.to", "youtube.com", "linkedin.com", "instagram.com",
                "huggingface.co", "tiktok.com"}
_SUBDOMAIN_TENANT = {"github.io", "vercel.app", "netlify.app", "pages.dev",
                     "notion.site", "substack.com", "blogspot.com", "medium.com"}
_TWO_PART_TLDS = {"co.uk", "com.au", "co.in", "com.br", "co.jp", "org.uk", "co.nz"}


# ── URLs ─────────────────────────────────────────────────────────────

def strip_tracking(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    p = urlparse(url.strip())
    keep = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not (k.lower().startswith(("utm_", "mc_")) or k.lower() in
                    {"ref", "ref_src", "fbclid", "gclid", "igshid", "srsltid"})]
    return urlunparse(p._replace(query=urlencode(keep), fragment=""))


def domain_of(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return "x.com" if host in ("twitter.com", "mobile.twitter.com") else host


def registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _TWO_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def first_segment(url: str) -> str:
    segs = [s for s in urlparse(url or "").path.split("/") if s]
    return segs[0].lower() if segs else ""


def owner_key(url: str) -> str:
    host = domain_of(url)
    if not host:
        return ""
    reg = registrable(host)
    if reg in _SUBDOMAIN_TENANT:
        return host
    if reg in _PATH_TENANT:
        return f"{reg}/{first_segment(url)}"
    return reg


def is_independent(source_url: str, tool_url: str, own_names=()) -> bool:
    a, b = owner_key(source_url), owner_key(tool_url)
    if not a or not b or a == b:
        return False
    if domain_of(source_url) and registrable(domain_of(source_url)) in _PATH_TENANT:
        if first_segment(source_url) in {n.lower() for n in own_names if n}:
            return False
    return True


# ── Text matching ────────────────────────────────────────────────────

_QUOTE_MAP = {"‘": "'", "’": "'", "“": '"', "”": '"',
              "–": "-", "—": "-", " ": " ", "​": ""}


def norm(text: str) -> str:
    t = text or ""
    for k, v in _QUOTE_MAP.items():
        t = t.replace(k, v)
    t = re.sub(r"[*_`#>|]", "", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def quote_in_text(quote: str, text: str, min_len: int = 12) -> bool:
    if not quote or not text:
        return False
    parts = [norm(p) for p in re.split(r"…|\.\.\.", quote)]
    parts = [p for p in parts if len(p) >= min_len]
    if not parts:
        return False
    hay = norm(text)
    return all(p in hay for p in parts)


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?[kKmMbB]?")


def numbers_in(text: str) -> set:
    return {m.replace(",", "").lower() for m in _NUM.findall(text or "") if m.strip(",")}


def parse_json_loose(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError("no text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object found")
    obj = json.loads(m.group(0))
    if not isinstance(obj, dict):
        raise ValueError("JSON is not an object")
    return obj


# ── Dates ────────────────────────────────────────────────────────────

_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y/%m/%d")


def parse_date(s) -> date | None:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        s = m.group(1)
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def within_days(d: date | None, today: date, days: int = 30) -> bool:
    return d is not None and 0 <= (today - d).days <= days


# ── Scores: computed from facts, never guessed by a model ────────────

def clamp(x, lo, hi):
    try:
        return max(lo, min(hi, int(x)))
    except (TypeError, ValueError):
        return lo


def browse_score(free_to_browse, needs_account) -> dict:
    reasons = []
    if free_to_browse is False:
        return {"score": 1, "reasons": ["not free to browse"]}
    s = 5
    if free_to_browse is None:
        s -= 1
        reasons.append("browsing access not stated")
    if needs_account is True:
        s -= 1
        reasons.append("needs account signup")
    elif needs_account is None:
        s -= 1
        reasons.append("account requirement not stated")
    return {"score": clamp(s, 1, 5), "reasons": reasons}


def create_score(paid_dep, needs_code, setup_minutes) -> dict:
    reasons = []
    s = 5
    if paid_dep is True:
        s -= 2
        reasons.append("needs a paid service")
    elif paid_dep is None:
        s -= 1
        reasons.append("paid dependency not stated")
    if needs_code is True:
        s -= 1
        reasons.append("needs coding")
    elif needs_code is None:
        s -= 1
        reasons.append("coding requirement not stated")
    if isinstance(setup_minutes, (int, float)) and setup_minutes > 30:
        s -= 1
        reasons.append(f"setup takes ~{int(setup_minutes)} min")
    return {"score": clamp(s, 1, 5), "reasons": reasons}


def crowdedness(n_alternatives, search_ok=True) -> dict:
    if not search_ok:
        return {"label": "unknown", "reason": "search could not check alternatives"}
    if n_alternatives == 0:
        return {"label": "unknown", "reason": "no alternatives surfaced in search"}
    if n_alternatives == 1:
        return {"label": "low", "reason": "1 alternative found"}
    if n_alternatives <= 4:
        return {"label": "medium", "reason": f"{n_alternatives} alternatives found"}
    return {"label": "high", "reason": f"{n_alternatives}+ alternatives found"}


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def lookalike_domains(tool_url: str, candidates) -> list:
    tool_reg = registrable(domain_of(tool_url))
    stem = tool_reg.split(".")[0].replace("-", "")
    out = []
    for c in candidates or []:
        host = domain_of(c if "//" in str(c) else f"https://{c}")
        reg = registrable(host)
        if not reg or reg == tool_reg:
            continue
        s = reg.split(".")[0].replace("-", "")
        if s and stem and (s == stem or (levenshtein(s, stem) <= 2 and len(stem) >= 6)):
            if reg not in out:
                out.append(reg)
    return out


# ── Claim verdicts and the content verdict ───────────────────────────

def claim_verdict(claim: dict, facts_by_id: dict, supports, contradicts, search_ok: bool):
    sup = [i for i in (supports or []) if i in facts_by_id]
    con = [i for i in (contradicts or []) if i in facts_by_id]
    con_ok = [i for i in con if facts_by_id[i]["status"] in ("INDEPENDENT", "OBSERVED")]
    if con_ok:
        return "CONTRADICTED", con_ok
    for want in ("INDEPENDENT", "OBSERVED", "UNCHECKED"):
        ids = [i for i in sup if facts_by_id[i]["status"] == want]
        if ids:
            return want, ids
    if claim.get("origin") == "reel":
        return "REEL_SAYS", []
    if claim.get("category") in ("performance", "popularity") and search_ok:
        return "UNVERIFIABLE", []
    return "SITE_SAYS", []


def decide_verdict(s: dict):
    if not s.get("search_ok", False):
        return "INSUFFICIENT EVIDENCE", "The search step failed, so independent evidence was not checked."
    if s.get("n_official", 0) < 3:
        return "INSUFFICIENT EVIDENCE", "Fewer than 3 verified facts came from the tool's own pages."
    if s.get("n_contradicted", 0) > 0:
        return "COVER THE GAP", "An independent or observed fact contradicts at least one claim."
    if s.get("paid_dep") and s.get("claims_free"):
        return "COVER THE GAP", "The tool is described as free, but using it needs a paid service."
    if s.get("n_independent", 0) == 0 and s.get("n_self_reported_numbers", 0) >= 2:
        return "INSUFFICIENT EVIDENCE", "The headline numbers come only from the tool's own pages — no independent source verified them."
    if s.get("n_independent", 0) == 0:
        return "INSUFFICIENT EVIDENCE", "No independent source could be verified."
    if s.get("create", 5) <= 1 and s.get("browse", 5) <= 2:
        return "SKIP", "Hard to try for free and hard to create with."
    if s.get("crowded") == "high" and s.get("fresh30", 0) == 0 and s.get("n_independent", 0) < 2:
        return "SKIP", "Crowded space, no recent coverage, and little independent evidence."
    return "COVER IT", (f"{s.get('n_independent', 0)} verified independent source(s) and "
                        "no contradictions found.")


# ── Hooks ────────────────────────────────────────────────────────────

SITE_PHRASES = ("the site says", "site says", "the site claims", "site claims",
                "they say", "they claim", "claims", "says it", "its own", "self-reported")


def validate_hook(hook: dict, facts_by_id: dict) -> dict:
    text = str((hook or {}).get("text", "")).strip()
    htype = str((hook or {}).get("type", "data")).lower()
    ids = [i for i in (hook or {}).get("fact_ids", []) if isinstance(i, str)]
    out = {"ok": False, "reason": "", "text": text, "type": htype, "fact_ids": ids}
    if not 20 <= len(text) <= 300:
        out["reason"] = "wrong length"
        return out
    if text.endswith("?"):
        out["reason"] = "ends with an unanswered question"
        return out
    if not ids or any(i not in facts_by_id for i in ids):
        out["reason"] = "cites a fact id that does not exist"
        return out
    cited = [facts_by_id[i] for i in ids]
    nums = numbers_in(text)
    allowed = set().union(*[numbers_in(f["text"]) for f in cited])
    stray = nums - allowed
    if stray:
        out["reason"] = f"numbers not found in cited facts: {', '.join(sorted(stray))}"
        return out
    solid = set().union(*[numbers_in(f["text"]) for f in cited
                          if f["status"] in ("INDEPENDENT", "OBSERVED")] or [set()])
    self_only = nums - solid
    if self_only and not any(p in text.lower() for p in SITE_PHRASES):
        out["reason"] = "uses a self-reported number without saying whose number it is"
        return out
    out["ok"] = True
    return out


def pick_hooks(validated: list, keep: int = 3) -> list:
    good = [h for h in validated if h["ok"]]
    chosen, seen = [], set()
    for h in good:
        if h["type"] not in seen:
            chosen.append(h)
            seen.add(h["type"])
    for h in good:
        if len(chosen) >= keep:
            break
        if h not in chosen:
            chosen.append(h)
    return chosen[:keep]


def numbers_supported(text: str, cited_texts, extra_ok=()) -> list:
    allowed = set(extra_ok)
    for t in cited_texts:
        allowed |= numbers_in(t)
    return sorted(numbers_in(text) - allowed)


def remove_sentence(text: str, excerpt: str):
    if not text or not excerpt or norm(excerpt) not in norm(text):
        return text, False
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if norm(excerpt) not in norm(s)]
    return " ".join(kept).strip(), len(kept) != len(sentences)


# ── Safety helpers ───────────────────────────────────────────────────

def is_thin(text: str, minimum: int = 300) -> bool:
    return len((text or "").strip()) < minimum


def fence_text(text: str) -> str:
    t = (text or "").encode("utf-8", errors="replace").decode("utf-8").replace("\x00", "")
    return re.sub(r"<\s*/?\s*data", lambda m: m.group(0).replace("<", "&lt;"), t, flags=re.I)


def redact_secrets(msg: str) -> str:
    msg = re.sub(r"sk-[A-Za-z0-9_\-]{6,}", "sk-[redacted]", str(msg))
    return re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", msg)


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))
