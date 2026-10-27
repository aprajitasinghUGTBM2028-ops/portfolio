"""
fetcher.py — Fetches and extracts text content from URLs.
Handles: landing pages, GitHub READMEs, and generic web pages.
Deep-fetches internal links one level deep (blog, pricing, docs, etc.).
"""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urlunparse, parse_qs, urlencode


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15

SUBPAGE_KEYWORDS = [
    "pricing", "price", "plan", "blog", "about", "docs", "documentation",
    "customize", "templates", "template", "sponsor", "faq", "features",
    "changelog", "analysis", "report", "review", "guide",
]


def strip_utm(url: str) -> str:
    """Remove UTM and tracking parameters from a URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=False)
    clean = {k: v for k, v in params.items()
             if not k.lower().startswith(("utm_", "ref", "source", "fbclid", "gclid"))}
    cleaned_query = urlencode(clean, doseq=True)
    return urlunparse(parsed._replace(query=cleaned_query))


def classify_url(url: str) -> str:
    """Classify a URL into a type: github, instagram, or web."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if "github.com" in host:
        return "github"
    if "instagram.com" in host:
        return "instagram"
    return "web"


def fetch_github(url: str) -> dict:
    """Fetch README content from a GitHub repo using the API, with raw fallback."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        return {"ok": False, "error": "Invalid GitHub URL — need owner/repo format."}

    owner, repo = parts[0], parts[1]
    readme_text = ""
    meta = {}

    # Try API first, fall back to raw URL
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    try:
        resp = requests.get(api_url, headers={
            **HEADERS, "Accept": "application/vnd.github.v3.raw"
        }, timeout=TIMEOUT)

        if resp.status_code == 200:
            readme_text = resp.text[:8000]
        elif resp.status_code == 404:
            return {"ok": False, "error": f"Repo '{owner}/{repo}' not found or has no README."}
    except requests.exceptions.RequestException:
        pass  # fall through to raw fallback

    # Fallback: fetch raw README directly
    if not readme_text:
        for readme_name in ["README.md", "readme.md", "README.rst", "README"]:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{readme_name}"
            try:
                resp = requests.get(raw_url, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code == 200:
                    readme_text = resp.text[:8000]
                    break
            except requests.exceptions.RequestException:
                continue
        # Also try master branch
        if not readme_text:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
            try:
                resp = requests.get(raw_url, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code == 200:
                    readme_text = resp.text[:8000]
            except requests.exceptions.RequestException:
                pass

    if not readme_text:
        # Last resort: scrape the GitHub page itself
        try:
            page_resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if page_resp.ok:
                soup = BeautifulSoup(page_resp.text, "html.parser")
                article = soup.find("article")
                if article:
                    readme_text = article.get_text(separator="\n", strip=True)[:8000]
        except requests.exceptions.RequestException:
            pass

    if not readme_text:
        return {"ok": False, "error": f"Could not fetch README for '{owner}/{repo}'."}

    # Try to get repo metadata (non-critical)
    try:
        meta_resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=HEADERS, timeout=TIMEOUT
        )
        if meta_resp.ok:
            data = meta_resp.json()
            meta = {
                "stars": data.get("stargazers_count", 0),
                "description": data.get("description", ""),
                "language": data.get("language", ""),
                "last_push": data.get("pushed_at", ""),
                "topics": data.get("topics", []),
            }
    except requests.exceptions.RequestException:
        meta = {"note": "Could not fetch repo metadata (rate limited)"}

    return {
        "ok": True,
        "source_type": "github",
        "url": url,
        "owner": owner,
        "repo": repo,
        "readme": readme_text,
        "meta": meta,
    }


def _extract_page_text(resp) -> dict:
    """Parse a response into title, meta_description, text, and internal links."""
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find internal links before stripping nav
    internal_links = []
    base_parsed = urlparse(str(resp.url))
    base_domain = base_parsed.hostname or ""
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        full_url = urljoin(str(resp.url), href)
        link_parsed = urlparse(full_url)
        link_domain = link_parsed.hostname or ""
        if link_domain == base_domain and link_parsed.path != base_parsed.path:
            path_lower = link_parsed.path.lower().strip("/")
            label = (a_tag.get_text(strip=True) or path_lower)[:60]
            if any(kw in path_lower for kw in SUBPAGE_KEYWORDS):
                internal_links.append({
                    "url": strip_utm(full_url),
                    "path": link_parsed.path,
                    "label": label,
                })

    # Remove script, style, nav, footer clutter
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "")

    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Deduplicate internal links by path
    seen_paths = set()
    unique_links = []
    for link in internal_links:
        if link["path"] not in seen_paths:
            seen_paths.add(link["path"])
            unique_links.append(link)

    return {
        "title": title,
        "meta_description": meta_desc,
        "text": text,
        "internal_links": unique_links[:10],
    }


def _fetch_subpages(links: list, max_pages: int = 5) -> list:
    """Fetch up to max_pages internal sub-pages and return their text."""
    subpages = []
    for link in links[:max_pages]:
        try:
            resp = requests.get(link["url"], headers=HEADERS, timeout=10,
                                allow_redirects=True)
            if resp.ok:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text)[:4000]
                if len(text) > 100:
                    subpages.append({
                        "url": strip_utm(link["url"]),
                        "path": link["path"],
                        "label": link["label"],
                        "text": text,
                    })
        except requests.exceptions.RequestException:
            continue
    return subpages


def fetch_webpage(url: str) -> dict:
    """Fetch a web page and its key sub-pages (blog, pricing, docs, etc.)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)

        if resp.status_code == 404:
            return {"ok": False, "error": f"Page not found (404): {url}"}
        if resp.status_code == 403:
            return {"ok": False, "error": f"Access denied (403): {url}"}
        resp.raise_for_status()

        page_data = _extract_page_text(resp)

        main_text = page_data["text"][:12000]

        # Check for pricing signals
        pricing_keywords = ["pricing", "free tier", "free plan", "pro plan",
                           "enterprise", "api key", "token", "credit",
                           "subscribe", "sign up", "waitlist", "free"]
        has_pricing_signals = any(kw in main_text.lower() for kw in pricing_keywords)

        # Deep fetch: follow internal links one level
        subpages = _fetch_subpages(page_data["internal_links"])

        # Build combined text with clear page boundaries
        subpage_text = ""
        subpage_urls = []
        for sp in subpages:
            subpage_text += f"\n\n--- SUB-PAGE: {sp['label']} ({sp['url']}) ---\n{sp['text']}"
            subpage_urls.append({"label": sp["label"], "url": sp["url"]})

        return {
            "ok": True,
            "source_type": "web",
            "url": strip_utm(url),
            "title": page_data["title"],
            "meta_description": page_data["meta_description"],
            "text": main_text,
            "subpage_text": subpage_text[:8000],
            "subpages_fetched": subpage_urls,
            "has_pricing_signals": has_pricing_signals,
            "final_url": strip_utm(str(resp.url)),
        }

    except requests.exceptions.Timeout:
        return {"ok": False, "error": f"Request timed out for: {url}"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Could not connect — dead link or domain down: {url}"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Failed to fetch page: {e}"}


def _try_instagram_oembed(url: str) -> dict | None:
    """Try Instagram's oEmbed API — works for public posts without auth."""
    try:
        oembed_url = f"https://api.instagram.com/oembed/?url={url}&omitscript=true"
        resp = requests.get(oembed_url, headers=HEADERS, timeout=10)
        if resp.ok:
            data = resp.json()
            title = data.get("title", "")
            author = data.get("author_name", "")
            html = data.get("html", "")
            caption = title
            if html:
                soup = BeautifulSoup(html, "html.parser")
                text_from_html = soup.get_text(separator="\n", strip=True)
                if text_from_html and len(text_from_html) > len(caption):
                    caption = text_from_html
            if caption and len(caption) > 20:
                return {
                    "ok": True,
                    "source_type": "instagram",
                    "url": url,
                    "caption": caption,
                    "title": f"{author} on Instagram" if author else "",
                    "text": caption,
                    "auto_fetched": True,
                    "fetch_method": "oembed",
                    "caption_only": True,
                }
    except (requests.exceptions.RequestException, ValueError):
        pass
    return None


def fetch_instagram(url: str) -> dict:
    """Fetch Instagram post/reel content. Tries oEmbed first, then meta tags."""
    # Method 1: oEmbed API (most reliable for public posts)
    oembed_result = _try_instagram_oembed(url)
    if oembed_result:
        return oembed_result

    # Method 2: Direct page scraping for meta tags
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if not resp.ok:
            return {
                "ok": True, "source_type": "instagram", "url": url,
                "needs_manual_input": True,
                "message": "Instagram blocked the auto-fetch (this is normal for private/recent posts). Paste the caption or what the creator says above.",
            }

        soup = BeautifulSoup(resp.text, "html.parser")

        caption = ""
        # Try og:description (Instagram puts captions here for public posts)
        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            caption = og["content"]
        # Try regular description
        if not caption:
            desc = soup.find("meta", attrs={"name": "description"})
            if desc and desc.get("content"):
                caption = desc["content"]
        # Try og:title
        if not caption:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                caption = og_title["content"]

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Also grab any visible text as fallback
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        page_text = soup.get_text(separator="\n", strip=True)
        page_text = re.sub(r'\n{3,}', '\n\n', page_text)[:4000]

        if not caption and len(page_text) < 100:
            return {
                "ok": True, "source_type": "instagram", "url": url,
                "needs_manual_input": True,
                "message": "Could not extract caption automatically. Paste the caption or what the creator says in the reel.",
            }

        return {
            "ok": True,
            "source_type": "instagram",
            "url": url,
            "caption": caption or page_text[:2000],
            "title": title,
            "text": f"{caption}\n\n{page_text}" if caption else page_text,
            "auto_fetched": True,
            "fetch_method": "meta_tags",
            "caption_only": True,
        }

    except requests.exceptions.RequestException:
        return {
            "ok": True, "source_type": "instagram", "url": url,
            "needs_manual_input": True,
            "message": "Could not connect to Instagram. Paste the caption or what the creator says in the reel.",
        }


def fetch(url: str) -> dict:
    """Main fetch dispatcher — routes URL to the right fetcher."""
    url = url.strip()

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    url_type = classify_url(url)

    if url_type == "github":
        return fetch_github(url)
    elif url_type == "instagram":
        return fetch_instagram(url)
    else:
        return fetch_webpage(url)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = fetch(sys.argv[1])
        import json
        print(json.dumps(result, indent=2, default=str))
    else:
        print("Usage: python fetcher.py <url>")
