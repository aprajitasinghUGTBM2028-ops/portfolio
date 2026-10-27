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
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set.\n"
            "Get one at https://platform.openai.com/api-keys"
        )
    api_key = api_key.encode("ascii", errors="ignore").decode("ascii").strip()
    if len(api_key) < 20:
        raise RuntimeError(
            "API key looks invalid after sanitization (too short).\n"
            "Re-paste your key in Streamlit secrets — make sure to use plain straight quotes."
        )
    return OpenAI(api_key=api_key)


def generate(client, prompt: str, **kwargs) -> str:
    """Try multiple models with retries."""
    prompt = _clean_text(prompt)
    last_error = None
    for model in MODELS:
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

    prompt = f"""You are an AI hype detector. Analyze this AI tool's marketing/description and extract the specific claims being made.

SOURCE CONTENT:
{context}

TASK:
1. First, identify what the tool/product IS (name, what it does, one line).
2. Extract 3-7 specific claims — things the tool says or implies it can do. Focus on:
   - Capability claims ("can generate X", "automates Y")
   - Performance claims ("10x faster", "saves hours")
   - Ease-of-use claims ("no code needed", "one click")
   - Scope claims ("works with any...", "universal")
   - Cost claims ("free", "open source")

Return ONLY valid JSON in this exact format:
{{
  "tool_name": "Name of the tool",
  "tool_summary": "One-line description of what it actually is",
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

    prompt = f"""You are a rigorous AI tool reviewer. Given the extracted claims about an AI tool, verify each one and assess how tryable this tool actually is.

Use your web search capability to look up current information about the tools and models mentioned. AI moves fast — verify model names, versions, pricing, and features against real-time web data rather than relying only on your training data.

EXTRACTED CLAIMS:
{claims_json}

SOURCE CONTENT (for reference):
{source_text}
{pricing_info}

TASK — For each claim, assess:
1. **Verdict**: "confirmed" (evidence supports it), "partially_true" (some truth but overstated), or "exaggerated" (you have positive evidence it's misleading)
2. **Evidence**: Brief explanation of why you gave that verdict
3. **Red flags**: Any issues (requires paid API, complex setup, limited scope, etc.)

Then assess TRYABILITY — can someone actually try this tool right now?
- free_tier: Is there a free option? (yes/no/unclear)
- setup_time: Rough estimate — under 10 min, 10-30 min, 30+ min, or unknown
- visible_result: Can you get a tangible output quickly? (yes/no/unclear)
- blockers: List any blockers (needs API key, requires signup, paid only, complex deps, etc.)

Finally, give a CONTENT VERDICT for a social media content creator:
- "COVER IT" — claims hold up, tool is tryable, good content potential
- "COVER THE GAP" — overhyped BUT interesting — the lie itself is the content angle
- "SKIP" — too expensive, too complex, too boring, or too niche

Return ONLY valid JSON:
{{
  "tool_name": "{claims_data.get('tool_name', 'Unknown')}",
  "verified_claims": [
    {{
      "claim": "the claim text",
      "verdict": "confirmed|partially_true|exaggerated",
      "evidence": "brief explanation",
      "red_flags": ["flag1", "flag2"]
    }}
  ],
  "tryability": {{
    "free_tier": "yes|no|unclear",
    "setup_time": "under 10 min|10-30 min|30+ min|unknown",
    "visible_result": "yes|no|unclear",
    "blockers": ["blocker1"],
    "score": 1-5
  }},
  "content_verdict": {{
    "verdict": "COVER IT|COVER THE GAP|SKIP",
    "reason": "One-paragraph explanation of why, written for a content creator deciding what to feature",
    "angle": "If covering, what's the content angle? The hook for a reel or post."
  }},
  "hype_score": 1-10,
  "summary": "2-3 sentence overall assessment"
}}"""

    text = generate(client, prompt, use_search=True)

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
