"""
analyzer.py — Uses Google Gemini to extract claims, verify them,
score tryability, and produce a content verdict.
"""

import os
import json
import time
from google import genai
from google.genai import types

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]


def get_client():
    """Initialize and return the Gemini client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Get one free at https://aistudio.google.com/apikey\n"
            "Then run: export GEMINI_API_KEY='your-key-here'"
        )
    return genai.Client(api_key=api_key)


def generate(client, prompt: str, use_search: bool = False) -> str:
    """Try multiple models with retries. use_search enables Google Search grounding."""
    last_error = None
    config = None
    if use_search:
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    for model in MODELS:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt, config=config
                )
                return response.text.strip()
            except Exception as e:
                last_error = e
                err = str(e)
                if "503" in err or "UNAVAILABLE" in err:
                    time.sleep(2 ** attempt)
                    continue
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    time.sleep(5 * (attempt + 1))
                    continue
                if "404" in err or "NOT_FOUND" in err or "not found" in err.lower():
                    break
                if "400" in err or "INVALID" in err or "API key" in err.lower():
                    raise RuntimeError(
                        f"Gemini API error: {err}\n"
                        "Check that your API key is valid at https://aistudio.google.com/apikey"
                    )
                break
    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_error}\n"
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

EXTRACTED CLAIMS:
{claims_json}

SOURCE CONTENT (for reference):
{source_text}
{pricing_info}

IMPORTANT: Your training data has a cutoff date. AI moves fast — new models, tools, and versions launch constantly. If a claim references a model name, version, or tool you don't recognize, do NOT assume it's fake. Mark it "partially_true" with evidence noting you cannot verify it due to your knowledge cutoff, rather than "exaggerated." Only mark something "exaggerated" when you have positive evidence it's misleading, not just because you haven't heard of it.

TASK — For each claim, assess:
1. **Verdict**: "confirmed" (evidence supports it), "partially_true" (some truth but overstated, or cannot fully verify), or "exaggerated" (you have positive evidence it's misleading)
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
