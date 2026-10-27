"""
fetcher.py — Fetches and extracts text content from URLs.
Handles: landing pages, GitHub READMEs, and generic web pages.
"""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15


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


def fetch_webpage(url: str) -> dict:
    """Fetch and extract text from a generic web page."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)

        if resp.status_code == 404:
            return {"ok": False, "error": f"Page not found (404): {url}"}
        if resp.status_code == 403:
            return {"ok": False, "error": f"Access denied (403): {url}"}
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script, style, nav, footer clutter
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        # Get main text content
        text = soup.get_text(separator="\n", strip=True)
        # Collapse whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text[:8000]  # cap for LLM context

        # Check for pricing signals
        pricing_keywords = ["pricing", "free tier", "free plan", "pro plan",
                           "enterprise", "api key", "token", "credit",
                           "subscribe", "sign up", "waitlist"]
        has_pricing_signals = any(kw in text.lower() for kw in pricing_keywords)

        return {
            "ok": True,
            "source_type": "web",
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "text": text,
            "has_pricing_signals": has_pricing_signals,
            "final_url": str(resp.url),  # after redirects
        }

    except requests.exceptions.Timeout:
        return {"ok": False, "error": f"Request timed out for: {url}"}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Could not connect — dead link or domain down: {url}"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Failed to fetch page: {e}"}


def fetch_instagram(url: str) -> dict:
    """Fetch Instagram post/reel content from meta tags and page text."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if not resp.ok:
            return {
                "ok": True, "source_type": "instagram", "url": url,
                "needs_manual_input": True,
                "message": f"Could not fetch Instagram page (status {resp.status_code}). Paste the caption below.",
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
