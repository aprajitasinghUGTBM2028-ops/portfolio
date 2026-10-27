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
    """Try multiple models with retries."""
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

    # Clean markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
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

    prompt = f"""You are a meticulous AI tool investigator writing for content creators. Your analysis must be TRACEABLE — every claim you make must point back to either the SOURCE CONTENT below or to specific external evidence you cite.

=== ABSOLUTE RULES (violating any of these makes your output useless) ===

RULE 1 — SOURCE CONTENT IS YOUR PRIMARY EVIDENCE.
Read the SOURCE CONTENT below line by line. If the source says "It's free" → free_tier is "yes". If the source shows 233 entries → mention 233 entries. If the source describes a gallery → it's a gallery, not a generator. DO NOT OVERRIDE what the source content says with your assumptions.

RULE 2 — NEVER INVENT FEATURES OR STEPS.
If the source content does not mention a signup process, DO NOT describe one. If the source doesn't mention email verification, DO NOT include it. If you didn't read about a specific feature in the source, DO NOT claim it exists. When unsure, say "not mentioned on the page" rather than guessing.

RULE 3 — NEVER CONFIRM BY CIRCULAR REASONING.
"Confirmed because the website says so" is NOT evidence — that's just reading the marketing back to them. Evidence means: your knowledge of the tool, Reddit/Twitter/HN/Product Hunt discussions, YouTube reviews, app store reviews, GitHub activity, blog posts, or the technical architecture proving the claim must be true.

RULE 4 — FIND THE INTERESTING DATA.
The source content contains specific numbers, statistics, or data points. These are GOLD for content creators. Find them and use them in your hooks and analysis. Numbers like "33 people typed the same prompt — likes ranged from 0 to 17,023" are 10x more valuable than "this tool has interesting features."

RULE 5 — IDENTIFY WHAT THE TOOL ACTUALLY IS.
The extraction identified this as: {tool_type}
Verify this against the source content. A gallery is NOT a generator. A wrapper is NOT a new AI. A curated collection is NOT a tool that creates things. Get this right — everything else depends on it.

RULE 6 — CHECK FOR LOOKALIKES.
Does this tool's name sound similar to a well-known tool? (e.g., "PromptMotion" vs "Prompt Motion" vs "Motion" the design tool). If yes, warn about confusion and clarify what THIS tool specifically is vs the lookalike.

=== INPUTS ===

EXTRACTED CLAIMS:
{claims_json}

KEY DATA POINTS FROM SOURCE:
{key_data}

SOURCE CONTENT (READ THIS CAREFULLY — this is your primary evidence):
{source_text}
{pricing_info}

=== SECTIONS ===

SECTION 1 — CLAIM VERIFICATION
For each claim, provide:
- verdict: "confirmed" / "partially_true" / "exaggerated" / "unverified"
- evidence: CITE YOUR SOURCE. Examples of good evidence:
  * "The source page explicitly states: '[exact quote]'"
  * "Known tool — discussed on Reddit r/singularity with 200+ upvotes (from my training data)"
  * "The underlying tech (Stable Diffusion) does support this capability"
  * "No public discussion found on Reddit, Twitter, Product Hunt, or YouTube — this is a red flag for a tool claiming 140K weekly visits"
  BAD evidence (BANNED): "Confirmed because the website claims it" / "Verified based on the tool's description"
- red_flags: Specific, concrete issues only. Not "may have limitations" but "claims 140K visits/week but has zero Reddit/Twitter discussion — suspicious"

SECTION 2 — TRYABILITY
Base this ONLY on what the source content shows:
- free_tier: If the source says "free" or "no cost", say "yes". If the source mentions pricing tiers, say "freemium" and explain. ONLY say "unclear" if the source genuinely doesn't mention pricing at all.
- free_tier_detail: Quote or paraphrase what the source says about pricing. If source says "It's free" → write "Site explicitly states it's free"
- setup_time_minutes: Estimate based ONLY on steps you can verify from the source. A simple website you just visit = 1 min. Don't add "email verification" unless the source mentions it.
- visible_result: Can they see/use something immediately? Base on source content.
- blockers: ONLY list blockers mentioned or clearly implied by the source content
- score: 1-5 based on the above. A free website with no signup = 4-5. A tool requiring API keys and coding = 1-2.

SECTION 3 — SETUP GUIDE
Write 3-6 steps based ONLY on what the source content describes.
- If it's a website you just visit: "1. Go to [url]  2. Browse [what's there]  3. [how to use it]"
- If the source doesn't describe a signup process: DO NOT INVENT ONE
- If it requires coding: say that in step 1
- If you genuinely don't know the steps because the source doesn't describe them: say "Steps unclear from available information — visit the site to explore"

SECTION 4 — VIRALITY ASSESSMENT
- visual_wow: 1-10 — Base on what the tool actually produces (from source content)
- shareability: 1-10 — Would the OUTPUT make someone screenshot/share?
- trend_fit: 1-10 — Current AI content trends
- uniqueness: 1-10 — Is this a new angle or done to death?
- virality_score: average of above, rounded
- virality_explanation: One sentence using SPECIFIC details from the source

SECTION 5 — HONEST COMPARISON
- similar_to: Compare to the RIGHT tool. If it's a gallery, compare to galleries (Pinterest, Dribbble). If it's a generator, compare to generators (Runway, Pika). Don't compare a gallery to a generator.
- what_makes_it_different: Based on source content — what specific feature/angle is unique?
- who_is_this_for: Specific person + specific need
- lookalike_warning: If the name could be confused with another tool, explain the difference. Otherwise null.

SECTION 6 — CONTENT VERDICT
- verdict: "COVER IT" / "COVER THE GAP" / "SKIP"
- reason: 2-3 sentences referencing SPECIFIC things from the source
- hook: Write a reel hook using ACTUAL DATA from the source. Use specific numbers, quotes, or findings. Example: "33 people typed the EXACT same AI prompt. One got 0 likes. Another got 17,023. Here's what was different." GENERIC HOOKS ARE BANNED.
- reel_format: Best format for this specific tool

Return ONLY valid JSON:
{{
  "tool_name": "{claims_data.get('tool_name', 'Unknown')}",
  "verified_claims": [
    {{
      "claim": "the claim text",
      "verdict": "confirmed|partially_true|exaggerated|unverified",
      "evidence": "specific evidence WITH SOURCE CITATION",
      "red_flags": ["specific flag"]
    }}
  ],
  "tryability": {{
    "free_tier": "yes|no|freemium|unclear",
    "free_tier_detail": "what the source says about pricing",
    "setup_time_minutes": 5,
    "visible_result": "yes|no|unclear",
    "blockers": ["only blockers found in source content"],
    "score": 1-5
  }},
  "setup_guide": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ..."
  ],
  "virality": {{
    "visual_wow": 1-10,
    "shareability": 1-10,
    "trend_fit": 1-10,
    "uniqueness": 1-10,
    "virality_score": 1-10,
    "virality_explanation": "one sentence with specific details from the source"
  }},
  "comparison": {{
    "similar_to": "Compare to the RIGHT category of tool",
    "what_makes_it_different": "one sentence based on source content",
    "who_is_this_for": "specific person + specific need",
    "lookalike_warning": "warning if name is confusable, or null"
  }},
  "content_verdict": {{
    "verdict": "COVER IT|COVER THE GAP|SKIP",
    "reason": "2-3 sentences referencing specific source data",
    "hook": "A reel hook using ACTUAL DATA/NUMBERS from the source",
    "reel_format": "suggested format"
  }},
  "hype_score": 1-10,
  "summary": "2-3 sentences referencing specific findings from the source content"
}}"""

    text = generate(client, prompt, prefer_model="gpt-4o")

    # Clean markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "Could not parse verification response", "raw": text}


def analyze(content: dict) -> dict:
    """Full analysis pipeline: extract claims → verify → verdict."""
    client = get_client()

    # Step 1: Extract claims
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

    # Step 2: Verify claims and get verdict
    result = verify_claims(client, claims_data, content)
    result["claims_data"] = claims_data

    return result
