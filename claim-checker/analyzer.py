"""
analyzer.py — Uses OpenAI GPT to extract claims, verify them,
score tryability, and produce a content verdict.
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
                    tools=[{"type": "web_search", "search_context_size": "medium"}],
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


def extract_claims(client, content: dict) -> list[dict]:
    """Extract hype claims from fetched content."""

    # Build context string based on source type
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
{content.get('text', '')}"""

    elif content["source_type"] == "instagram":
        context = f"""Instagram caption:
{content.get('caption', content.get('text', 'No caption provided'))}"""
    else:
        context = str(content)

    prompt = f"""You are a meticulous AI tool investigator. Your job is to READ THE SOURCE CONTENT CAREFULLY and extract ONLY what's actually there. You NEVER make assumptions or fill in gaps with guesses.

SOURCE CONTENT:
{context}

TASK — Read the source content above word by word before answering:

1. IDENTIFY THE TOOL TYPE from the source content. What does this tool ACTUALLY do? Choose the most accurate category:
   - Generator (creates new content from scratch)
   - Gallery/Directory (curates or showcases existing content)
   - Wrapper (puts a UI around another AI like GPT/Claude/Stable Diffusion)
   - Marketplace (sells templates, prompts, or assets)
   - Editor (modifies existing content)
   - Analyzer (examines or scores content)
   - Aggregator (collects data from multiple sources)
   - Other (explain what it is)
   BASE THIS ON WHAT THE SOURCE CONTENT DESCRIBES, not what the name sounds like.

2. FIND SPECIFIC NUMBERS AND DATA in the source content. Look for:
   - User counts, entries, items in the database
   - Statistics, research findings, studies mentioned
   - Pricing numbers, free tier details
   - Performance metrics, time savings
   - Any interesting data points that would make someone stop scrolling
   Quote these EXACTLY as they appear.

3. Extract 3-7 specific claims. For EACH claim:
   - Include the EXACT quote from the source where this claim appears
   - If there is no quote (you're inferring it), mark it as "implied"
   - Focus on what the source ACTUALLY SAYS, not what you think tools like this usually do

Return ONLY valid JSON:
{{
  "tool_name": "Name of the tool",
  "tool_type": "generator|gallery|wrapper|marketplace|editor|analyzer|aggregator|other",
  "tool_summary": "One honest line based ONLY on what the source content shows (e.g. 'A curated gallery of 233 AI-generated motion design videos with prompt details — not a generator')",
  "key_data_points": ["specific numbers/stats found in the source content"],
  "claims": [
    {{
      "claim": "The specific claim in plain language",
      "category": "capability|performance|ease_of_use|scope|cost",
      "quote": "The EXACT text from the source, or 'implied — no direct quote found'"
    }}
  ]
}}

If this doesn't appear to be an AI tool, return:
{{
  "tool_name": "N/A",
  "tool_summary": "This doesn't appear to be an AI tool",
  "claims": [],
  "not_ai_tool": true
}}"""

    text = generate(client, prompt)

    try:
        return _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        return {"tool_name": "Parse Error", "tool_summary": "Could not parse LLM response", "claims": [], "raw": text}


def verify_claims(client, claims_data: dict, content: dict) -> dict:
    """Verify each claim and score tryability."""

    claims_json = json.dumps(claims_data, indent=2)

    # Include pricing signals
    pricing_info = ""
    if content.get("source_type") == "web" and content.get("has_pricing_signals"):
        pricing_info = "\nNote: The page contains pricing-related language."
    if content.get("source_type") == "github":
        meta = content.get("meta", {})
        pricing_info = f"\nGitHub stats — Stars: {meta.get('stars', '?')}, Language: {meta.get('language', '?')}, Last push: {meta.get('last_push', '?')}"

    source_text = ""
    if content.get("source_type") == "github":
        source_text = content.get("readme", "")[:6000]
    elif content.get("source_type") == "web":
        source_text = content.get("text", "")[:6000]
    elif content.get("source_type") == "instagram":
        source_text = content.get("caption", content.get("text", ""))[:3000]

    tool_type = claims_data.get("tool_type", "unknown")
    key_data = json.dumps(claims_data.get("key_data_points", []))

    prompt = f"""You are a skeptical AI tool investigator. A content creator pasted a URL and wants to know: is this tool legit, or is it hype? Your job is to be HONEST, not generous.

=== THE #1 MISTAKE YOU MUST AVOID ===

CIRCULAR CONFIRMATION. This means marking a claim "confirmed" just because the tool's own website says it. A website saying "we have 10,000 users" is a CLAIM, not proof. The whole point of this tool is to check whether marketing claims are real.

Here is what GOOD vs BAD looks like:

CLAIM: "Over 200 curated motion design examples"
  BAD verdict: "confirmed — The source page states there are 103 Product UI and 96 Kinetic type entries"
  WHY BAD: You just read the website's own number back. That's the claim itself, not evidence.
  GOOD verdict: "unverified — The page lists 103 + 96 = 199 entries in its categories. I cannot independently verify these are real curated examples vs auto-generated filler. No Reddit/Twitter/YouTube discussion found to corroborate."

CLAIM: "AI-generated animations from text prompts"
  BAD verdict: "confirmed — The website describes AI-generated motion graphics"
  WHY BAD: The website CLAIMING it does something is not proof it does it.
  GOOD verdict: "partially_true — The site shows video thumbnails but I found no demo, no user reviews on Reddit/Twitter/Product Hunt, and no YouTube walkthroughs. The underlying claim is plausible (tools like Runway do this) but THIS specific tool has zero independent verification."

CLAIM: "Free to use"
  GOOD verdict: "confirmed — Site says 'free' and there's no paywall, login gate, or pricing page visible. Consistent with a gallery/showcase site that monetizes differently or is a side project."

=== SCORING RULES (most tools score 3-6, not 7-10) ===

VIRALITY SCORES (1-10):
- 1-2: Boring, no visual output, developer-only CLI tool
- 3-4: Decent but nothing new. Another AI wrapper, another chatbot, another "generate images" tool.
- 5-6: Has a unique angle OR produces genuinely interesting output. Most good tools land here.
- 7-8: Genuinely novel concept with proven viral potential. Think: first time someone showed AI removing objects from video.
- 9-10: Cultural moment. Almost never. Reserved for tools that broke Twitter/TikTok.
A niche gallery = 3-5 range. A wrapper around GPT = 3-4. An AI image generator = 4-6 unless it does something truly new.

HYPE SCORE (1-10):
- 1-3: Honest, understated marketing. Open source project with just a README.
- 4-6: Normal marketing language. Most tools are here. Claims features, shows demos, uses some superlatives.
- 7-8: Heavy marketing with unverified claims. "Revolutionary", "the future of X", big user numbers with no proof.
- 9-10: Outright deceptive. Fake screenshots, impossible claims, purchased reviews.

CONTENT VERDICT:
- "COVER IT" = genuinely unique angle + data to back it up + audience would care. RARE.
- "COVER THE GAP" = interesting enough but needs the creator to add their own angle. MOST COMMON.
- "SKIP" = nothing new, no data, audience won't care.

=== GUARDRAILS ===

1. SOURCE CONTENT is what the tool CLAIMS, not proof. Read it for data points and features, but treat every claim as "the website says X" — then ask "but is X actually true?"
2. YOU HAVE WEB SEARCH. Use it. For each claim, ACTUALLY SEARCH for the tool on Reddit, Twitter/X, Hacker News, Product Hunt, YouTube, and any relevant forums. Search for "[tool name] review", "[tool name] reddit", "[tool name] product hunt", etc.
3. ONLY mark "confirmed" when your web search found INDEPENDENT evidence: Reddit/HN/Twitter posts, Product Hunt listings, YouTube reviews, GitHub stars, app store reviews, blog posts from real users, or the technical architecture making the claim necessarily true.
4. If your web search found nothing → "unverified" with evidence: "Searched Reddit, Hacker News, Product Hunt, YouTube — zero independent mentions found. Only source is the tool's own website."
5. CITE what you find. "Found 3 Reddit posts in r/artificial discussing this tool (oldest from Jan 2024)" or "Product Hunt launch with 245 upvotes" — real data, real numbers.
6. NEVER INVENT features or steps not mentioned in the source. "Not mentioned on the page" beats a guess.
7. If the source says "free" or "It's free" → free_tier is "yes", free_tier_detail quotes it. Only say "unclear" if pricing is truly never mentioned.
8. The tool type from extraction was: {tool_type} — verify this. A gallery is NOT a generator.
9. Check for name lookalikes (e.g. "Motion" the design tool vs "PromptMotion" the gallery). If confusable, set lookalike_warning. Otherwise set it to null.

=== INPUTS ===

EXTRACTED CLAIMS:
{claims_json}

KEY DATA POINTS FROM SOURCE:
{key_data}

SOURCE CONTENT (this is what the website says — treat it as marketing, not truth):
{source_text}
{pricing_info}

=== OUTPUT FORMAT ===

Return ONLY valid JSON matching this structure:
{{
  "tool_name": "{claims_data.get('tool_name', 'Unknown')}",
  "verified_claims": [
    {{
      "claim": "the claim text",
      "verdict": "confirmed|partially_true|exaggerated|unverified",
      "evidence": "INDEPENDENT evidence or 'Only source is the website itself — no Reddit/Twitter/YouTube discussion found'",
      "red_flags": ["specific concrete flag, or empty array"]
    }}
  ],
  "tryability": {{
    "free_tier": "yes|no|freemium|unclear",
    "free_tier_detail": "quote what the source says about pricing",
    "setup_time_minutes": 5,
    "visible_result": "yes|no|unclear",
    "blockers": ["only blockers found in source content"],
    "score": 4
  }},
  "setup_guide": [
    "Step 1: ...",
    "Step 2: ..."
  ],
  "virality": {{
    "visual_wow": 5,
    "shareability": 4,
    "trend_fit": 5,
    "uniqueness": 4,
    "virality_score": 4,
    "virality_explanation": "one sentence with specific details — remember most tools score 3-6"
  }},
  "comparison": {{
    "similar_to": "Think of it as [known tool] but for [specific niche]",
    "what_makes_it_different": "one sentence based on source content",
    "who_is_this_for": "specific person + specific need",
    "lookalike_warning": "warning text or null"
  }},
  "content_verdict": {{
    "verdict": "COVER IT|COVER THE GAP|SKIP",
    "reason": "2-3 sentences. Be honest. Most tools are COVER THE GAP at best.",
    "hook": "A reel hook using ACTUAL NUMBERS or DATA from the source. Not a description of the tool. Example: '199 AI animations, zero Reddit posts. I checked if this gallery is real or just a pretty landing page.' GENERIC HOOKS LIKE 'Explore this amazing tool' ARE BANNED.",
    "reel_format": "suggested format"
  }},
  "hype_score": 5,
  "summary": "2-3 honest sentences. What's real, what's unverified, and the bottom line."
}}"""

    text = generate_with_search(client, prompt, prefer_model="gpt-4o")

    try:
        return _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        return {"error": "Could not parse verification response", "raw": text}


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
    """Full reel analysis pipeline: identify tool → fetch official page → analyze."""
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

    # Also try to extract URLs directly from the reel text
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

    # Step 3: Build the tool page context
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
            tool_page_section = f"""
TOOL'S OFFICIAL PAGE ({tool_url}):
Title: {tool_page.get('title', 'N/A')}
Meta: {tool_page.get('meta_description', '')}

Page content:
{tool_page.get('text', '')[:6000]}"""
    else:
        tool_page_section = "\nTOOL'S OFFICIAL PAGE: Could not be fetched. Base your analysis only on the reel content and your training knowledge. Be explicit about what you could not verify."

    # Step 4: Run reel-specific analysis
    prompt = f"""You are an AI tool analyst writing a concise report for content creators about a tool promoted in an Instagram reel. Follow these rules EXACTLY.

=== RULES ===

1. Say what the thing IS in the first sentence: an app, a gallery, a prompt pack, a repo, a plugin, an add-on. Never call a gallery a "generator."
2. NEVER invent steps. Don't describe a sign-up, trial, or payment unless the official page shows it. Otherwise write "not seen on the page."
3. YOU HAVE WEB SEARCH. Use it. Search for the tool on Reddit, Twitter/X, Hacker News, Product Hunt, YouTube. Search "[tool name] review", "[tool name] reddit", etc. Cite what you find with real numbers.
4. Mark every claim:
   - CONFIRMED: Your web search found evidence on a credible third-party source (Reddit post, YouTube review, Product Hunt listing, etc.)
   - REPORTED: A third party mentioned it but you can't independently verify the specific number/detail
   - CANNOT CONFIRM: Self-reported by the creator/tool, or your web search found nothing
5. Treat the reel creator's own numbers (engagement, results they claim) as CANNOT CONFIRM.
6. Scoring rubric (be STRICT — most tools score 3-6):
   - 8-10: News or traction in the last 30 days, still rising, hook can't be copied in an hour. RARE.
   - 5-7: Real interest but average, similar content already exists.
   - 1-4: Old news, crowded format, or little evidence of demand.
   Every score MUST cite a number or fact. No evidence = write "no evidence found" and don't inflate.
7. Keep it short. Cut anything the reader can't act on.
8. Don't repeat the reel's claims as findings — CHECK them using your web search against real sources.
9. For setup steps, mark which times come from the source and which are YOUR estimates.
10. List paid requirements (accounts, subscriptions, API keys) as their own step with cost.
11. If lookalike sites or similarly-named tools exist, warn about them.

=== INPUTS ===

REEL CONTENT (from Instagram):
Creator: {content.get('title', 'unknown')}
URL: {reel_url}
Caption/text:
{_clean_text(reel_text[:3000])}

{tool_page_section}

=== OUTPUT ===

Return ONLY valid JSON:
{{
  "is_reel_report": true,
  "what_it_is": "One sentence: what this tool actually is (app, gallery, repo, plugin, etc.). Be precise.",
  "tool_name": "{tool_info.get('tool_name', 'Unknown')}",
  "tool_url": "{tool_url or 'unknown'}",
  "reel_viewed": {{
    "creator": "the creator handle from the reel",
    "caption_summary": "2-3 key points from the caption",
    "engagement": "likes, comments, shares if visible in the fetched data, or 'not available from meta tags'",
    "on_screen": "what could be determined from the available content",
    "not_seen": "be honest: video frames, audio, full comments section, etc."
  }},
  "setup_steps": [
    {{
      "step_num": 0,
      "what_to_do": "prerequisite step if needed",
      "time_estimate": "5 min",
      "time_source": "my estimate",
      "cost": "$0 or $X/mo or null"
    }}
  ],
  "total_time": {{
    "from_nothing": "X min — if starting with nothing",
    "if_ready": "Y min — if prerequisites are met"
  }},
  "risks": "What the install edits, downloads, or asks for. Say if you didn't audit the code. null if no risks seen.",
  "tryability": {{
    "free_tier": "Free / Freemium ($X/mo for more) / Paid ($X) — based on official page, NOT the reel",
    "developer_score": "X/10",
    "non_coder_score": "X/10",
    "time_to_first_result": "estimate with reasoning"
  }},
  "claim_check": {{
    "confirmed": [
      {{"claim": "what was confirmed", "source": "where you saw evidence"}}
    ],
    "cannot_confirm": [
      {{"claim": "what can't be confirmed", "reason": "why — self-reported / no evidence / etc."}}
    ]
  }},
  "scorecard": [
    {{"metric": "Trend fit", "score": "X/10", "why": "specific reason citing evidence"}},
    {{"metric": "Uniqueness", "score": "X/10", "why": "specific reason"}},
    {{"metric": "Shareability", "score": "X/10", "why": "specific reason with numbers if available"}},
    {{"metric": "Tryability", "score": "X/10", "why": "specific reason"}},
    {{"metric": "Overall", "score": "X/10", "why": "weighted summary"}}
  ],
  "distinct_angle": "What is NOT in the reel that IS verifiable — the content creator's edge. Be specific.",
  "reel_hooks": [
    {{"name": "short name for the hook concept", "description": "Full hook description with on-screen text suggestion. Be creative and specific."}},
    {{"name": "second hook", "description": "A different creative angle"}},
    {{"name": "third hook", "description": "A third distinct angle"}}
  ],
  "sources": [
    {{"title": "Source name", "url": "the URL"}}
  ]
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


def analyze(content: dict) -> dict:
    """Full analysis pipeline: extract claims → verify → verdict."""
    client = get_client()

    # Instagram reels get the reel-specific pipeline
    if content.get("source_type") == "instagram":
        return _analyze_reel(client, content)

    # Everything else: standard pipeline
    claims_data = extract_claims(client, content)

    if claims_data.get("not_ai_tool"):
        return {
            "tool_name": "N/A",
            "error": "not_ai_tool",
            "message": "This doesn't appear to be an AI tool. The Claim Checker works best with AI tools, APIs, and platforms.",
            "claims_data": claims_data,
        }

    if not claims_data.get("claims"):
        return {
            "tool_name": claims_data.get("tool_name", "Unknown"),
            "error": "no_claims",
            "message": "Could not extract any specific claims from this content.",
            "claims_data": claims_data,
        }

    result = verify_claims(client, claims_data, content)
    result["claims_data"] = claims_data

    return result
