"""Litmus — Test the Promise"""
import threading

import streamlit as st

import analyzer
import checks as C

DAILY_CAP = 40
STATUS_ICON = {"INDEPENDENT": "[v]", "CORROBORATED": "[v]", "OBSERVED": "[v]", "CONTRADICTED": "[x]",
               "SITE_SAYS": "[~]", "REEL_SAYS": "[~]", "UNCHECKED": "[?]", "UNVERIFIABLE": "[?]"}


@st.cache_resource
def _counter():
    return {"n": 0, "day": "", "lock": threading.Lock()}


def _check_cap():
    from datetime import date
    c = _counter()
    today = str(date.today())
    with c["lock"]:
        if c["day"] != today:
            c["n"], c["day"] = 0, today
        if c["n"] >= DAILY_CAP:
            return False
        c["n"] += 1
        return True


def _api_key():
    parts = [st.secrets.get("OPENAI_API_KEY", "")]
    for s in ("OPENAI_API_KEY_2", "OPENAI_API_KEY_3"):
        parts.append(st.secrets.get(s, ""))
    key = "".join(parts)
    return key if key.startswith("sk-") else ""


def _parse_input(text):
    """Extract URL from user input. Remainder is treated as caption."""
    text = text.strip()
    if not text:
        return "", "", ""
    parts = text.split(None, 1)
    first = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if "." in first or "://" in first:
        return first, rest, ""
    return "", text, ""


def _looks_like_caption(text):
    """Detect if input looks like a pasted social-media caption rather than a question."""
    t = text.strip()
    if len(t) < 80:
        return False
    if any(c in t for c in ("#", "\n")):
        return True
    if len(t) > 200:
        return True
    return False


def _format_result(r):
    """Format analysis result as flowing markdown matching the playbook standard."""
    sc = r["scores"]
    rpt = r["report"]
    lines = []

    # Title: just the name + what it is
    lines.append(f"### {C.esc(r['name'])}")
    lines.append(f"**{C.esc(r['what_it_is'])}**")
    lines.append("")

    # Summary
    if rpt.get("summary"):
        lines.append(C.esc(rpt["summary"]))
        lines.append("")

    # Tryability split
    tryability = rpt.get("tryability") or {}
    if any(tryability.get(k) for k in ("the_site", "the_tool", "time_to_result")):
        lines.append("**Tryability**")
        if tryability.get("the_site"):
            lines.append(f"- The site: {C.esc(tryability['the_site'])}")
        if tryability.get("the_tool"):
            lines.append(f"- The tool: {C.esc(tryability['the_tool'])}")
        if tryability.get("time_to_result"):
            lines.append(f"- Time to first result: {C.esc(tryability['time_to_result'])}")
        lines.append("")

    # Setup steps with time estimates
    steps = rpt.get("setup_steps") or []
    if steps:
        lines.append("**Setup time:** ~{} min estimated".format(
            sc.get("setup_minutes") or sum(
                int("".join(c for c in str(s.get("time", "5")) if c.isdigit()) or "5")
                for s in steps)))
        for i, step in enumerate(steps, 1):
            t = step.get("time", "")
            lines.append(f"- Step {i}: {C.esc(step.get('step', ''))} ({C.esc(t)} min)")
        lines.append("")
    else:
        sm = sc.get("setup_minutes")
        lines.append(f"**Setup time:** ~{sm} min estimated" if sm else "**Setup time:** ~5 min estimated")
        lines.append("")

    # Paid dependency
    pd = sc.get("paid_dependency")
    if pd is True:
        lines.append("**Paid dependency:** Yes — needs a paid service")
    elif pd is None:
        lines.append("**Paid dependency:** Unknown")
    else:
        lines.append("**Paid dependency:** No")
    lines.append("")

    # Scores table — rule-based, not LLM-generated
    br = "; ".join(sc.get("browse_reasons", [])) or "no issues"
    cr = "; ".join(sc.get("create_reasons", [])) or "no issues"
    n_conf = sc.get("n_confirmed_independent", 0)
    n_total = sc.get("n_independent", 0)
    ind_detail = f"{n_conf} verified, {n_total - n_conf} unverified" if n_total else "none found"
    lines.append("**Scores** (computed from access flags, not LLM opinion)")
    lines.append("")
    lines.append("| Metric | Score | How it was computed |")
    lines.append("|---|---|---|")
    lines.append(f"| Browse | {sc['browse']}/5 | Starts at 5. {br} |")
    lines.append(f"| Create | {sc['create']}/5 | Starts at 5. {cr} |")
    lines.append(f"| Crowdedness | {sc['crowded']} | {sc.get('crowded_reason', '')} |")
    lines.append(f"| Independent sources | {n_total} | {ind_detail} |")
    lines.append("")

    # How people are using it
    if rpt.get("how_people_use_it"):
        lines.append("**How people are using it**")
        lines.append(C.esc(rpt["how_people_use_it"]))
        lines.append("")

    # Claims table (confirmed vs cannot confirm)
    ct = rpt.get("claims_table") or []
    if ct:
        confirmed = [c for c in ct if c.get("status") == "confirmed"]
        cannot = [c for c in ct if c.get("status") != "confirmed"]
        lines.append("**Claims**")
        lines.append("| Confirmed | Cannot confirm |")
        lines.append("|---|---|")
        max_rows = max(len(confirmed), len(cannot))
        for i in range(max_rows):
            left = ""
            right = ""
            if i < len(confirmed):
                left = f"{C.esc(confirmed[i].get('claim', ''))} — {C.esc(confirmed[i].get('detail', ''))}"
            if i < len(cannot):
                right = f"{C.esc(cannot[i].get('claim', ''))} — {C.esc(cannot[i].get('detail', ''))}"
            lines.append(f"| {left} | {right} |")
        lines.append("")

    # Virality scorecard
    vs = rpt.get("virality_scorecard") or []
    if vs:
        lines.append("**Virality scorecard** (LLM estimate — treat as directional, not precise)")
        lines.append("| Dimension | Score | Why |")
        lines.append("|---|---|---|")
        for item in vs:
            dim = C.esc(item.get("dimension", ""))
            score = item.get("score", "?")
            mx = item.get("max", 10)
            reason = C.esc(item.get("reason", ""))
            lines.append(f"| {dim} | {score}/{mx} | {reason} |")
        lines.append("")

    if rpt.get("why_viral"):
        lines.append(f"**Why it could go viral:** {C.esc(rpt['why_viral'])}")
    if rpt.get("why_not_viral"):
        lines.append(f"**Why it might not:** {C.esc(rpt['why_not_viral'])}")
    if rpt.get("why_viral") or rpt.get("why_not_viral"):
        lines.append("")

    # Quick start
    if rpt.get("quick_start"):
        lines.append("**Quick start**")
        for i, step in enumerate(rpt["quick_start"], 1):
            lines.append(f"{i}. {C.esc(step)}")
        lines.append("")

    # Content hooks — split by hype vs gap
    hooks = rpt.get("hooks") or []
    hype = [h for h in hooks if h.get("type") == "hype"]
    gap = [h for h in hooks if h.get("type") == "gap"]
    other = [h for h in hooks if h.get("type") not in ("hype", "gap")]
    if hype:
        lines.append("**Hype hooks** (ride the excitement)")
        for h in hype:
            prin = f" *({C.esc(h.get('principle', ''))})*" if h.get("principle") else ""
            lines.append(f"- {C.esc(h['text'])}{prin}")
            if h.get("why_it_works"):
                lines.append(f"  Why it works: {C.esc(h['why_it_works'])}")
            if h.get("unverified_numbers"):
                nums_str = ", ".join(f'"{n}"' for n in h["unverified_numbers"])
                lines.append(f"  [!] {nums_str} not verified by our pipeline — illustrative number for virality")
        lines.append("")
    if gap:
        lines.append("**Gap hooks** (reveal the truth)")
        for h in gap:
            prin = f" *({C.esc(h.get('principle', ''))})*" if h.get("principle") else ""
            lines.append(f"- {C.esc(h['text'])}{prin}")
            if h.get("why_it_works"):
                lines.append(f"  Why it works: {C.esc(h['why_it_works'])}")
        lines.append("")
    if other:
        lines.append("**More hooks**")
        for h in other:
            lines.append(f"- **[{C.esc(h.get('type', 'hook'))}]** {C.esc(h['text'])}")
        lines.append("")

    # Reel structure
    rs = rpt.get("reel_structure") or {}
    if any(rs.get(k) for k in ("hook_0_2s", "demo_2_8s", "reveal_8_15s", "cta_15_20s")):
        lines.append("**Reel structure (20 sec)**")
        if rs.get("hook_0_2s"):
            lines.append(f"- 0-2s: {C.esc(rs['hook_0_2s'])}")
        if rs.get("demo_2_8s"):
            lines.append(f"- 2-8s: {C.esc(rs['demo_2_8s'])}")
        if rs.get("reveal_8_15s"):
            lines.append(f"- 8-15s: {C.esc(rs['reveal_8_15s'])}")
        if rs.get("cta_15_20s"):
            lines.append(f"- 15-20s: {C.esc(rs['cta_15_20s'])}")
        lines.append("")

    # Risk warnings
    rw = rpt.get("risk_warnings") or []
    if rw:
        lines.append("**Risk warnings**")
        for w in rw:
            lines.append(f"- {C.esc(w)}")
        lines.append("")

    # Bottom line
    if rpt.get("bottom_line"):
        lines.append(f"**Bottom line:** {C.esc(rpt['bottom_line'])}")
        lines.append("")

    # Distinct angle
    if rpt.get("distinct_angle"):
        lines.append(f"**Distinct angle:** {C.esc(rpt['distinct_angle']['text'])}")
        lines.append("")

    # Alternatives
    if r["research"].get("alternatives"):
        lines.append(f"**Alternatives:** {', '.join(C.esc(a) for a in r['research']['alternatives'])}")

    # Platforms searched
    if r["research"].get("platforms"):
        plat = ", ".join(f"{k} ({v})" for k, v in r["research"]["platforms"].items())
        lines.append(f"**Searched on:** {plat}")

    # Source list
    sl = rpt.get("sources_list") or []
    if sl:
        lines.append(f"**Sources:** {', '.join(C.esc(s) for s in sl)}")

    return "\n".join(lines)


# ── Page config ──────────────────────────────────────────────────────

st.set_page_config(page_title="Litmus", page_icon=":test_tube:", layout="centered")

# ── ChatGPT-inspired refinements (base dark theme via config.toml) ─
st.markdown("""<style>
/* Hide Streamlit chrome */
#MainMenu, footer, header, .stDeployButton {display: none !important;}

/* Center chat content */
.stMainBlockContainer {
    max-width: 48rem;
    margin: 0 auto;
    padding-top: 1rem;
}

/* Clean font */
body, .stMarkdown, .stChatMessage {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif !important;
}

/* Chat messages — transparent bg like ChatGPT */
.stChatMessage {
    background-color: transparent !important;
    border: none !important;
}
[data-testid="stChatMessageContent"] {
    background-color: transparent !important;
}

/* Chat input — dark pill */
.stChatInput > div {
    background-color: #303030 !important;
    border: 1px solid #444 !important;
    border-radius: 1.5rem !important;
}
.stChatInput textarea {
    color: #d1d1d1 !important;
}
[data-testid="stBottom"] {
    background-color: #212121 !important;
}

/* Sidebar buttons */
section[data-testid="stSidebar"] .stButton > button {
    background-color: #2a2a2a !important;
    border: 1px solid #444 !important;
    border-radius: 0.5rem !important;
    font-size: 0.85rem !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background-color: #3a3a3a !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #333 !important;
}
section[data-testid="stSidebar"] code {
    background-color: #2a2a2a !important;
}

/* Expanders */
.stExpander {
    background-color: #2a2a2a !important;
    border: 1px solid #3a3a3a !important;
    border-radius: 0.5rem !important;
}

/* Tables */
.stMarkdown th {
    background-color: #2a2a2a !important;
    border-color: #444 !important;
}
.stMarkdown td {
    border-color: #3a3a3a !important;
}

/* Buttons */
.stButton > button {
    background-color: #303030 !important;
    border: 1px solid #444 !important;
    border-radius: 0.5rem !important;
}
.stButton > button:hover {
    background-color: #404040 !important;
}
.stFormSubmitButton > button {
    background-color: #303030 !important;
    border: 1px solid #444 !important;
}

/* Status widget */
[data-testid="stStatusWidget"] {
    background-color: #2a2a2a !important;
    border-color: #444 !important;
}
</style>""", unsafe_allow_html=True)

pw = st.secrets.get("APP_PASSWORD", "")
if pw and not st.session_state.get("authed"):
    st.title("Litmus")
    st.caption("Test the Promise")
    entered = st.text_input("Password", type="password")
    if entered and entered == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.warning("Wrong password.")
    st.stop()

_key = _api_key()
if not _key:
    st.title("Litmus")
    st.caption("Test the Promise")
    st.error("OpenAI API key not configured. Add it in app secrets.")
    st.stop()

st.title("Litmus")
st.caption("Test the Promise — paste a URL, GitHub link, or Instagram caption.")

# ── Session state init ──────────────────────────────────────────────

if "user_context" not in st.session_state:
    st.session_state.user_context = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_reel" not in st.session_state:
    st.session_state.pending_reel = None
if "saved_analyses" not in st.session_state:
    st.session_state.saved_analyses = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None

# ── Sidebar: profile + saved analyses ──────────────────────────────

with st.sidebar:
    st.markdown("### Your profile")
    if st.session_state.user_context is None:
        with st.form("user_context_form"):
            budget = st.selectbox("Your budget", ["Free only", "Under $20/mo", "Under $50/mo", "Flexible"])
            experience = st.selectbox("Technical level", ["Non-technical", "Some coding", "Developer"])
            if st.form_submit_button("Save"):
                st.session_state.user_context = {
                    "budget": budget, "experience": experience, "use_case": "Instagram Reels"}
                st.rerun()
    else:
        ctx = st.session_state.user_context
        st.markdown(f"**{ctx['experience']}** · {ctx['budget']} · Instagram Reels")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Edit profile"):
                st.session_state.user_context = None
                st.rerun()
        with col2:
            if st.session_state.last_result and st.button("Re-analyze"):
                st.session_state["_rerender"] = True
                st.rerun()


    # History
    st.markdown("---")
    st.markdown("### History")
    if not st.session_state.saved_analyses:
        st.caption("No saved checks yet.")
    for i, saved in enumerate(st.session_state.saved_analyses):
        col_view, col_del = st.columns([4, 1])
        with col_view:
            if st.button(f"{saved['name']} — {saved['verdict']}", key=f"saved_{i}"):
                st.session_state["_view_saved"] = i
                st.rerun()
        with col_del:
            if st.button("x", key=f"del_{i}", help="Delete this saved check"):
                st.session_state.saved_analyses.pop(i)
                st.rerun()

    # MCP integration
    st.markdown("---")
    st.markdown("### Use in Claude Desktop")
    with st.expander("MCP setup (copy-paste)"):
        st.markdown("**1. Install dependencies**")
        st.code("pip install openai requests beautifulsoup4 mcp", language="bash")
        st.markdown("**2. Clone the repo**")
        st.code("git clone https://github.com/aprajitasinghugtbm2028-ops/portfolio.git",
                language="bash")
        st.markdown("**3. Add to Claude Desktop config**")
        st.markdown("Open `~/.claude/claude_desktop_config.json` and add:")
        st.code('''{
  "mcpServers": {
    "litmus": {
      "command": "python",
      "args": ["/path/to/portfolio/claim-checker/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key-here"
      }
    }
  }
}''', language="json")
        st.caption("Replace `/path/to/` with wherever you cloned the repo. "
                   "Uses the same OpenAI key as this app.")

# ── Re-render with new profile (no new API call) ───────────────────

if st.session_state.get("_rerender") and st.session_state.last_result:
    del st.session_state["_rerender"]
    r = st.session_state.last_result
    with st.chat_message("assistant"):
        with st.status("Re-analyzing with updated profile...", expanded=True) as status_box:
            try:
                new_report = analyzer.stage_report(
                    analyzer.OpenAILLM(_key),
                    {f["id"]: f for f in r["facts"]},
                    r["scores"], r["claims"],
                    user_context=st.session_state.get("user_context"))
                r["report"] = new_report
                st.session_state.last_result = r
            except Exception as e:
                status_box.update(label="Error", state="error")
                st.error(C.redact_secrets(str(e)))
                st.stop()
            status_box.update(label="Updated for your profile", state="complete")
        main_text = _format_result(r)
        st.markdown(main_text)
        st.session_state.messages.append({
            "role": "assistant", "content": main_text,
            "claims": r["claims"], "facts": r["facts"],
            "evidence": f"Re-rendered with profile: {st.session_state.user_context}"})
    st.stop()

# ── View saved analysis ─────────────────────────────────────────────

if st.session_state.get("_view_saved") is not None:
    idx = st.session_state.pop("_view_saved")
    if idx >= len(st.session_state.saved_analyses):
        st.rerun()
    saved = st.session_state.saved_analyses[idx]
    col_back, col_del = st.columns([3, 1])
    with col_back:
        if st.button("Back to chat"):
            st.rerun()
    with col_del:
        if st.button("Delete this check", type="secondary"):
            st.session_state.saved_analyses.pop(idx)
            st.rerun()
    st.markdown(f"### Saved: {C.esc(saved['name'])}")
    for msg in saved.get("messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"], unsafe_allow_html=False)
            if msg.get("claims"):
                with st.expander(f"Claims ({len(msg['claims'])})"):
                    for cl in msg["claims"]:
                        ic = STATUS_ICON.get(cl["verdict"], "[?]")
                        st.markdown(f"{ic} **{C.esc(cl['verdict'])}** — {C.esc(cl['text'])}")
            if msg.get("facts"):
                with st.expander(f"Verified facts ({len(msg['facts'])})"):
                    for f_ in msg["facts"]:
                        ic = STATUS_ICON.get(f_["status"], "[?]")
                        st.markdown(f"{ic} **{C.esc(f_['status'])}** — {C.esc(f_['text'])}")
            if msg.get("evidence"):
                with st.expander("Evidence detail"):
                    st.markdown(msg["evidence"])
    st.stop()

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=False)
        if msg.get("claims"):
            with st.expander(f"Claims ({len(msg['claims'])})"):
                for cl in msg["claims"]:
                    ic = STATUS_ICON.get(cl["verdict"], "[?]")
                    st.markdown(f"{ic} **{C.esc(cl['verdict'])}** — {C.esc(cl['text'])}")
        if msg.get("facts"):
            with st.expander(f"Verified facts ({len(msg['facts'])})"):
                for f in msg["facts"]:
                    ic = STATUS_ICON.get(f["status"], "[?]")
                    st.markdown(f"{ic} **{C.esc(f['status'])}** — {C.esc(f['text'])}")
        if msg.get("evidence"):
            with st.expander("Evidence detail"):
                st.markdown(msg["evidence"])

# ── Save / update / delete chat (right after conversation) ──────────
if st.session_state.messages and st.session_state.last_result:
    _r = st.session_state.last_result
    _saved_idx = next((i for i, s in enumerate(st.session_state.saved_analyses)
                       if s.get("url") == _r.get("url")), None)
    st.markdown("---")
    if _saved_idx is not None:
        _saved = st.session_state.saved_analyses[_saved_idx]
        col_s, col_d = st.columns([3, 1])
        with col_s:
            if len(_saved.get("messages", [])) < len(st.session_state.messages):
                if st.button("Update saved chat", type="primary"):
                    st.session_state.saved_analyses[_saved_idx]["messages"] = list(st.session_state.messages)
                    st.rerun()
            else:
                st.caption("Chat saved.")
        with col_d:
            if st.button("Delete saved", type="secondary"):
                st.session_state.saved_analyses.pop(_saved_idx)
                st.rerun()
    else:
        if st.button("Save this chat", type="primary"):
            st.session_state.saved_analyses.append({
                "name": _r.get("name", "Unknown"),
                "verdict": _r["verdict"],
                "url": _r.get("url", ""),
                "messages": list(st.session_state.messages)})
            st.rerun()


# ── Chat input ───────────────────────────────────────────────────────

if prompt := st.chat_input("Paste a URL, GitHub link, or Instagram caption"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Follow-up question (no URL, but we have a previous analysis)
    url, caption, on_screen = "", "", ""
    is_followup = False

    if st.session_state.pending_reel:
        url = st.session_state.pending_reel
        caption = prompt
        st.session_state.pending_reel = None
    else:
        url, caption, on_screen = _parse_input(prompt)

    if not url and st.session_state.last_result:
        is_followup = True
        r = st.session_state.last_result
        brief = [{"id": f["id"], "text": f["text"], "status": f["status"]}
                 for f in r["facts"]]
        context = (f"Previous analysis of {r['name']} ({r['url']}):\n"
                   f"Facts: {C.fence_text(str(brief))}\n"
                   f"Scores: {str(r['scores'])}\n"
                   f"Verdict: {r['verdict']}")
        with st.chat_message("assistant"):
            with st.status("Thinking...", expanded=True) as status_box:
                try:
                    answer = analyzer.OpenAILLM(_key).json(
                        "You are a helpful AI tool analyst. Answer based on the analysis context. "
                        "Be direct and specific. If the user asks for alternatives or workarounds, "
                        "give concrete steps. Reply as JSON: {\"answer\": \"your answer\"}",
                        f"{context}\n\nUser question: {prompt}")
                    resp = str(answer.get("answer", "I couldn't answer that."))
                except Exception as e:
                    resp = f"Error: {C.redact_secrets(str(e))}"
                status_box.update(label="Done", state="complete")
            st.markdown(resp)
            st.session_state.messages.append({"role": "assistant", "content": resp})
        st.stop()

    cap_used = False
    if not url and _looks_like_caption(prompt):
        if not _check_cap():
            resp = f"Daily limit reached ({DAILY_CAP} checks). Try again tomorrow."
            st.session_state.messages.append({"role": "assistant", "content": resp})
            with st.chat_message("assistant"):
                st.markdown(resp)
            st.stop()
        cap_used = True
        with st.chat_message("assistant"):
            with st.status("Identifying the tool from the caption...", expanded=True) as status_box:
                try:
                    _key = _api_key()
                    tool_info = analyzer.identify_tool_from_caption(
                        analyzer.OpenAILLM(_key), prompt,
                        progress=lambda s: status_box.write(s))
                except Exception as e:
                    tool_info = None
                    status_box.write(f"Error: {C.redact_secrets(str(e))}")
            if tool_info and tool_info.get("tool_url"):
                url = tool_info["tool_url"]
                caption = prompt
                tool_name = tool_info.get("tool_name", "")
                st.markdown(f"Found **{C.esc(tool_name)}** — analyzing {C.esc(url)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Found **{C.esc(tool_name)}** — analyzing {C.esc(url)}"})
            else:
                resp = ("I couldn't identify a specific tool from that caption. "
                        "Try pasting the tool's website URL or GitHub link instead.")
                st.session_state.messages.append({"role": "assistant", "content": resp})
                st.markdown(resp)
                st.stop()

    if not url:
        resp = "Paste a URL to check (e.g. `prompt-motion.com` or `github.com/org/repo`)."
        st.session_state.messages.append({"role": "assistant", "content": resp})
        with st.chat_message("assistant"):
            st.markdown(resp)
        st.stop()

    if not cap_used and not _check_cap():
        resp = f"Daily limit reached ({DAILY_CAP} checks). Try again tomorrow."
        st.session_state.messages.append({"role": "assistant", "content": resp})
        with st.chat_message("assistant"):
            st.markdown(resp)
        st.stop()

    with st.chat_message("assistant"):
        with st.status("Analyzing...", expanded=True) as status_box:
            try:
                r = analyzer.analyze(url, analyzer.OpenAILLM(_key), caption, on_screen,
                                     progress=lambda s: status_box.write(s),
                                     user_context=st.session_state.get("user_context"))
            except Exception as e:
                status_box.update(label="Error", state="error")
                err = C.redact_secrets(str(e))
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {err}"})
                st.stop()
            status_box.update(label="Analysis complete", state="complete")

        if r["state"] == "error":
            msg = C.esc(r.get("message", "Unknown error"))
            if "instagram" in url.lower() and "caption" in r.get("message", "").lower():
                st.markdown("I couldn't read this Instagram reel automatically. "
                            "Could you paste the caption (and any on-screen text) in the chat?")
                st.session_state.pending_reel = url
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "I couldn't read this Instagram reel automatically. "
                               "Could you paste the caption (and any on-screen text) in the chat?"})
            else:
                st.markdown(f"Could not analyze: {msg}")
                st.session_state.messages.append({"role": "assistant", "content": f"Could not analyze: {msg}"})
            st.stop()

        if r["state"] == "thin":
            msg = C.esc(r.get("message", "Too little text."))
            st.markdown(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.stop()

        # Store full result for re-render and follow-ups
        st.session_state.last_result = r

        # Format main output
        main_text = _format_result(r)
        st.markdown(main_text)

        # Expandable detail sections
        facts_by_id = {f["id"]: f for f in r["facts"]}
        with st.expander(f"Claims ({len(r['claims'])})"):
            for cl in r["claims"]:
                ic = STATUS_ICON.get(cl["verdict"], "[?]")
                st.markdown(f"{ic} **{C.esc(cl['verdict'])}** — {C.esc(cl['text'])}")
                eids = cl.get("evidence_ids") or []
                for eid in eids:
                    ef = facts_by_id.get(eid)
                    if ef:
                        src = C.esc(ef.get("url", ""))
                        st.caption(f"  {eid}: {C.esc(ef['text'])} [{ef['status']}] — {src}")

        with st.expander(f"Verified facts ({len(r['facts'])})"):
            for f in r["facts"]:
                ic = STATUS_ICON.get(f["status"], "[?]")
                src = f" — {C.esc(f['url'])}" if f.get("url") else ""
                corr = ""
                if f.get("corroborated_by"):
                    cf = facts_by_id.get(f["corroborated_by"])
                    if cf:
                        corr = f" (corroborated by {f['corroborated_by']}: {C.esc(cf['text'][:60])})"
                st.markdown(f"{ic} **{C.esc(f['status'])}** — {C.esc(f['text'])}{corr}")
                st.caption(f"  Source: {C.esc(f.get('url', 'unknown'))} | Origin: {f.get('origin', '?')}")

        evidence_lines = []
        if r.get("investigation", {}).get("investigated"):
            inv_list = r["investigation"]["investigated"]
            evidence_lines.append(f"**Conditional branches run:** {len(inv_list)}")
            for branch in inv_list:
                if branch.startswith("pricing:"):
                    svc = branch.split(":", 1)[1]
                    evidence_lines.append(f"- Pricing: {C.esc(svc)} — triggered because tool's own pages mention this service as a dependency")
                elif branch.startswith("deps:"):
                    fname = branch.split(":", 1)[1]
                    evidence_lines.append(f"- Dependencies: parsed {C.esc(fname)} from repository (code, no LLM)")
                else:
                    evidence_lines.append(f"- {C.esc(branch)}")
        if r.get("dropped_facts"):
            evidence_lines.append(f"**Rejected facts (quote not on page):** {len(r['dropped_facts'])}")
        if r["research"].get("rejected"):
            evidence_lines.append(f"**Rejected research findings:** {len(r['research']['rejected'])}")
            for item in r["research"]["rejected"]:
                if isinstance(item, dict):
                    evidence_lines.append(f"- {C.esc(item.get('reason', ''))} — {C.esc(str(item.get('text', ''))[:80])}")
        if r["report"].get("hooks_rejected"):
            evidence_lines.append(f"**Rejected hooks:** {len(r['report']['hooks_rejected'])}")
            for h in r["report"]["hooks_rejected"]:
                evidence_lines.append(f"- {C.esc(h.get('reason', ''))} — {C.esc(h['text'][:80])}")
        if r["research"].get("lookalikes"):
            evidence_lines.append(f"**Lookalike domains:** {', '.join(C.esc(d) for d in r['research']['lookalikes'])}")
        evidence_lines.append(f"Models used: {', '.join(r.get('models', []))}")
        evidence_lines.append(f"Verdict: {C.esc(r['verdict'])} — {C.esc(r['verdict_rule'])}")
        evidence_text = "\n\n".join(evidence_lines)

        with st.expander("Evidence detail"):
            st.markdown(evidence_text)

        # Save to chat history
        st.session_state.messages.append({
            "role": "assistant", "content": main_text,
            "claims": r["claims"], "facts": r["facts"], "evidence": evidence_text})
