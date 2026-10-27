# Technical Note — AI Hype Claim Checker

## Problem

AI content pages evaluate dozens of new AI tools every week. Each tool comes with marketing claims — "completely free," "no code needed," "replaces your workflow" — that take 30-60 minutes to manually verify. The researcher needs to know three things fast: Are the claims real? Can I actually try this? Is it worth a post?

I chose this problem because it maps directly to the research workflow at @aistuff.muu. Every reel or post starts with someone finding a tool, getting excited by the pitch, and then spending time figuring out if the tool delivers. Automating the skepticism layer saves time and produces better content decisions.

## Approach

The tool follows a three-stage pipeline:

1. **Fetch** — Given a URL (GitHub repo, landing page, or Instagram reel), extract the raw text content. GitHub repos use the API with a raw-file fallback for rate limits. Web pages are parsed with BeautifulSoup, stripping navigation and scripts. Instagram requires manual caption input since their pages need authentication.

2. **Analyze** — Send the extracted content to Google Gemini Flash in two LLM calls:
   - **Claim extraction**: Identify 3-7 specific claims categorized as capability, performance, ease-of-use, scope, or cost claims
   - **Verification + scoring**: For each claim, assess if it's confirmed, partially true, or exaggerated. Then score tryability (free tier, setup time, blockers) and generate a content verdict

3. **Present** — Format results as a color-coded CLI output with a clear three-way verdict: Cover It, Cover the Gap, or Skip.

Key design decisions:
- **Two LLM calls instead of one**: Splitting extraction and verification produces more structured, reliable output than asking for everything at once.
- **Streamlit web UI + CLI**: Both interfaces share the same backend pipeline. The web UI makes it accessible to non-technical users; the CLI is faster for power users.
- **Gemini Flash over Pro**: The free tier is generous, latency is lower, and the task doesn't need Pro-level reasoning.
- **Model fallback chain**: The analyzer tries multiple Gemini Flash models in sequence, handling deprecations and 503 overload errors gracefully.
- **Three verdicts, not a binary**: "Cover the Gap" captures the most interesting content angle — when a tool is overhyped, *the hype itself* becomes the story.

## Technical Implementation

- **Language**: Python 3.9+
- **LLM**: Google Gemini Flash via `google-genai` SDK (new official SDK)
- **Web fetching**: `requests` + `BeautifulSoup4`
- **Frontend**: Streamlit for the web interface

The fetcher module handles three input types (GitHub, web pages, Instagram) with graceful degradation — if the GitHub API is rate-limited, it falls back to raw.githubusercontent.com, then to scraping the page HTML. The analyzer module manages prompt engineering, JSON parsing (including stripping markdown code fences that Gemini sometimes wraps responses in), and error states (not an AI tool, no claims found).

## Testing

Tested against:
1. **GPT Researcher** (GitHub) — A real, actively maintained repo. Tests the GitHub fetcher, claim extraction from a README, and the case where "open source" ≠ "free" (needs OpenAI + Tavily keys).
2. **Dead/invalid URLs** — Returns clear error messages for 404s, connection failures, and invalid formats.
3. **Non-AI content** — Detects when the URL points to something that isn't an AI tool and reports it.
4. **Instagram URLs** — Correctly identifies Instagram links and prompts for manual caption input.
5. **Rate-limited GitHub API** — Falls back to raw file fetch without failing.

What failed during development: Initially tried a single LLM call for both extraction and verification. The output was less structured and sometimes merged claims together. Splitting into two calls fixed this.

## Limitations and Next Steps

**Current limitations:**
- Cannot auto-fetch Instagram captions (auth wall)
- Verification is reasoning-based — the tool doesn't actually *try* the tool it's reviewing
- Single-page analysis — doesn't follow links to pricing pages or documentation
- Depends on Gemini's knowledge, which has a training cutoff

**With another day, I would add:**
- Link-following to verify pricing claims against actual pricing pages
- Batch mode to check a list of URLs from a CSV
- A simple cache to avoid re-analyzing the same tool
- Browser automation to actually try signing up for free tiers and report real results
