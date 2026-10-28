"""AI Hype Claim Checker — Chat Interface"""
import threading

import streamlit as st

import analyzer
import checks as C

DAILY_CAP = 40
STATUS_ICON = {"INDEPENDENT": "[v]", "OBSERVED": "[v]", "CONTRADICTED": "[x]",
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
    """Format analysis result as flowing markdown."""
    sc = r["scores"]
    rpt = r["report"]
    lines = []

    lines.append(f"### {C.esc(r['name'])} — {C.esc(r['verdict'])}")
    lines.append(f"*{C.esc(r['verdict_rule'])}*")
    lines.append("")
    lines.append(f"**{C.esc(r['what_it_is'])}**")
    lines.append("")

    br = "; ".join(sc.get("browse_reasons", [])) or "no issues"
    cr = "; ".join(sc.get("create_reasons", [])) or "no issues"
    lines.append("| Metric | Score | Why |")
    lines.append("|---|---|---|")
    lines.append(f"| Browse | {sc['browse']}/5 | {br} |")
    lines.append(f"| Create | {sc['create']}/5 | {cr} |")
    lines.append(f"| Crowdedness | {sc['crowded']} | {sc.get('crowded_reason', '')} |")
    lines.append(f"| Independent sources | {sc['n_independent']} | — |")
    lines.append("")

    pd = sc.get("paid_dependency")
    if pd is True:
        lines.append("**Paid dependency:** Yes — needs a paid service")
    elif pd is None:
        lines.append("**Paid dependency:** Unknown — page does not clearly state")
    else:
        lines.append("**Paid dependency:** No")

    sm = sc.get("setup_minutes")
    lines.append(f"**Setup time:** {'~' + str(sm) + ' min' if sm is not None else 'not stated'}")
    lines.append("")

    lines.append(f"**Summary:** {C.esc(rpt['summary'])}")
    lines.append("")

    if rpt.get("quick_start"):
        lines.append("**Quick start**")
        for i, step in enumerate(rpt["quick_start"], 1):
            lines.append(f"{i}. {C.esc(step)}")
        lines.append("")

    if rpt.get("hooks"):
        lines.append("**Content hooks**")
        for h in rpt["hooks"]:
            lines.append(f"- **[{C.esc(h['type'])}]** {C.esc(h['text'])}")
        lines.append("")

    if rpt.get("bottom_line"):
        lines.append(f"**Bottom line:** {C.esc(rpt['bottom_line'])}")
    if rpt.get("virality_notes"):
        lines.append(f"**Virality:** {C.esc(rpt['virality_notes'])}")
    if rpt.get("uniqueness"):
        lines.append(f"**Uniqueness:** {C.esc(rpt['uniqueness'])}")
    if rpt.get("distinct_angle"):
        lines.append(f"**Distinct angle:** {C.esc(rpt['distinct_angle']['text'])}")
    if r["research"].get("alternatives"):
        lines.append(f"**Alternatives:** {', '.join(C.esc(a) for a in r['research']['alternatives'])}")

    if r["research"].get("platforms"):
        plat = ", ".join(f"{k} ({v})" for k, v in r["research"]["platforms"].items())
        lines.append(f"**Searched on:** {plat}")

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
                                     progress=lambda s: status_box.write(s))
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
        evidence_text = "\n\n".join(evidence_lines)

        with st.expander("Evidence detail"):
            st.markdown(evidence_text)

        # Save to history
        st.session_state.messages.append({
            "role": "assistant", "content": main_text,
            "claims": r["claims"], "facts": r["facts"], "evidence": evidence_text})
