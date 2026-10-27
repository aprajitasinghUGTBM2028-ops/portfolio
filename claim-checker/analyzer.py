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
    """Verify claims with live web search, structured evidence, and hook validation."""

    claims_json = json.dumps(claims_data, indent=2)

    # Build source text with sub-pages
    pricing_info = ""
    if content.get("source_type") == "web" and content.get("has_pricing_signals"):
        pricing_info = "\nNote: The page contains pricing-related language."
    if content.get("source_type") == "github":
        meta = content.get("meta", {})
        pricing_info = f"\nGitHub stats — Stars: {meta.get('stars', '?')}, Language: {meta.get('language', '?')}, Last push: {meta.get('last_push', '?')}"

    source_text = ""
    subpage_text = ""
    if content.get("source_type") == "github":
        source_text = content.get("readme", "")[:6000]
    elif content.get("source_type") == "web":
        source_text = content.get("text", "")[:6000]
        subpage_text = content.get("subpage_text", "")[:6000]
    elif content.get("source_type") == "instagram":
        source_text = content.get("caption", content.get("text", ""))[:3000]

    tool_type = claims_data.get("tool_type", "unknown")
    key_data = json.dumps(claims_data.get("key_data_points", []))

    subpage_section = ""
    if subpage_text:
        fetched_labels = [sp["label"] for sp in content.get("subpages_fetched", [])]
        subpage_section = f"""
SUB-PAGES FETCHED ({', '.join(fetched_labels)}):
{subpage_text}
"""

    prompt = f"""You are a skeptical AI tool investigator with web search. A content creator pasted a URL. Your job: check if it's legit or hype.

=== EVIDENCE RULES ===

1. The HOMEPAGE and SUB-PAGES below are what the tool CLAIMS. A feature visible on the official page (a Customize page, a Subscribe box, a pricing table) is CONFIRMED as existing. But claims about quality, results, or popularity need THIRD-PARTY evidence.
2. YOU HAVE WEB SEARCH. Use it. Search for the tool on Reddit, Twitter/X, Hacker News, Product Hunt, YouTube. Search "[tool name] review", "[tool name] reddit", "[tool name] site:reddit.com", etc.
3. Use these EXACT statuses for each claim:
   - CONFIRMED: Feature exists on the official page, OR third-party source backs it up.
   - REPORTED: A third party mentioned it but you can't verify the specific detail.
   - SELF-REPORTED: The tool/creator's own number or claim. Label it as such.
   - NOT FOUND: You searched and found nothing. "NOT FOUND" ≠ "false" — say what you searched.
   - CONTRADICTED: Evidence contradicts the claim. Cite the contradiction.
4. NEVER write "I checked Reddit" or "I searched Product Hunt" unless you actually ran that search and its result is in your evidence. If you didn't search, don't claim you did.
5. Every number needs a source and a date. If the homepage says 233 but the blog says 199, show both.
6. Read the sub-pages below for features the homepage doesn't mention (customize pages, blog analysis, pricing details, sponsor info).
7. Dig for a distinct statistic — the site's blog or analysis pages often have one (e.g. "33 people used the same prompt, likes ranged 0 to 17,023").
8. Split "browse and copy" from "make a video" in setup. Give each its own time and cost. If making content requires a paid account (e.g. Claude Pro), list it as a separate step with cost.
9. Strip tracking parameters (?utm_...) from every source URL you output.
10. Search for lookalike sites with similar names and list them. Say they are not the official site.

=== SCORING RULES (most tools score 3-6, not 7-10) ===

VIRALITY (1-10): Every score MUST cite evidence. No evidence = no inflation.
- 1-2: Boring CLI tool, no visual output
- 3-4: Nothing new — another wrapper, another chatbot
- 5-6: Unique angle OR interesting output. Most good tools land here.
- 7-8: Genuinely novel with proven viral potential. RARE.
- 9-10: Cultural moment. Almost never.

HYPE (1-10):
- 1-3: Honest, understated. Open source README.
- 4-6: Normal marketing. Most tools.
- 7-8: Heavy unverified claims. "Revolutionary", big numbers with no proof.
- 9-10: Outright deceptive.

VERDICT:
- "COVER IT" = unique angle + data + audience cares. RARE.
- "COVER THE GAP" = interesting but creator needs their own angle. MOST COMMON.
- "SKIP" = nothing new, no data, audience won't care.

=== INPUTS ===

Tool type from extraction: {tool_type}

EXTRACTED CLAIMS:
{claims_json}

KEY DATA POINTS:
{key_data}

HOMEPAGE CONTENT:
{source_text}
{pricing_info}
{subpage_section}

=== OUTPUT FORMAT ===

Return ONLY valid JSON. The "evidence_list" is your structured fact sheet — every fact you cite anywhere must appear here first, with a source URL. Hooks may ONLY use facts from this list.

{{
  "tool_name": "{claims_data.get('tool_name', 'Unknown')}",
  "evidence_list": [
    {{
      "fact": "what you found",
      "status": "CONFIRMED|REPORTED|SELF-REPORTED|NOT FOUND|CONTRADICTED",
      "source_url": "the URL where you found this (stripped of UTM params), or 'official site' for features on the page, or null if not found",
      "date": "when this was published/found, or null"
    }}
  ],
  "verified_claims": [
    {{
      "claim": "the claim text",
      "verdict": "CONFIRMED|REPORTED|SELF-REPORTED|NOT FOUND|CONTRADICTED",
      "evidence": "cite from evidence_list — what you found and where",
      "red_flags": ["specific flag or empty array"]
    }}
  ],
  "tryability": {{
    "free_tier": "yes|no|freemium|unclear",
    "free_tier_detail": "quote what the source says",
    "setup_browse": {{"time": "X min", "cost": "$0", "steps": "what browsing/copying involves"}},
    "setup_create": {{"time": "X min", "cost": "$Y/mo for [service]", "steps": "what actually making content involves, including paid dependencies"}},
    "visible_result": "yes|no|unclear",
    "blockers": ["only real blockers"],
    "score": 4
  }},
  "setup_guide": [
    "Step 1: Browse — ...",
    "Step 2: Copy a prompt — ...",
    "Step 3: To make a video — ... (requires [paid service] at $X/mo)"
  ],
  "virality": {{
    "visual_wow": 5,
    "shareability": 4,
    "trend_fit": 5,
    "uniqueness": 4,
    "virality_score": 4,
    "virality_explanation": "cite evidence for each score"
  }},
  "comparison": {{
    "similar_to": "Think of it as [known tool] but for [niche]",
    "what_makes_it_different": "based on source content",
    "who_is_this_for": "specific person + specific need",
    "lookalike_warning": "list any similarly-named sites found and clarify they are not official, or null",
    "lookalike_sites": ["site1.com", "site2.com"]
  }},
  "content_verdict": {{
    "verdict": "COVER IT|COVER THE GAP|SKIP",
    "reason": "2-3 sentences citing evidence_list entries",
    "hooks": [
      "Hook 1 — must use ONLY facts from evidence_list. Include specific numbers.",
      "Hook 2 — different angle, still evidence-backed",
      "Hook 3 — third angle"
    ],
    "reel_format": "suggested format"
  }},
  "hype_score": 5,
  "summary": "2-3 honest sentences. What's confirmed, what's self-reported, what's not found."
}}"""

    text = generate_with_search(client, prompt, prefer_model="gpt-4o")

    try:
        result = _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        return {"error": "Could not parse verification response", "raw": text}

    # Hook validation pass: check hooks only use facts from evidence_list
    result = _validate_hooks(client, result)

    return result


def _validate_hooks(client, result: dict) -> dict:
    """Second pass: check that hooks only use facts from the evidence list."""
    hooks = result.get("content_verdict", {}).get("hooks", [])
    evidence = result.get("evidence_list", [])
    if not hooks or not evidence:
        return result

    evidence_json = json.dumps(evidence, indent=2)
    hooks_json = json.dumps(hooks, indent=2)

    prompt = f"""You are a fact-checker. Below is a list of verified evidence and a list of reel hooks.
Check each hook: does every number, claim, and action in the hook appear in the evidence list?

EVIDENCE LIST:
{evidence_json}

HOOKS:
{hooks_json}

For each hook, return:
- "valid": true if every fact in the hook is backed by the evidence list
- "valid": false if the hook contains a number, claim, or action NOT in the evidence
- "fix": if invalid, rewrite the hook using ONLY facts from the evidence list

Return ONLY valid JSON:
{{
  "hook_checks": [
    {{"hook_index": 0, "valid": true}},
    {{"hook_index": 1, "valid": false, "problem": "claims Reddit search but no Reddit evidence exists", "fix": "rewritten hook using only evidence"}}
  ]
}}"""

    try:
        text = generate(client, prompt)
        checks = _parse_json_response(text)
        validated_hooks = list(hooks)
        for check in checks.get("hook_checks", []):
            idx = check.get("hook_index", -1)
            if not check.get("valid") and check.get("fix") and 0 <= idx < len(validated_hooks):
                validated_hooks[idx] = check["fix"]
        if "content_verdict" in result:
            result["content_verdict"]["hooks"] = validated_hooks
    except Exception:
        pass
    return result


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
