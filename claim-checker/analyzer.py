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

    prompt = f"""You are a skeptical AI tool reviewer who has tested hundreds of tools. You don't take marketing at face value. You dig into what's ACTUALLY happening.

SOURCE CONTENT:
{context}

TASK:
1. Identify what this tool ACTUALLY is — not what it says it is. Be specific: "a wrapper around GPT-4 that generates blog posts" is better than "an AI writing assistant."
2. Extract 3-7 specific claims. For EACH claim, think: "What would I need to see to believe this?" Focus on:
   - Capability claims ("can generate X", "automates Y") — but what does it ACTUALLY do under the hood?
   - Performance claims ("10x faster", "saves hours") — compared to what? Says who?
   - Ease-of-use claims ("no code needed", "one click") — is there hidden complexity?
   - Scope claims ("works with any...", "universal") — what are the actual limits?
   - Cost claims ("free", "open source") — what's the catch? API costs? Usage limits?

Return ONLY valid JSON in this exact format:
{{
  "tool_name": "Name of the tool",
  "tool_summary": "One brutally honest line about what this actually is (e.g. 'A Streamlit app that calls Claude API to rewrite text — marketed as an AI writing revolution')",
  "claims": [
    {{
      "claim": "The specific claim in plain language",
      "category": "capability|performance|ease_of_use|scope|cost",
      "quote": "The exact or near-exact text from the source that makes this claim (if available)"
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
        source_text = content.get("readme", "")[:4000]
    elif content.get("source_type") == "web":
        source_text = content.get("text", "")[:4000]
    elif content.get("source_type") == "instagram":
        source_text = content.get("caption", content.get("text", ""))[:2000]

    prompt = f"""You are a brutally honest AI tool reviewer who has personally tested hundreds of tools. You don't just read marketing pages — you think about what ACTUALLY happens when someone tries this tool. You write for content creators who need to decide in 30 seconds: is this worth my time?

IMPORTANT RULES:
- NEVER say "confirmed" just because the website claims something. That's circular. Only confirm if you have INDEPENDENT evidence (your own knowledge, the tool's actual architecture, user reviews, GitHub activity, etc.)
- Before marking anything "unverified", ACTUALLY LOOK for evidence: think about Reddit threads, YouTube reviews, Twitter/X posts, Product Hunt launches, app store reviews, GitHub issues, blog reviews — real people talking about this tool. If nobody is talking about it, THAT ITSELF is evidence (a tool with no public discussion is a red flag). Say "no public reviews or social media discussion found" — don't just say "unverified without user feedback" and give up.
- If the tool is too new or obscure for public feedback, evaluate based on: the team behind it, similar tools that work the same way, whether the technical approach is sound, and red flags in the marketing.
- Be specific. "This tool is interesting" is banned. "This generates 30-second videos from a single text prompt, similar to Runway but focused on product demos" is good.
- Think about what a non-technical person would experience trying this for the first time.

EXTRACTED CLAIMS:
{claims_json}

SOURCE CONTENT (for reference):
{source_text}
{pricing_info}

SECTION 1 — CLAIM VERIFICATION
For each claim:
- verdict: "confirmed" (you have independent evidence), "partially_true" (has a catch), "exaggerated" (misleading), or "unverified" (searched but found no independent evidence)
- evidence: What SPECIFIC evidence do you have? Check these sources mentally:
  * Do you know this tool from your training data? Have people discussed it on Reddit, Twitter/X, Hacker News, Product Hunt?
  * Are there YouTube reviews, blog posts, or app store reviews?
  * Does the GitHub repo have real activity (stars, issues, contributors) or is it dead/empty?
  * Does the underlying technology (the API/model it uses) actually support what's claimed?
  * If zero public discussion exists, say that — it's a signal.
- red_flags: Concrete issues, not vague warnings

SECTION 2 — TRYABILITY (think like a non-coder friend asking "how do I try this?")
- free_tier: yes/no/freemium (free but limited)/unclear — and if freemium, what do you get for free?
- setup_time_minutes: Your honest estimate in minutes. Think through: do they need to sign up? Verify email? Enter payment? Install anything? Wait for access?
- visible_result: yes/no/unclear — can they get something cool to screenshot/screen-record within the first try?
- blockers: Be specific — not "requires signup" but "requires Google account signup + email verification, takes ~2 min"

SECTION 3 — SETUP GUIDE (write this for someone who has never used a terminal)
Write 3-6 numbered steps. Use plain English. Example:
  "1. Go to toolname.com and click Sign Up"
  "2. Sign in with your Google account (no credit card needed)"
  "3. Click 'New Project' and paste any text"
  "4. Hit Generate — you'll see your result in about 10 seconds"
If the tool requires coding or API keys, say that clearly in step 1 so they know upfront.

SECTION 4 — VIRALITY ASSESSMENT (think like a content strategist)
- visual_wow: 1-10 — Does this produce something that makes people stop scrolling? A text-based tool scores 2. A tool that generates stunning videos scores 9.
- shareability: 1-10 — Would someone screenshot/screen-record their result and share it? Can viewers immediately understand what they're seeing?
- trend_fit: 1-10 — Does this fit current social media trends (AI demos, before/after, "I replaced X with AI", tool reveals, etc.)?
- uniqueness: 1-10 — Is this the first tool doing this, or the 50th ChatGPT wrapper? Has this been covered to death already?
- virality_score: average of the above four, rounded
- virality_explanation: One sentence explaining the score honestly

SECTION 5 — HONEST COMPARISON
- similar_to: "Think of it as [well-known tool/concept] but [key difference]" — e.g. "Canva but for video ads" or "ChatGPT with a nicer UI, nothing new under the hood"
- what_makes_it_different: One sentence — what genuinely sets this apart? If nothing, say "Nothing — this is a wrapper/clone of [X]"
- who_is_this_for: One sentence — "Perfect for [specific person] who needs [specific thing]"

SECTION 6 — CONTENT VERDICT
- verdict: "COVER IT" / "COVER THE GAP" / "SKIP"
- reason: 2-3 sentences. Be opinionated. Would YOU make a reel about this?
- hook: Write the actual first line of a reel script. Not a generic "explore the capabilities" — write something like "This AI tool just made Canva obsolete. Here's what happened when I tested it." or "Everyone's hyping this tool but nobody's showing you THIS..."
- reel_format: Suggest the best format — "screen recording with voiceover", "before/after split", "reaction video", "tutorial walkthrough", "myth-busting", etc.

Return ONLY valid JSON:
{{
  "tool_name": "{claims_data.get('tool_name', 'Unknown')}",
  "verified_claims": [
    {{
      "claim": "the claim text",
      "verdict": "confirmed|partially_true|exaggerated|unverified",
      "evidence": "specific evidence, not just repeating the claim",
      "red_flags": ["specific flag"]
    }}
  ],
  "tryability": {{
    "free_tier": "yes|no|freemium|unclear",
    "free_tier_detail": "what you get for free, if anything",
    "setup_time_minutes": 5,
    "visible_result": "yes|no|unclear",
    "blockers": ["specific blocker with detail"],
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
    "virality_explanation": "one honest sentence"
  }},
  "comparison": {{
    "similar_to": "It's like X but Y",
    "what_makes_it_different": "one sentence",
    "who_is_this_for": "one sentence"
  }},
  "content_verdict": {{
    "verdict": "COVER IT|COVER THE GAP|SKIP",
    "reason": "2-3 opinionated sentences",
    "hook": "The actual first line of a reel script",
    "reel_format": "suggested format"
  }},
  "hype_score": 1-10,
  "summary": "2-3 sentence brutally honest assessment"
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
