"""AI Hype Claim Checker — Chat Interface"""
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

    # Scores table
    br = "; ".join(sc.get("browse_reasons", [])) or "no issues"
    cr = "; ".join(sc.get("create_reasons", [])) or "no issues"
    lines.append("| Metric | Score | Why |")
    lines.append("|---|---|---|")
    lines.append(f"| Browse | {sc['browse']}/5 | {br} |")
    lines.append(f"| Create | {sc['create']}/5 | {cr} |")
    lines.append(f"| Crowdedness | {sc['crowded']} | {sc.get('crowded_reason', '')} |")
    lines.append(f"| Independent sources | {sc['n_independent']} | — |")
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
        lines.append("**Virality scorecard**")
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

    # Content hooks
    if rpt.get("hooks"):
        lines.append("**Content hooks**")
        for h in rpt["hooks"]:
            lines.append(f"- **[{C.esc(h['type'])}]** {C.esc(h['text'])}")
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

st.set_page_config(page_title="AI Hype Claim Checker", page_icon="V", layout="centered")

pw = st.secrets.get("APP_PASSWORD", "")
if pw and not st.session_state.get("authed"):
    st.title("AI Hype Claim Checker")
    entered = st.text_input("Password", type="password")
    if entered and entered == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.warning("Wrong password.")
    st.stop()

_key = _api_key()
if not _key:
    st.title("AI Hype Claim Checker")
    st.error("OpenAI API key not configured. Add it in app secrets.")
    st.stop()

st.title("AI Hype Claim Checker")
st.caption("Paste a tool URL. I'll search Reddit, HN, X, YouTube, LinkedIn, and more to check what's real.")

# ── User context (asked once per session) ────────────────────────────

if "user_context" not in st.session_state:
    st.session_state.user_context = None

with st.sidebar:
    if st.session_state.user_context is None:
        st.markdown("**Quick setup** (one time)")
        with st.form("user_context_form"):
            budget = st.selectbox("Your budget", ["Free only", "Under $20/mo", "Under $50/mo", "Flexible"])
            experience = st.selectbox("Technical level", ["Non-technical", "Some coding", "Developer"])
            use_case = st.selectbox("Content for", ["Instagram Reels", "YouTube Shorts", "TikTok", "All platforms"])
            if st.form_submit_button("Save"):
                st.session_state.user_context = {"budget": budget, "experience": experience, "use_case": use_case}
                st.rerun()
    else:
        ctx = st.session_state.user_context
        st.markdown(f"**You:** {ctx['experience']} · {ctx['budget']} · {ctx['use_case']}")
        if st.button("Edit profile"):
            st.session_state.user_context = None
            st.rerun()

# ── Chat state ───────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_reel" not in st.session_state:
    st.session_state.pending_reel = None

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


# ── Chat input ───────────────────────────────────────────────────────

if prompt := st.chat_input("Paste a tool URL (e.g. prompt-motion.com) or add caption for a reel"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # If waiting for reel caption, the whole input is caption text
    if st.session_state.pending_reel:
        url = st.session_state.pending_reel
        caption = prompt
        on_screen = ""
        st.session_state.pending_reel = None
    else:
        url, caption, on_screen = _parse_input(prompt)

    if not url:
        resp = "I need a URL to check. Paste something like `prompt-motion.com` or `https://github.com/org/repo`."
        st.session_state.messages.append({"role": "assistant", "content": resp})
        with st.chat_message("assistant"):
            st.markdown(resp)
        st.stop()

    if not _check_cap():
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

        # Format main output
        main_text = _format_result(r)
        st.markdown(main_text)

        # Expandable detail sections (inside the chat bubble)
        with st.expander(f"Claims ({len(r['claims'])})"):
            for cl in r["claims"]:
                ic = STATUS_ICON.get(cl["verdict"], "[?]")
                st.markdown(f"{ic} **{C.esc(cl['verdict'])}** — {C.esc(cl['text'])}")

        with st.expander(f"Verified facts ({len(r['facts'])})"):
            for f in r["facts"]:
                ic = STATUS_ICON.get(f["status"], "[?]")
                st.markdown(f"{ic} **{C.esc(f['status'])}** — {C.esc(f['text'])}")

        evidence_lines = []
        if r.get("investigation", {}).get("investigated"):
            evidence_lines.append(f"**Conditional branches run:** {', '.join(r['investigation']['investigated'])}")
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

        # Save to history
        st.session_state.messages.append({
            "role": "assistant", "content": main_text,
            "claims": r["claims"], "facts": r["facts"], "evidence": evidence_text})
