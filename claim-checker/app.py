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
    .claim-independent { color: #28a745; font-weight: 600; }
    .claim-site-says { color: #6c757d; font-weight: 600; }
    .claim-unverifiable { color: #ffc107; font-weight: 600; }
    .claim-contradicted { color: #dc3545; font-weight: 600; }
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
    """Remove hidden unicode characters and whitespace from copy-paste."""
    if not key:
        return ""
    raw = str(key)
    raw = "".join(raw.split())
    clean = "".join(c for c in raw if ord(c) < 128)
    return clean

def get_api_key():
    """Check for API key — try multiple secret fields, then env."""
    parts = []
    try:
        for k in ["OPENAI_API_KEY", "OPENAI_API_KEY2", "OPENAI_API_KEY3"]:
            if k in st.secrets:
                parts.append(str(st.secrets[k]))
        if parts:
            return sanitize_key("".join(parts))
    except (KeyError, FileNotFoundError):
        pass
    return sanitize_key(os.environ.get("OPENAI_API_KEY", ""))

stored_key = get_api_key()

# Password gate
def get_app_password():
    """Get app password from secrets or env."""
    try:
        if "APP_PASSWORD" in st.secrets:
            return str(st.secrets["APP_PASSWORD"]).strip()
    except (KeyError, FileNotFoundError):
        pass
    return os.environ.get("APP_PASSWORD", "")

app_password = get_app_password()

with st.sidebar:
    st.header("Settings")

    # Password protection
    if app_password:
        entered_pw = st.text_input("App Password", type="password", help="Enter the password to use this tool")
        if not entered_pw:
            st.warning("Enter the app password to continue.")
            st.stop()
        if entered_pw != app_password:
            st.error("Wrong password.")
            st.stop()

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

    # Usage counter
    if "usage_count" not in st.session_state:
        st.session_state.usage_count = 0
    daily_cap = 20
    st.caption(f"Checks today: {st.session_state.usage_count}/{daily_cap}")

    st.divider()
    st.markdown("**How it works**")
    st.markdown(
        "1. Paste a URL (GitHub repo, landing page, or Instagram reel)\n"
        "2. The tool fetches the page + sub-pages\n"
        "3. A 9-step AI pipeline classifies, searches, validates, and critiques\n"
        "4. You get an evidence-backed verdict with fact IDs"
    )
    st.caption("**Cost:** ~5-7 API calls per check (~$0.05-0.15). Uses GPT-4o with web search.")

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
    st.info("Instagram blocks auto-fetch most of the time. Paste the caption or what the creator says below — just the tool name + their claims is enough.")
    caption_input = st.text_area(
        "What does the reel say? (creator's caption, voiceover, or on-screen text)",
        height=120,
        placeholder='e.g. "This AI tool just replaced my entire design team. It\'s called ToolName and it generates videos from text in seconds..."',
    )

# ── Run ──────────────────────────────────────────────────────────────

if check_btn and url:
    if not api_key:
        st.error("Please enter your OpenAI API key in the sidebar.")
        st.stop()

    if st.session_state.usage_count >= daily_cap:
        st.error(f"Daily limit reached ({daily_cap} checks). Come back tomorrow or adjust the cap in secrets.")
        st.stop()

    os.environ["OPENAI_API_KEY"] = api_key
    st.session_state.usage_count += 1

    with st.status("Analyzing...", expanded=True) as status:
        # Step 1: Fetch
        st.write("Fetching content...")
        content = fetch(url)

        if content.get("needs_manual_input"):
            if not caption_input:
                status.update(label="Need caption", state="error")
                st.warning("Instagram blocked the auto-fetch (this is normal). Paste what the creator says in the box above and hit **Check it** again.")
                st.stop()
            content = {
                "ok": True,
                "source_type": "instagram",
                "url": url,
                "caption": caption_input,
                "text": caption_input,
            }
        elif content.get("source_type") == "instagram" and caption_input:
            content["caption"] = caption_input
            content["text"] = caption_input + "\n\n" + content.get("text", "")

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
            subpages = content.get("subpages_fetched", [])
            if subpages:
                labels = [sp.get("label", sp.get("url", "?")) for sp in subpages]
                st.caption(f"Sub-pages crawled: {', '.join(labels)}")
        elif content["source_type"] == "instagram":
            if content.get("auto_fetched"):
                method = content.get("fetch_method", "")
                st.write(f"Fetched Instagram content: **{content.get('title', url)}**")
                if content.get("caption_only"):
                    st.caption("Got the caption text. For full reel analysis (on-screen text, voiceover), paste what the creator says/shows in the box above.")
            else:
                st.write("Using provided Instagram caption")

        # Step 2-3: Analyze
        if content["source_type"] == "instagram":
            st.write("Identifying tool from reel...")
            st.write("Fetching official page...")
            st.write("Searching Reddit, HN, Product Hunt for independent verification...")
            st.write("Running full analysis...")
        else:
            st.write("Step 1/9: Classifying tool & planning research...")
            st.write("Step 2/9: Building source index...")
            st.write("Step 3/9: Searching for independent evidence...")
            st.write("Step 4/9: Extracting structured facts...")
            st.write("Step 5/9: Validating facts against sources...")
            st.write("Step 6/9: Filling evidence gaps...")
            st.write("Step 7/9: Writing report from validated facts...")
            st.write("Step 8/9: Critic checking report against evidence...")
            st.write("Step 9/9: Writing hooks from evidence...")
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

    # ── Parse/quality warnings ──────────────────────────────────────
    if result.get("_search_parse_failed"):
        st.warning("Some search results could not be parsed. Evidence may be incomplete.")
    if result.get("_gap_parse_failed"):
        st.warning("Gap-filling search results could not be parsed.")
    if result.get("_no_independent_sources"):
        st.warning("No independent (non-official) sources found. All evidence comes from the tool's own site.")

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

    if result.get("is_reel_report"):
        # ════════════════════════════════════════════════════════════
        # REEL REPORT FORMAT
        # ════════════════════════════════════════════════════════════

        tool_name = result.get("tool_name", "Unknown Tool")
        st.markdown(f"## {tool_name}: Tool Check")

        # ── What it is ──────────────────────────────────────────────
        what = result.get("what_it_is", "")
        if what:
            st.markdown(f"**What it is:** {what}")

        if result.get("_tool_page_fetched"):
            st.caption(f"Official page fetched: {result.get('_tool_page_url', '')}")

        # ── The reel I viewed ───────────────────────────────────────
        reel = result.get("reel_viewed", {})
        if reel:
            st.markdown("### The reel I viewed")
            creator = reel.get("creator", "unknown")
            st.markdown(f"**Creator:** {creator}")
            if reel.get("caption_summary"):
                st.markdown(f"**Caption:** {reel['caption_summary']}")
            if reel.get("engagement"):
                st.markdown(f"**Engagement:** {reel['engagement']}")
            if reel.get("on_screen"):
                st.markdown(f"**On screen:** {reel['on_screen']}")
            if reel.get("not_seen"):
                st.caption(f"Not seen: {reel['not_seen']}")

        # ── Setup ───────────────────────────────────────────────────
        steps = result.get("setup_steps", [])
        if steps:
            st.markdown("### Setup (plain language)")
            header = "| Step | What to do | Time | Source |"
            sep = "|---|---|---|---|"
            rows = [header, sep]
            for s in steps:
                num = s.get("step_num", "")
                what_do = s.get("what_to_do", "")
                time_est = s.get("time_estimate", "?")
                time_src = s.get("time_source", "")
                cost = s.get("cost")
                if cost and cost != "null" and cost != "$0":
                    what_do = f"{what_do} ({cost})"
                rows.append(f"| {num} | {what_do} | {time_est} | {time_src} |")
            st.markdown("\n".join(rows))

            total = result.get("total_time", {})
            if total:
                parts = []
                if total.get("from_nothing"):
                    parts.append(f"**From nothing:** {total['from_nothing']}")
                if total.get("if_ready"):
                    parts.append(f"**If ready:** {total['if_ready']}")
                if parts:
                    st.caption(" | ".join(parts))

        risks = result.get("risks")
        if risks and risks != "null":
            st.warning(f"**Risks:** {risks}")

        # ── Tryability ──────────────────────────────────────────────
        tryability = result.get("tryability", {})
        if tryability:
            st.markdown("### Tryability")
            cols = st.columns(4)
            cols[0].metric("Free Tier", tryability.get("free_tier", "?"))
            cols[1].metric("Developers", tryability.get("developer_score", "?"))
            cols[2].metric("Non-coders", tryability.get("non_coder_score", "?"))
            if tryability.get("time_to_first_result"):
                cols[3].metric("First Result", tryability["time_to_first_result"])

        # ── Claim Check ─────────────────────────────────────────────
        cc = result.get("claim_check", {})
        confirmed = cc.get("confirmed", [])
        cannot = cc.get("cannot_confirm", [])
        if confirmed or cannot:
            st.markdown("### Claim Check")
            col_c, col_u = st.columns(2)
            with col_c:
                st.markdown("**Confirmed**")
                if confirmed:
                    for c in confirmed:
                        st.markdown(f"- {c.get('claim', '')} *({c.get('source', '')})*")
                else:
                    st.caption("None confirmed independently")
            with col_u:
                st.markdown("**Cannot confirm**")
                if cannot:
                    for c in cannot:
                        st.markdown(f"- {c.get('claim', '')} *({c.get('reason', '')})*")
                else:
                    st.caption("All claims confirmed")

        # ── Scorecard ───────────────────────────────────────────────
        scorecard = result.get("scorecard", [])
        if scorecard:
            st.markdown("### Scorecard")
            header = "| Metric | Score | Why |"
            sep = "|---|---|---|"
            rows = [header, sep]
            for s in scorecard:
                rows.append(f"| {s.get('metric', '')} | {s.get('score', '?')} | {s.get('why', '')} |")
            st.markdown("\n".join(rows))

        # ── Distinct Angle ──────────────────────────────────────────
        angle = result.get("distinct_angle", "")
        if angle:
            st.markdown("### Distinct Angle")
            st.info(angle)

        # ── Reel Hooks ──────────────────────────────────────────────
        hooks = result.get("reel_hooks", [])
        if hooks:
            st.markdown("### Reel Hooks")
            for h in hooks:
                name = h.get("name", "Hook")
                desc = h.get("description", "")
                st.markdown(f"**{name}:** {desc}")

        # ── Sources ─────────────────────────────────────────────────
        sources = result.get("sources", [])
        if sources:
            st.markdown("### Sources")
            for s in sources:
                title = s.get("title", "")
                src_url = s.get("url", "")
                if src_url:
                    st.markdown(f"- [{title}]({src_url})")
                elif title:
                    st.markdown(f"- {title}")

    else:
        # ════════════════════════════════════════════════════════════
        # STANDARD REPORT FORMAT (web pages, GitHub repos)
        # ════════════════════════════════════════════════════════════

        claims_data = result.get("claims_data", {})

        # Tool info
        st.markdown(f"### {claims_data.get('tool_name', 'Unknown Tool')}")
        st.markdown(f"*{claims_data.get('tool_summary', '')}*")

        # Honest comparison (right up top so they get the context)
        comp = result.get("comparison", {})
        lw = comp.get("lookalike_warning")
        if lw and str(lw).lower() not in ("null", "none", "n/a", ""):
            st.warning(f"**Name alert:** {lw}")
        if comp.get("similar_to"):
            st.markdown(f"> {comp['similar_to']}")
        if comp.get("who_is_this_for"):
            st.caption(comp["who_is_this_for"])

        # ── Evidence Stats Banner ──────────────────────────────────
        ev_stats = result.get("_evidence_stats", {})
        if ev_stats:
            ind = ev_stats.get("independent", 0)
            ss = ev_stats.get("site_says", 0)
            unv = ev_stats.get("unverifiable", 0)
            total = ev_stats.get("total", 0)
            st.caption(f"Evidence: {total} items — {ind} independent, {ss} site-says, {unv} unverifiable")
        if result.get("_no_independent_sources"):
            st.warning("No independent sources found. All evidence comes from the tool's own site.")

        # ── Searches Run ───────────────────────────────────────────
        searches = result.get("_searches_run", [])
        if searches:
            with st.expander("Searches run", expanded=False):
                for s in searches:
                    found = s.get("found_results", s.get("found", False))
                    icon = "✅" if found else "❌"
                    st.caption(f"{icon} {s.get('query', '?')}")

        # ── Evidence List ──────────────────────────────────────────
        evidence_list = result.get("evidence_list", [])
        if evidence_list:
            with st.expander("Evidence Sheet (what was actually found)", expanded=False):
                for ev in evidence_list:
                    status = ev.get("status", "?")
                    status_icons = {
                        "SITE_SAYS": "📄", "INDEPENDENT": "✅",
                        "UNVERIFIABLE": "❓", "CONTRADICTED": "❌",
                    }
                    icon = status_icons.get(status, "•")
                    src = ev.get("source_url") or ""
                    date = ev.get("date") or ""
                    date_str = f" ({date})" if date else ""
                    st.markdown(f"{icon} **{status}** — {ev.get('fact', '')}")
                    if src and src not in ("null", "None", "official site", ""):
                        st.caption(f"Source: {src}{date_str}")

        # ── Claims & Verification ───────────────────────────────────
        st.markdown("### Claim Check")
        for i, vc in enumerate(result.get("verified_claims", []), 1):
            verdict = vc.get("verdict", "UNVERIFIABLE").upper()
            icon_map = {
                "SITE_SAYS": "📄", "INDEPENDENT": "✅",
                "UNVERIFIABLE": "❓", "CONTRADICTED": "❌",
            }
            icon = icon_map.get(verdict, "❓")

            st.markdown(f"**{i}. {vc['claim']}**")
            st.markdown(f"{icon} **{verdict}** — {vc.get('evidence', '')}")
            flags = vc.get("red_flags", [])
            if flags:
                st.markdown(f"🚩 *{', '.join(flags)}*")

        # ── Tryability ──────────────────────────────────────────────
        st.markdown("### Can You Actually Try This?")
        tryability = result.get("tryability", {})
        score = tryability.get("score", "?")
        if isinstance(score, (int, float)):
            st.progress(min(int(score), 5) / 5, text=f"Tryability: {int(score)}/5")

        col_a, col_b = st.columns(2)
        free_tier = tryability.get("free_tier", "?")
        free_detail = tryability.get("free_tier_detail", "")
        col_a.metric("Free Tier", free_tier)
        col_b.metric("Quick Result?", tryability.get("visible_result", "?"))

        if free_detail:
            st.caption(f"Free tier: {free_detail}")

        # Split tryability: browse vs create
        setup_browse = tryability.get("setup_browse", {})
        setup_create = tryability.get("setup_create", {})
        if setup_browse or setup_create:
            bc1, bc2 = st.columns(2)
            with bc1:
                st.markdown("**Browse & Copy**")
                if setup_browse:
                    st.markdown(f"Time: {setup_browse.get('time', '?')} | Cost: {setup_browse.get('cost', '$0')}")
                    if setup_browse.get("steps"):
                        st.caption(setup_browse["steps"])
            with bc2:
                st.markdown("**Make Content**")
                if setup_create:
                    st.markdown(f"Time: {setup_create.get('time', '?')} | Cost: {setup_create.get('cost', '?')}")
                    if setup_create.get("steps"):
                        st.caption(setup_create["steps"])

        blockers = tryability.get("blockers", [])
        if blockers:
            st.warning("**Blockers:** " + " / ".join(blockers))

        # ── Setup Guide ─────────────────────────────────────────────
        setup_steps = result.get("setup_guide", [])
        if setup_steps:
            st.markdown("### How to Try It (Step by Step)")
            for step in setup_steps:
                st.markdown(f"{step}")

        # ── Virality Assessment ─────────────────────────────────────
        virality = result.get("virality", {})
        if virality:
            st.markdown("### Will This Go Viral?")
            v_score = virality.get("virality_score", "?")
            if isinstance(v_score, (int, float)):
                st.progress(min(int(v_score), 10) / 10, text=f"Virality Potential: {int(v_score)}/10")

            v_cols = st.columns(4)
            v_cols[0].metric("Visual Wow", f"{virality.get('visual_wow', '?')}/10")
            v_cols[1].metric("Shareability", f"{virality.get('shareability', '?')}/10")
            v_cols[2].metric("Trend Fit", f"{virality.get('trend_fit', '?')}/10")
            v_cols[3].metric("Uniqueness", f"{virality.get('uniqueness', '?')}/10")

            if virality.get("virality_explanation"):
                st.caption(virality["virality_explanation"])

        # ── What Makes It Different ─────────────────────────────────
        if comp.get("what_makes_it_different"):
            st.info(f"**What's actually different:** {comp['what_makes_it_different']}")

        # ── Content Verdict ─────────────────────────────────────────
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

        st.markdown(f"""
<div class="{css}">
    <h3>{verdict}</h3>
    <p>{cv.get('reason', '')}</p>
</div>
""", unsafe_allow_html=True)

        if isinstance(hype_score, (int, float)):
            st.progress(min(int(hype_score), 10) / 10, text=f"Hype Score: {int(hype_score)}/10")
        else:
            st.markdown(f"**Hype Score:** {hype_score}/10")

        hooks = cv.get("hooks", [])
        if hooks:
            st.markdown("**Reel Hooks (evidence-backed):**")
            for i, h in enumerate(hooks, 1):
                st.markdown(f"{i}. *\"{h}\"*")
        elif cv.get("hook"):
            st.markdown(f'**Reel Hook:** *"{cv["hook"]}"*')
        if cv.get("reel_format"):
            st.caption(f"Suggested format: {cv['reel_format']}")

        # Lookalike sites warning
        lookalikes = comp.get("lookalike_sites", [])
        if lookalikes:
            st.warning(f"**Lookalike sites found:** {', '.join(lookalikes)} — these are NOT the official tool.")

        summary = result.get("summary", "")
        if summary:
            st.markdown(f"**Bottom line:** {summary}")
