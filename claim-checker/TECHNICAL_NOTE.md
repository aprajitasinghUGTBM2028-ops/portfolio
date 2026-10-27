# Technical Note — AI Hype Claim Checker

## Problem

AI content pages evaluate dozens of new AI tools every week. Each tool comes with marketing claims — "completely free," "no code needed," "replaces your workflow" — that take 30-60 minutes to manually verify. The researcher needs to know three things fast: Are the claims real? Can I actually try this? Is it worth a post?

I chose this problem because it maps directly to the research workflow at content pages like @aistuff.muu. Every reel or post starts with someone finding a tool, getting excited by the pitch, and then spending time figuring out if the tool delivers. Automating the skepticism layer saves time and produces better content decisions.

## Approach

The tool follows a 9-step pipeline with code validation between every AI step:

1. **Classify & Plan** (AI) — Identifies the tool type, spots claims with exact quotes, and plans what evidence to gather (search queries, sub-pages to fetch).
2. **Build Sources** (code) — Indexes all fetched content by source ID. Fetches additional sub-pages the plan identified.
3. **Search for Evidence** (AI + web search) — Runs planned queries via OpenAI's Responses API with `web_search` tool. Reports facts with source URLs.
4. **Extract Facts** (AI) — Reads all sources and produces structured facts with quotes, source IDs, and categories.
5. **Validate Facts** (code) — Checks quotes against source text. Assigns statuses using domain comparison (not a whitelist). Flags unverified quotes.
6. **Find Gaps** (AI) — Identifies missing evidence. Runs up to 2 additional searches if critical gaps exist (zero independent sources, missing pricing info).
7. **Write Report** (AI) — Produces the full report citing only validated fact IDs. Every number must cite a fact.
8. **Critique Report** (AI) — A separate call checks the report against the evidence list for unsupported claims, invented numbers, or misattributed sources.
9. **Write Hooks** (AI + code) — Generates reel hooks. Code validates that every number comes from a fact, SITE_SAYS numbers are attributed, and hooks don't end with unanswered questions.

Key design decisions:
- **Code computes verdicts**: The model returns `evidence_ids` per claim. Code derives the verdict (SITE_SAYS, INDEPENDENT, UNVERIFIABLE, CONTRADICTED) by checking each evidence item's source domain against the tool's domain. This prevents the model from marking everything "CONFIRMED."
- **Domain-based independence**: Uses `urlparse` to compare domains. A source is INDEPENDENT only if its domain differs from the tool's own domain. This replaces an earlier whitelist approach that had false matches (`"x.com" in "linux.com"`).
- **Prompt injection fencing**: All page content is wrapped in `<data label="..." instructions="none">` tags. The `</data>` sequence is escaped inside content.
- **Tolerant JSON parsing**: Uses `re.search(r'\{.*\}', text, re.S)` to extract JSON from model responses, handling markdown code fences and preamble text.

## Technical Implementation

- **Language**: Python 3.9+
- **LLM**: OpenAI GPT-4o via the Responses API (with `web_search` tool) and Chat Completions API (with JSON mode)
- **Web fetching**: `requests` + `BeautifulSoup4` with SSRF protection, thin-content detection, and sub-page priority sorting
- **Frontend**: Streamlit with password gate and usage counter

## Testing

Tested against:
1. **Prompt Motion** (web page) — A curated prompt gallery. Tests claim extraction, the difference between "free to browse" vs "needs Claude/GPT to use," and whether SITE_SAYS numbers get the "the site says" prefix.
2. **gstack** (GitHub) — A large README repo. Tests GitHub fetcher with API fallback.
3. **Dead/invalid URLs** — Returns clear error messages for 404s, connection failures, and invalid formats.
4. **Non-AI content** — Detects non-AI URLs and reports "not an AI tool."
5. **Instagram URLs** — Correctly identifies Instagram links and prompts for manual caption input.
6. **Thin content pages** — JS-rendered pages that return <300 chars are rejected with a helpful message.

### Known Issues Found During Testing

- **Run-to-run variance**: Different runs can produce different search results, leading to different evidence sets and slightly different scores. This is inherent to web search.
- **Score inflation**: The model tends to give higher scores than warranted. Code clamping catches out-of-range values, but within-range inflation (e.g., 7/10 virality for a niche tool) still occurs. The critic step catches some of these.
- **Invented search results**: In early versions, the model would invent URLs not found during search. The current version validates evidence URLs against gathered sources and downgrades unmatched ones to UNVERIFIABLE.

## Limitations and Next Steps

**Current limitations:**
- Cannot auto-fetch Instagram captions (auth wall)
- Verification uses web search, not live-testing — the tool can't actually try what it reviews
- Web search results vary between runs, causing score variance
- Login-walled pages can't be analyzed

**With more time, I would add:**
- Persistent usage tracking (current counter resets per session)
- A test suite that runs the same URLs multiple times to measure consistency
- Browser automation to actually try signing up for free tiers
- Screenshot capture to show what the tool looks like
