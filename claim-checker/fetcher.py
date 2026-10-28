"""
fetcher.py: collects evidence. Plain code, no LLM.

Returns a dict:
  {ok, kind, url, title, pages:[{url,text}], text, thin, login_wall, error, meta}
`kind` is one of: github, web, instagram.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from checks import domain_of, is_thin, strip_tracking

UA = {"User-Agent": "Mozilla/5.0 (compatible; ClaimChecker/2.0)"}
TIMEOUT = 12
MAX_BYTES = 1_500_000
PER_PAGE_CHARS = 3000
TOTAL_CHARS = 20000
MAX_SUBPAGES = 5
SUBPAGE_KEYWORDS = ("pricing", "price", "plans", "faq", "docs", "about", "sponsor",
                    "how", "features", "install", "getting-started", "terms")
LOGIN_WALL_MARKERS = ("log in to continue", "login to continue", "sign up to see",
                      "create an account to", "please log in", "see more from")


class FetchError(Exception):
    pass


# ── safety: no private networks, bounded sizes ───────────────────────

def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def validate_url(url: str) -> str:
    url = strip_tracking((url or "").strip())
    if url and "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("That does not look like a valid http(s) link.")
    if not _host_is_public(p.hostname):
        raise FetchError("That address is not a public website, so it was not fetched.")
    return url


def _get(url: str, headers=None, hops: int = 4) -> requests.Response:
    for _ in range(hops + 1):
        url = validate_url(url)
        try:
            r = requests.get(url, headers={**UA, **(headers or {})}, timeout=TIMEOUT,
                             allow_redirects=False, stream=True)
        except requests.RequestException as e:
            raise FetchError(f"Could not reach the site ({type(e).__name__}).") from e
        if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, r.headers.get("Location", ""))
            continue
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                break
        r._content = body
        r.encoding = r.apparent_encoding or "utf-8"
        r.url = url
        return r
    raise FetchError("Too many redirects.")


# ── HTML → text ──────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8").replace("\x00", "")


def html_to_text(html_text: str):
    soup = BeautifulSoup(_clean(html_text), "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe"]):
        t.decompose()
    title = _clean((soup.title.string or "").strip()) if soup.title and soup.title.string else ""
    text = soup.get_text("\n", strip=True)
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    return title, _clean("\n".join(lines)), soup


def _pick_subpages(soup, base_url: str):
    base_dom = domain_of(base_url)
    scored, seen = [], {strip_tracking(base_url).rstrip("/")}
    for a in soup.find_all("a", href=True):
        link = strip_tracking(urljoin(base_url, a["href"])).rstrip("/")
        if link in seen or domain_of(link) != base_dom or not link.startswith("http"):
            continue
        seen.add(link)
        label = (a.get_text(" ", strip=True) + " " + urlparse(link).path).lower()
        hits = [i for i, k in enumerate(SUBPAGE_KEYWORDS) if k in label]
        if hits:
            scored.append((min(hits), link))
    scored.sort()
    return [u for _, u in scored[:MAX_SUBPAGES]]


def _budget(pages):
    if not pages:
        return []
    per = max(500, TOTAL_CHARS // max(len(pages), 1))
    out, used = [], 0
    for p in pages:
        t = p["text"][:per]
        if used + len(t) > TOTAL_CHARS:
            t = t[: max(0, TOTAL_CHARS - used)]
        if t:
            out.append({"url": p["url"], "text": t})
            used += len(t)
    return out


def _result(kind, url, **kw):
    base = {"ok": True, "kind": kind, "url": url, "title": "", "pages": [], "text": "",
            "thin": False, "login_wall": False, "error": "", "meta": {}}
    base.update(kw)
    base["text"] = "\n\n".join(f"[{p['url']}]\n{p['text']}" for p in base["pages"])
    return base


def _fail(kind, url, msg):
    return _result(kind, url, ok=False, error=msg)


# ── web pages ────────────────────────────────────────────────────────

def fetch_web(url: str) -> dict:
    try:
        r = _get(url)
    except FetchError as e:
        return _fail("web", url, str(e))
    if r.status_code >= 400:
        return _fail("web", url, f"The site answered with HTTP {r.status_code}.")
    ctype = r.headers.get("Content-Type", "")
    if "html" not in ctype and "text" not in ctype:
        return _fail("web", url, "The link is not a web page.")
    title, text, soup = html_to_text(r.text)
    pages = [{"url": r.url, "text": text}]
    for sub in _pick_subpages(soup, r.url):
        try:
            sr = _get(sub)
            if sr.status_code < 400 and "html" in sr.headers.get("Content-Type", ""):
                _, st, _ = html_to_text(sr.text)
                if st:
                    pages.append({"url": sr.url, "text": st})
        except FetchError:
            continue
    pages = _budget(pages)
    joined = " ".join(p["text"] for p in pages)
    low = joined.lower()
    return _result("web", r.url, title=title, pages=pages, thin=is_thin(joined),
                   login_wall=any(m in low for m in LOGIN_WALL_MARKERS))


# ── GitHub ───────────────────────────────────────────────────────────

def _gh_headers():
    tok = os.environ.get("GITHUB_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def parse_github(url: str):
    p = urlparse(url)
    if (p.hostname or "").lower().replace("www.", "") != "github.com":
        return None
    segs = [s for s in p.path.split("/") if s]
    return (segs[0], segs[1].removesuffix(".git")) if len(segs) >= 2 else None


def fetch_github(url: str) -> dict:
    ref = parse_github(url)
    if not ref:
        return _fail("github", url, "Not a GitHub repository link.")
    owner, repo = ref
    api = f"https://api.github.com/repos/{owner}/{repo}"
    meta = {"owner": owner, "repo": repo}
    try:
        r = _get(api, headers=_gh_headers())
        if r.status_code == 404:
            return _fail("github", url, "Repository not found (or private).")
        if r.status_code == 200:
            j = r.json()
            meta.update(stars=j.get("stargazers_count"), forks=j.get("forks_count"),
                        pushed_at=j.get("pushed_at"), created_at=j.get("created_at"),
                        license=(j.get("license") or {}).get("spdx_id"),
                        description=j.get("description"), archived=j.get("archived"),
                        homepage=j.get("homepage"))
        readme = ""
        rr = _get(api + "/readme", headers={**_gh_headers(),
                                            "Accept": "application/vnd.github.raw+json"})
        if rr.status_code == 200:
            readme = rr.text
        else:
            for branch in ("main", "master"):
                raw = _get(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md")
                if raw.status_code == 200:
                    readme = raw.text
                    break
    except FetchError as e:
        return _fail("github", url, str(e))
    pages = [{"url": f"https://github.com/{owner}/{repo}", "text": readme}]
    facts = "; ".join(f"{k}={v}" for k, v in meta.items() if v not in (None, "") and k not in ("owner", "repo"))
    if facts:
        pages.insert(0, {"url": api, "text": f"GitHub API fields: {facts}"})
    pages = _budget(pages)
    return _result("github", f"https://github.com/{owner}/{repo}", title=f"{owner}/{repo}",
                   pages=pages, thin=is_thin(readme, 200), meta=meta)


# ── Instagram: only user supplied text is trusted ────────────────────

def fetch_instagram(url: str, caption: str = "", on_screen: str = "", notes: str = "") -> dict:
    parts = [("caption", caption), ("on-screen text", on_screen), ("notes", notes)]
    text = "\n".join(f"{k}: {v.strip()}" for k, v in parts if v and v.strip())
    if is_thin(text, 20):
        return _fail("instagram", url,
                     "Instagram does not allow automatic reading. Paste the reel's caption "
                     "(and any on-screen text) and run it again.")
    return _result("instagram", strip_tracking(url), title="Instagram reel",
                   pages=[{"url": strip_tracking(url), "text": text}], thin=is_thin(text, 80),
                   meta={"source": "user_supplied"})


def fetch(url: str, caption: str = "", on_screen: str = "") -> dict:
    host = domain_of(url if "//" in url else "https://" + url)
    if host.endswith("instagram.com"):
        return fetch_instagram(url, caption, on_screen)
    if host == "github.com":
        return fetch_github(validate_url(url)) if parse_github(url) else fetch_web(url)
    return fetch_web(url)
