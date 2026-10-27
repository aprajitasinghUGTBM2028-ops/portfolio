"""
analyzer.py — Uses OpenAI GPT to extract claims, verify them,
score tryability, and produce a content verdict.

Architecture: 4-step pipeline where each call does one focused thing.
  1. extract_claims — read homepage + sub-pages, extract what the tool claims
  2. gather_evidence — web search ONLY, build structured fact list
  3. analyze_with_evidence — score/verify/verdict from pre-gathered evidence
  4. write_hooks — write hooks constrained to evidence list
"""

import os
import json
import time
import re
from openai import OpenAI

MODELS = ["gpt-4o-mini", "gpt-4o"]


def _clean_text(text: str) -> str:
    """Remove non-UTF-8 characters and null bytes from text."""
    if not text:
        return ""
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    text = text.replace("\x00", "")
    text = re.sub(r'[\ud800-\udfff]', '', text)
    return text


def get_client():
    """Initialize and return the OpenAI client."""
    raw_key = os.environ.get("OPENAI_API_KEY", "")
    raw_key = "".join(raw_key.split())
    api_key = "".join(c for c in raw_key if ord(c) < 128)
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set.\n"
            "Get one at https://platform.openai.com/api-keys"
        )
    if len(api_key) < 20:
        raise RuntimeError(
            f"API key invalid after cleaning. Raw length: {len(raw_key)}, "
            f"clean length: {len(api_key)}, raw type: {type(raw_key).__name__}, "
            f"raw repr start: {repr(raw_key[:30])}\n"
            "Re-paste your key in Streamlit secrets with plain straight quotes."
        )
    return OpenAI(api_key=api_key)


def generate(client, prompt: str, prefer_model: str = None, **kwargs) -> str:
    """Try multiple models with retries (Chat Completions — no web search)."""
    prompt = _clean_text(prompt)
    models = MODELS
    if prefer_model:
        models = [prefer_model] + [m for m in MODELS if m != prefer_model]
    last_error = None
    for model in models:
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                last_error = e
                err = str(e)
                if "429" in err or "rate_limit" in err.lower():
                    time.sleep(5 * (attempt + 1))
                    continue
                if "503" in err or "overloaded" in err.lower():
                    time.sleep(2 ** attempt)
                    continue
                if "404" in err or "model_not_found" in err.lower():
                    break
                if "invalid_api_key" in err.lower() or "authentication" in err.lower():
                    raise RuntimeError(
                        f"OpenAI API error: {err}\n"
                        "Check that your API key is valid at https://platform.openai.com/api-keys"
                    )
                if "codec" in err.lower() or "encode" in err.lower():
                    raise RuntimeError(
                        f"Encoding error: {err}\n"
                        "The content may contain unsupported characters."
                    )
                break
    raise RuntimeError(
        f"All models failed. Last error: {last_error}\n"
        "Try again in a few minutes, or check your API key."
    )


def generate_with_search(client, prompt: str, prefer_model: str = None) -> str:
    """Use the Responses API with web_search so GPT can search the internet live."""
    prompt = _clean_text(prompt)
    models = MODELS
    if prefer_model:
        models = [prefer_model] + [m for m in MODELS if m != prefer_model]
    last_error = None
    for model in models:
        for attempt in range(3):
            try:
                response = client.responses.create(
                    model=model,
                    input=prompt,
                    tools=[{"type": "web_search", "search_context_size": "high"}],
                    temperature=0.3,
                )
                return response.output_text.strip()
            except Exception as e:
                last_error = e
                err = str(e)
                if "429" in err or "rate_limit" in err.lower():
                    time.sleep(5 * (attempt + 1))
                    continue
                if "503" in err or "overloaded" in err.lower():
                    time.sleep(2 ** attempt)
                    continue
                if "404" in err or "model_not_found" in err.lower():
                    break
                if "invalid_api_key" in err.lower() or "authentication" in err.lower():
                    raise RuntimeError(
                        f"OpenAI API error: {err}\n"
                        "Check that your API key is valid at https://platform.openai.com/api-keys"
                    )
                break
    raise RuntimeError(
        f"All models failed (Responses API). Last error: {last_error}\n"
        "Try again in a few minutes, or check your API key."
    )


def _parse_json_response(text: str) -> dict:
    """Clean markdown fences and parse JSON from LLM response."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()
    return json.loads(text)


# ═══════════════════════════════════════════════════════════════════
# STEP 1: Extract claims from homepage + sub-pages
# ═══════════════════════════════════════════════════════════════════

def extract_claims(client, content: dict) -> dict:
    """Extract hype claims from fetched content including sub-pages."""

    if content["source_type"] == "github":
        context = f"""GitHub Repo: {content['owner']}/{content['repo']}
Description: {content.get('meta', {}).get('description', 'N/A')}
Stars: {content.get('meta', {}).get('stars', 'N/A')}
Language: {content.get('meta', {}).get('language', 'N/A')}

README content:
{content.get('readme', '')}"""

    elif content["source_type"] == "web":
        context = f"""Page title: {content.get('title', 'N/A')}
URL: {content.get('url', '')}
Meta description: {content.get('meta_description', '')}

Page content:
{content.get('text', '')[:8000]}"""

        # Include sub-page content so extraction sees /customize, /blog, etc.
        subpage_text = content.get("subpage_text", "")
        if subpage_text:
            context += f"""

SUB-PAGES (internal links followed one level deep):
{subpage_text[:6000]}"""

    elif content["source_type"] == "instagram":
        context = f"""Instagram caption:
{content.get('caption', content.get('text', 'No caption provided'))}"""
    else:
        context = str(content)

    prompt = f"""You are a meticulous AI tool investigator. READ THE SOURCE CONTENT CAREFULLY — every page, including sub-pages — and extract ONLY what's actually there.

SOURCE CONTENT:
{context}

TASK:

1. IDENTIFY THE TOOL TYPE from the source content:
   - Generator (creates new content from scratch)
   - Gallery/Directory (curates or showcases existing content)
   - Wrapper (puts a UI around another AI like GPT/Claude/Stable Diffusion)
   - Marketplace (sells templates, prompts, or assets)
   - Editor / Analyzer / Aggregator / Other
   BASE THIS ON WHAT THE PAGES DESCRIBE, not what the name sounds like.

2. FIND EVERY SPECIFIC NUMBER across all pages (homepage AND sub-pages):
   - Entry counts, user counts, item tallies
   - Statistics from blog/analysis pages (e.g. "33 accounts used the same prompt")
   - Pricing: look for "free", price tiers, or "subscribe" on ANY page
   - Performance metrics, time savings
   Quote these EXACTLY as they appear and note which page they're on.

3. Extract 3-7 specific claims. For EACH claim:
   - Include the EXACT quote from the source
   - Note which page it's from (homepage, /blog, /customize, etc.)
   - If there is no quote (you're inferring), mark it as "implied"

4. IDENTIFY PAID DEPENDENCIES: Does using this tool require a paid account for another service? (e.g. Claude Pro, OpenAI API, Adobe subscription). List each with its cost.

Return ONLY valid JSON:
{{
  "tool_name": "Name of the tool",
  "tool_type": "generator|gallery|wrapper|marketplace|editor|analyzer|aggregator|other",
  "tool_summary": "One honest line from what the pages show",
  "key_data_points": ["specific numbers/stats with page source"],
  "paid_dependencies": ["Claude Pro at $20/mo", "OpenAI API at ~$X per use"],
  "claims": [
    {{
      "claim": "The specific claim in plain language",
      "category": "capability|performance|ease_of_use|scope|cost",
      "quote": "EXACT text from the source",
      "page": "homepage|/blog|/customize|etc."
    }}
  ]
}}

If this doesn't appear to be an AI tool, return:
{{"tool_name": "N/A", "tool_summary": "This doesn't appear to be an AI tool", "claims": [], "not_ai_tool": true}}"""

    text = generate(client, prompt, prefer_model="gpt-4o")

    try:
        return _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        return {"tool_name": "Parse Error", "tool_summary": "Could not parse LLM response", "claims": [], "raw": text}


# ═══════════════════════════════════════════════════════════════════
# STEP 2: Gather evidence via web search (ONLY fact-finding)
# ═══════════════════════════════════════════════════════════════════

def gather_evidence(client, tool_name: str, claims_data: dict, content: dict) -> list:
    """Use web search to find independent evidence. Returns a list of facts."""

    claims_summary = "\n".join(
        f"- {c['claim']}" for c in claims_data.get("claims", [])
    )

    prompt = f"""You are a research assistant. Your ONLY job is to search the web and report what you find about "{tool_name}". Do NOT analyze, score, or give opinions. Just find facts.

SEARCH THESE (run each search):
1. "{tool_name}" site:reddit.com
2. "{tool_name}" review
3. "{tool_name}" site:producthunt.com
4. "{tool_name}" — general search for the tool
5. "{tool_name}" similar names OR lookalike — find domains with similar names

CLAIMS TO CHECK (search for evidence about each):
{claims_summary}

FOR EACH FACT YOU FIND, report:
- fact: what you found (exact quote or summary)
- source_url: the URL (strip ?utm_... tracking params)
- source_type: "official_site" | "reddit" | "product_hunt" | "news_article" | "youtube" | "blog" | "directory" | "other"
- date: when published, or null
- search_query: what you searched to find this

ALSO REPORT:
- Searches that returned NOTHING (so we know you actually searched)
- Domains with similar names to "{tool_name}" (lookalikes)
- Whether the tool requires paid accounts for other services (e.g. Claude, OpenAI, Adobe)

Return ONLY valid JSON:
{{
  "evidence": [
    {{
      "fact": "what you found",
      "source_url": "url without utm params",
      "source_type": "reddit|product_hunt|news_article|official_site|etc.",
      "date": "2024-01-15 or null",
      "search_query": "what you searched"
    }}
  ],
  "empty_searches": [
    {{"query": "what you searched", "result": "no results found"}}
  ],
  "lookalike_domains": ["promptmotion.org", "otherdomain.com"],
  "paid_dependencies_found": ["Claude Pro $20/mo — needed to generate videos"]
}}"""

    text = generate_with_search(client, prompt, prefer_model="gpt-4o")

    try:
        return _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        return {"evidence": [], "empty_searches": [], "lookalike_domains": [], "paid_dependencies_found": []}


# ═══════════════════════════════════════════════════════════════════
# STEP 3: Verify claims + score + verdict (NO web search needed)
# ═══════════════════════════════════════════════════════════════════

def analyze_with_evidence(client, claims_data: dict, content: dict, evidence_data: dict) -> dict:
    """Verify claims, score, and write verdict using pre-gathered evidence."""

    claims_json = json.dumps(claims_data, indent=2)
    evidence_json = json.dumps(evidence_data.get("evidence", []), indent=2)
    empty_searches = json.dumps(evidence_data.get("empty_searches", []), indent=2)
    lookalikes = evidence_data.get("lookalike_domains", [])
    paid_deps = evidence_data.get("paid_dependencies_found", [])

    # Build page summary
    source_text = ""
    subpage_text = ""
    if content.get("source_type") == "github":
        source_text = content.get("readme", "")[:4000]
    elif content.get("source_type") == "web":
        source_text = content.get("text", "")[:4000]
        subpage_text = content.get("subpage_text", "")[:4000]

    tool_type = claims_data.get("tool_type", "unknown")
    paid_deps_from_extract = claims_data.get("paid_dependencies", [])
    all_paid_deps = list(set(paid_deps + paid_deps_from_extract))

    prompt = f"""You are writing a tool report for content creators. You have pre-gathered evidence below — use ONLY these facts. Do not invent or assume anything not in the evidence or the page content.

=== CLAIM STATUSES (use exactly) ===
- CONFIRMED: Feature visible on the official page, OR evidence from a third party backs it up.
- REPORTED: A third party mentioned it, but you can't verify the specific number.
- SELF-REPORTED: The tool's own page says it — label it honestly as their claim.
- NOT FOUND: Web search returned nothing. "Not found" does NOT mean "false."
- CONTRADICTED: Evidence directly contradicts the claim.

=== RULES ===
1. A feature on the official page (a /customize page, a subscribe box) is CONFIRMED as existing.
2. Claims about popularity, quality, or results need third-party evidence to be CONFIRMED.
3. Every number you write needs a source. If the homepage says one number and the blog says another, show BOTH.
4. Only reference searches that appear in EMPTY SEARCHES below. Never claim you searched something you didn't.
5. Third-party write-ups show interest, NOT virality. Virality means people share it unprompted with their audience.
6. Coverage ≠ virality. A directory listing ≠ endorsement.
7. Paid dependencies: {json.dumps(all_paid_deps) if all_paid_deps else "None found"}
8. Lookalike domains found: {json.dumps(lookalikes) if lookalikes else "None found"}

=== SCORING (be strict — most tools score 3-6) ===
Tryability: "browse and copy" is SEPARATE from "make content."
- Browse score: Can someone browse and copy a prompt for free? If yes, high score.
- Create score: Can someone make original content? Include the cost of paid dependencies.
- If making content needs Claude Pro ($20/mo) or OpenAI API, the create score drops.

Virality (1-10): Every score MUST cite a specific fact from the evidence.
- Trend fit: Is this trending NOW or old news? Cite dates.
- Uniqueness: How many similar tools exist? If evidence found 100 similar projects, score low.
- Shareability / Visual wow: Based on what the tool actually produces.

=== INPUTS ===

Tool type: {tool_type}

CLAIMS:
{claims_json}

WEB SEARCH EVIDENCE:
{evidence_json}

SEARCHES THAT FOUND NOTHING:
{empty_searches}

HOMEPAGE (first 4000 chars):
{source_text[:4000]}

SUB-PAGES:
{subpage_text[:4000]}

=== OUTPUT (valid JSON only) ===

{{
  "tool_name": "{claims_data.get('tool_name', 'Unknown')}",
  "evidence_list": [
    {{
      "fact": "from the evidence above",
      "status": "CONFIRMED|REPORTED|SELF-REPORTED|NOT FOUND|CONTRADICTED",
      "source_url": "url or 'official site'",
      "date": "date or null"
    }}
  ],
  "verified_claims": [
    {{
      "claim": "claim text",
      "verdict": "CONFIRMED|REPORTED|SELF-REPORTED|NOT FOUND|CONTRADICTED",
      "evidence": "cite the specific evidence item",
      "red_flags": []
    }}
  ],
  "tryability": {{
    "free_tier": "yes|no|freemium|unclear",
    "free_tier_detail": "quote from the page",
    "setup_browse": {{"time": "X min", "cost": "$0", "steps": "what browsing involves"}},
    "setup_create": {{"time": "X min", "cost": "$Y/mo for [service]", "steps": "what creating involves, including paid deps"}},
    "visible_result": "yes|no|unclear",
    "blockers": ["real blockers only"],
    "score": 4
  }},
  "setup_guide": [
    "Step 1: Browse — ...",
    "Step 2: Copy a prompt — ... (free)",
    "Step 3: To make a video — requires [paid service] at $X/mo"
  ],
  "virality": {{
    "visual_wow": 5,
    "shareability": 4,
    "trend_fit": 5,
    "uniqueness": 4,
    "virality_score": 4,
    "virality_explanation": "cite specific evidence for each sub-score"
  }},
  "comparison": {{
    "similar_to": "Think of it as [known tool] but for [niche]",
    "what_makes_it_different": "cite specific data point that competitors lack",
    "who_is_this_for": "specific person + specific need",
    "lookalike_warning": "list of similarly-named sites and clarify they are not official, or null",
    "lookalike_sites": {json.dumps(lookalikes) if lookalikes else "[]"}
  }},
  "content_verdict": {{
    "verdict": "COVER IT|COVER THE GAP|SKIP",
    "reason": "2-3 sentences citing evidence"
  }},
  "hype_score": 5,
  "summary": "2-3 honest sentences. What's confirmed, self-reported, and not found."
}}"""

    text = generate(client, prompt, prefer_model="gpt-4o")

    try:
        return _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        return {"error": "Could not parse analysis response", "raw": text}


# ═══════════════════════════════════════════════════════════════════
# STEP 4: Write hooks from evidence (separate focused call)
# ═══════════════════════════════════════════════════════════════════

def write_hooks(client, evidence_list: list, tool_name: str) -> list:
    """Write 3 reel hooks using ONLY facts from the evidence list."""

    evidence_json = json.dumps(evidence_list, indent=2)

    prompt = f"""You write reel hooks for content creators. A hook is the first sentence that makes someone stop scrolling. It creates TENSION — a gap between what the viewer expects and what's true.

=== RULES ===
1. Every number, claim, and action in the hook MUST appear in the evidence list below.
2. If a number isn't in the evidence, you CANNOT use it.
3. A hook is NOT a headline or description. It's a question or contradiction that demands an answer.

=== BAD HOOKS (these are headlines, not hooks) ===
- "Over 200 motion videos with full prompts" — no tension, just a feature list
- "Explore this amazing AI tool" — generic, no data
- "Check out this gallery of AI animations" — descriptive, not hooky

=== GOOD HOOKS (these create tension) ===
- "33 accounts typed the same 26 words. Same prompt. Likes from 0 to 17,023." — specific data, unexpected gap
- "The gallery's own blog says long prompts win. An independent review says they don't look better. The one phrase that scored higher? 'Go all out.'" — contradiction between sources
- "44% of this AI motion gallery is one prompt, remixed. I ran it so you don't have to." — surprising stat + promise

=== EVIDENCE LIST ===
{evidence_json}

Write exactly 3 hooks for "{tool_name}". Each hook must:
- Use a specific number or fact from the evidence list
- Create tension (a gap, a contradiction, or a surprising comparison)
- Be 1-2 sentences max

Return ONLY valid JSON:
{{
  "hooks": [
    "hook 1 text",
    "hook 2 text",
    "hook 3 text"
  ]
}}"""

    try:
        text = generate(client, prompt, prefer_model="gpt-4o")
        result = _parse_json_response(text)
        return result.get("hooks", [])
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════
# STEP 5 (reel pipeline): Identify tool from Instagram reel
# ═══════════════════════════════════════════════════════════════════

def _identify_tool_from_reel(client, reel_text: str) -> dict:
    """Identify the tool/product promoted in an Instagram reel."""
    prompt = f"""An Instagram reel is promoting an AI tool or tech product. From the text below, identify:
1. The tool's name
2. Its official URL (if mentioned, or if you know it from your training data)
3. What to search to find it

REEL CONTENT:
{_clean_text(reel_text[:2000])}

Return ONLY valid JSON:
{{
  "tool_name": "the tool name",
  "tool_url": "https://... or null if unknown",
  "search_terms": "what to search for"
}}"""
    text = generate(client, prompt)
    try:
        return _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        return {"tool_name": "Unknown", "tool_url": None, "search_terms": ""}


def _analyze_reel(client, content: dict) -> dict:
    """Full reel analysis pipeline: identify tool -> fetch page -> gather evidence -> analyze."""
    from fetcher import fetch_webpage, fetch_github, classify_url

    reel_text = content.get("caption", content.get("text", ""))
    reel_url = content.get("url", "")

    # Step 1: Identify the tool from the reel
    tool_info = _identify_tool_from_reel(client, reel_text)

    # Step 2: Try to fetch the tool's official page
    tool_page = None
    tool_url = tool_info.get("tool_url")
    if tool_url:
        url_type = classify_url(tool_url)
        if url_type == "github":
            tool_page = fetch_github(tool_url)
        else:
            tool_page = fetch_webpage(tool_url)
        if not tool_page.get("ok"):
            tool_page = None

    if not tool_page:
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]*'
        found_urls = re.findall(url_pattern, reel_text)
        for found_url in found_urls:
            if "instagram.com" not in found_url:
                url_type = classify_url(found_url)
                if url_type == "github":
                    tool_page = fetch_github(found_url)
                else:
                    tool_page = fetch_webpage(found_url)
                if tool_page and tool_page.get("ok"):
                    tool_url = found_url
                    break
                tool_page = None

    # Step 3: Build context and run evidence-based analysis
    tool_page_section = ""
    if tool_page and tool_page.get("ok"):
        if tool_page.get("source_type") == "github":
            meta = tool_page.get("meta", {})
            tool_page_section = f"""
TOOL'S OFFICIAL PAGE ({tool_url}):
GitHub: {tool_page.get('owner', '?')}/{tool_page.get('repo', '?')}
Stars: {meta.get('stars', '?')} | Language: {meta.get('language', '?')} | Last push: {str(meta.get('last_push', '?'))[:10]}
Description: {meta.get('description', 'N/A')}

README:
{tool_page.get('readme', '')[:6000]}"""
        else:
            subpage_text = tool_page.get("subpage_text", "")
            tool_page_section = f"""
TOOL'S OFFICIAL PAGE ({tool_url}):
Title: {tool_page.get('title', 'N/A')}
Meta: {tool_page.get('meta_description', '')}

Page content:
{tool_page.get('text', '')[:6000]}"""
            if subpage_text:
                fetched_labels = [sp.get("label", "?") for sp in tool_page.get("subpages_fetched", [])]
                tool_page_section += f"""

SUB-PAGES ({', '.join(fetched_labels)}):
{subpage_text[:4000]}"""
    else:
        tool_page_section = "\nTOOL'S OFFICIAL PAGE: Could not be fetched. Be explicit about what you could not verify."

    prompt = f"""You are an AI tool analyst writing a concise report for content creators about a tool promoted in an Instagram reel.

=== RULES ===
1. Say what the thing IS in the first sentence: app, gallery, prompt pack, repo, plugin. Never call a gallery a "generator."
2. NEVER invent steps not on the official page. Write "not seen on the page" if unsure.
3. YOU HAVE WEB SEARCH. Search for the tool on Reddit, Product Hunt, YouTube, Hacker News. Cite what you find.
4. Use these statuses:
   - CONFIRMED: Feature on the official page OR third-party evidence
   - REPORTED: Third party mentioned, can't verify specific detail
   - SELF-REPORTED: Creator's or tool's own claim
   - NOT FOUND: Searched, found nothing (not the same as "false")
   - CONTRADICTED: Evidence contradicts the claim
5. Scoring (strict, most tools 3-6):
   - 8-10: Breaking news, still rising, can't be copied. RARE.
   - 5-7: Real interest but average.
   - 1-4: Old news, crowded, little evidence.
   Every score MUST cite a number or fact.
6. Split "browse/copy" from "make content." List paid dependencies as their own step.
7. List any domains with similar names (lookalikes).
8. Third-party write-ups mean interest, not virality. Coverage ≠ spread.

=== INPUTS ===

REEL CONTENT (from Instagram):
Creator: {content.get('title', 'unknown')}
URL: {reel_url}
Caption/text:
{_clean_text(reel_text[:3000])}

{tool_page_section}

=== OUTPUT (valid JSON only) ===

{{
  "is_reel_report": true,
  "what_it_is": "One sentence: what this tool actually is.",
  "tool_name": "{tool_info.get('tool_name', 'Unknown')}",
  "tool_url": "{tool_url or 'unknown'}",
  "reel_viewed": {{
    "creator": "handle",
    "caption_summary": "2-3 key points",
    "engagement": "visible numbers or 'not available'",
    "on_screen": "what was visible",
    "not_seen": "what couldn't be determined"
  }},
  "evidence_list": [
    {{"fact": "what you found", "status": "CONFIRMED|REPORTED|SELF-REPORTED|NOT FOUND|CONTRADICTED", "source_url": "url", "date": "date or null"}}
  ],
  "setup_steps": [
    {{"step_num": 1, "what_to_do": "step", "time_estimate": "X min", "time_source": "page|my estimate", "cost": "$0 or $X/mo"}}
  ],
  "total_time": {{
    "from_nothing": "X min",
    "if_ready": "Y min"
  }},
  "risks": "what install does, or null",
  "tryability": {{
    "free_tier": "Free / Freemium / Paid",
    "developer_score": "X/10",
    "non_coder_score": "X/10",
    "time_to_first_result": "estimate"
  }},
  "claim_check": {{
    "confirmed": [{{"claim": "text", "source": "where"}}],
    "cannot_confirm": [{{"claim": "text", "reason": "why"}}]
  }},
  "scorecard": [
    {{"metric": "Trend fit", "score": "X/10", "why": "cite evidence"}},
    {{"metric": "Uniqueness", "score": "X/10", "why": "cite evidence"}},
    {{"metric": "Shareability", "score": "X/10", "why": "cite evidence"}},
    {{"metric": "Tryability", "score": "X/10", "why": "cite evidence"}},
    {{"metric": "Overall", "score": "X/10", "why": "weighted"}}
  ],
  "distinct_angle": "What's verifiable that the reel missed — the creator's edge.",
  "reel_hooks": [
    {{"name": "hook concept", "description": "Full hook with tension and data"}},
    {{"name": "second hook", "description": "Different angle"}},
    {{"name": "third hook", "description": "Third angle"}}
  ],
  "sources": [{{"title": "name", "url": "url"}}]
}}"""

    text = generate_with_search(client, prompt, prefer_model="gpt-4o")

    try:
        result = _parse_json_response(text)
        result["is_reel_report"] = True
        if tool_page and tool_page.get("ok"):
            result["_tool_page_fetched"] = True
            result["_tool_page_url"] = tool_url
        return result
    except (json.JSONDecodeError, ValueError):
        return {"error": "Could not parse reel analysis", "raw": text}


# ═══════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════

def analyze(content: dict) -> dict:
    """Full analysis pipeline: extract -> gather evidence -> analyze -> write hooks."""
    client = get_client()

    # Instagram reels get their own pipeline
    if content.get("source_type") == "instagram":
        return _analyze_reel(client, content)

    # ── Step 1: Extract claims (sees homepage + sub-pages) ──
    claims_data = extract_claims(client, content)

    if claims_data.get("not_ai_tool"):
        return {
            "tool_name": "N/A",
            "error": "not_ai_tool",
            "message": "This doesn't appear to be an AI tool.",
            "claims_data": claims_data,
        }

    if not claims_data.get("claims"):
        return {
            "tool_name": claims_data.get("tool_name", "Unknown"),
            "error": "no_claims",
            "message": "Could not extract any specific claims from this content.",
            "claims_data": claims_data,
        }

    tool_name = claims_data.get("tool_name", "Unknown")

    # ── Step 2: Gather evidence via web search (ONLY fact-finding) ──
    evidence_data = gather_evidence(client, tool_name, claims_data, content)

    # ── Step 3: Analyze with evidence (no search, just reasoning) ──
    result = analyze_with_evidence(client, claims_data, content, evidence_data)
    result["claims_data"] = claims_data

    # ── Step 4: Write hooks from evidence (focused creative call) ──
    evidence_list = result.get("evidence_list", evidence_data.get("evidence", []))
    hooks = write_hooks(client, evidence_list, tool_name)
    if hooks and "content_verdict" in result:
        result["content_verdict"]["hooks"] = hooks

    return result
