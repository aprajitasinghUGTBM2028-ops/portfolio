"""
AI Hype Claim Checker — Streamlit Web Interface
Paste an AI tool's URL and get a verdict on what's real, what's hype,
and whether it's worth covering.
"""

import os
import streamlit as st
from fetcher import fetch
from analyzer import analyze

st.set_page_config(
    page_title="AI Hype Claim Checker",
    page_icon="🔍",
    layout="centered",
)

# ── Styling ──────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0 0.5rem;
    }
    .main-header h1 {
        font-size: 2rem;
        margin-bottom: 0.25rem;
    }
    .main-header p {
        color: #888;
        font-size: 1rem;
    }
    .verdict-cover { background: #d4edda; border-left: 4px solid #28a745; padding: 1rem; border-radius: 6px; }
    .verdict-gap { background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem; border-radius: 6px; }
    .verdict-skip { background: #f8d7da; border-left: 4px solid #dc3545; padding: 1rem; border-radius: 6px; }
    .claim-confirmed { color: #28a745; font-weight: 600; }
    .claim-partial { color: #ffc107; font-weight: 600; }
    .claim-exaggerated { color: #dc3545; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────

st.markdown("""
<div class="main-header">
    <h1>AI Hype Claim Checker</h1>
    <p>Paste an AI tool's URL. Get a verdict: what's real, what's hype, and whether it's worth covering.</p>
</div>
""", unsafe_allow_html=True)

# ── API Key ──────────────────────────────────────────────────────────

def sanitize_key(key):
    """Remove hidden unicode characters that sneak in from copy-paste."""
    if not key:
        return ""
    return str(key).encode("ascii", errors="ignore").decode("ascii").strip()

def get_api_key():
    """Check for API key in Streamlit secrets, then env, then sidebar input."""
    try:
        return sanitize_key(st.secrets["OPENAI_API_KEY"])
    except (KeyError, FileNotFoundError):
        return sanitize_key(os.environ.get("OPENAI_API_KEY", ""))

stored_key = get_api_key()

with st.sidebar:
    st.header("Settings")
    if stored_key:
        api_key = stored_key
        st.success("API key configured")
    else:
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="Get a key at https://platform.openai.com/api-keys",
        )
        st.markdown(
            "[Get an API key →](https://platform.openai.com/api-keys)",
        )
    st.divider()
    st.markdown("**How it works**")
    st.markdown(
        "1. Paste a URL (GitHub repo, landing page, or Instagram reel)\n"
        "2. The tool fetches the content\n"
        "3. GPT extracts and verifies claims\n"
        "4. You get a verdict with a content angle"
    )

# ── Input ────────────────────────────────────────────────────────────

col1, col2 = st.columns([4, 1])
with col1:
    url = st.text_input(
        "URL",
        placeholder="https://github.com/owner/cool-ai-tool",
        label_visibility="collapsed",
    )
with col2:
    check_btn = st.button("Check it", type="primary", use_container_width=True)

caption_input = None
if url and ("instagram.com" in url.lower()):
    caption_input = st.text_area(
        "Paste the Instagram caption (required for reels)",
        height=100,
    )

# ── Run ──────────────────────────────────────────────────────────────

if check_btn and url:
    if not api_key:
        st.error("Please enter your OpenAI API key in the sidebar.")
        st.stop()

    os.environ["OPENAI_API_KEY"] = api_key

    with st.status("Analyzing...", expanded=True) as status:
        # Step 1: Fetch
        st.write("Fetching content...")
        content = fetch(url)

        if content.get("needs_manual_input"):
            if not caption_input:
                st.error("Instagram reel detected — please paste the caption above and try again.")
                st.stop()
            content = {
                "ok": True,
                "source_type": "instagram",
                "url": url,
                "caption": caption_input,
                "text": caption_input,
            }

        if not content.get("ok"):
            st.error(f"Fetch failed: {content.get('error', 'Unknown error')}")
            st.stop()

        # Show fetch info
        if content["source_type"] == "github":
            meta = content.get("meta", {})
            st.write(f"Fetched GitHub repo: **{content['owner']}/{content['repo']}**")
            st.caption(f"⭐ {meta.get('stars', '?')} stars | {meta.get('language', '?')} | Last push: {str(meta.get('last_push', '?'))[:10]}")
        elif content["source_type"] == "web":
            st.write(f"Fetched page: **{content.get('title', url)}**")
        elif content["source_type"] == "instagram":
            st.write("Using provided Instagram caption")

        # Step 2-3: Analyze
        st.write("Extracting claims...")
        st.write("Verifying & scoring...")
        try:
            result = analyze(content)
        except RuntimeError as e:
            status.update(label="Analysis failed", state="error")
            st.error(str(e))
            st.stop()
        except Exception as e:
            status.update(label="Analysis failed", state="error")
            st.error(f"API error: {e}")
            st.stop()
        status.update(label="Analysis complete", state="complete")

    # ── Error states ─────────────────────────────────────────────────

    if result.get("error"):
        err = result["error"]
        if err == "not_ai_tool":
            st.warning("This doesn't appear to be an AI tool. The Claim Checker works best with AI tools, APIs, and platforms.")
        elif err == "no_claims":
            st.warning("Could not extract any specific claims from this content.")
        else:
            st.error(result.get("message", "Analysis failed."))
        st.stop()

    # ── Results ──────────────────────────────────────────────────────

    claims_data = result.get("claims_data", {})

    # Tool info
    st.markdown(f"### 🔍 {claims_data.get('tool_name', 'Unknown Tool')}")
    st.markdown(f"*{claims_data.get('tool_summary', '')}*")

    # Claims
    st.markdown("### 📋 Extracted Claims")
    for i, claim in enumerate(claims_data.get("claims", []), 1):
        cat = claim.get("category", "").replace("_", " ").title()
        st.markdown(f"**{i}. [{cat}]** {claim['claim']}")
        if claim.get("quote"):
            st.caption(f'"{claim["quote"]}"')

    # Verification
    st.markdown("### 🔬 Claim Verification")
    for i, vc in enumerate(result.get("verified_claims", []), 1):
        verdict = vc["verdict"]
        if verdict == "confirmed":
            icon, css_class = "✅", "claim-confirmed"
        elif verdict == "partially_true":
            icon, css_class = "⚠️", "claim-partial"
        else:
            icon, css_class = "❌", "claim-exaggerated"

        verdict_label = verdict.upper().replace("_", " ")
        st.markdown(f"**{i}. {vc['claim']}**")
        st.markdown(f"<span class='{css_class}'>{icon} {verdict_label}</span> — {vc.get('evidence', '')}", unsafe_allow_html=True)
        flags = vc.get("red_flags", [])
        if flags:
            st.markdown(f"🚩 *{', '.join(flags)}*")

    # Tryability
    st.markdown("### 🧪 Tryability")
    tryability = result.get("tryability", {})
    score = tryability.get("score", "?")
    if isinstance(score, int):
        st.progress(score / 5, text=f"Tryability: {score}/5")
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Free Tier", tryability.get("free_tier", "?"))
    col_b.metric("Setup Time", tryability.get("setup_time", "?"))
    col_c.metric("Visible Result", tryability.get("visible_result", "?"))
    blockers = tryability.get("blockers", [])
    if blockers:
        st.warning(f"**Blockers:** {', '.join(blockers)}")
    else:
        st.success("No blockers!")

    # Content Verdict
    st.markdown("---")
    cv = result.get("content_verdict", {})
    verdict = cv.get("verdict", "UNKNOWN")
    hype_score = result.get("hype_score", "?")

    if "COVER IT" in verdict.upper():
        css = "verdict-cover"
    elif "COVER THE GAP" in verdict.upper():
        css = "verdict-gap"
    else:
        css = "verdict-skip"

    hype_bar = "🔥" * int(hype_score) if isinstance(hype_score, int) else "?"

    st.markdown(f"""
<div class="{css}">
    <h3>📣 {verdict}</h3>
    <p><strong>Hype Score:</strong> {hype_bar} ({hype_score}/10)</p>
    <p>{cv.get('reason', '')}</p>
</div>
""", unsafe_allow_html=True)

    if cv.get("angle"):
        st.info(f"💡 **Content Angle:** {cv['angle']}")

    summary = result.get("summary", "")
    if summary:
        st.caption(summary)
