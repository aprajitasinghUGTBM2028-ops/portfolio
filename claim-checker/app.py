"""AI Hype Claim Checker — Streamlit UI"""
import threading

import streamlit as st

import analyzer
import checks as C

DAILY_CAP = 40
VERDICT_COLORS = {"COVER IT": "green", "COVER THE GAP": "orange",
                  "SKIP": "red", "INSUFFICIENT EVIDENCE": "gray"}
STATUS_EMOJI = {"INDEPENDENT": "V", "OBSERVED": "V", "CONTRADICTED": "X",
                "SITE_SAYS": "~", "REEL_SAYS": "~", "UNCHECKED": "?", "UNVERIFIABLE": "?"}


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


def api_key():
    parts = [st.secrets.get("OPENAI_API_KEY", "")]
    for s in ("OPENAI_API_KEY_2", "OPENAI_API_KEY_3"):
        parts.append(st.secrets.get(s, ""))
    key = "".join(parts)
    if not key.startswith("sk-"):
        st.error("OpenAI key not configured.")
        st.stop()
    return key


st.set_page_config(page_title="AI Hype Claim Checker", page_icon="V", layout="wide")
st.title("AI Hype Claim Checker")
st.caption("Paste an AI tool link. The checker verifies claims against what it can actually read and find.")

pw = st.secrets.get("APP_PASSWORD", "")
if not pw:
    st.error("App not configured (password missing).")
    st.stop()
if not st.session_state.get("authed"):
    entered = st.text_input("Password", type="password")
    if entered and entered == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.warning("Wrong password.")
    st.stop()

url = st.text_input("Tool URL", placeholder="https://example.com or github.com/org/repo")
col_cap, col_screen = st.columns(2)
caption = col_cap.text_area("Caption (for Instagram reels)", height=80)
on_screen = col_screen.text_area("On-screen text (for reels)", height=80)

if st.button("Check it", type="primary") and url:
    if not _check_cap():
        st.error(f"Daily limit reached ({DAILY_CAP} checks). Try again tomorrow.")
        st.stop()
    key = api_key()
    status = st.empty()
    try:
        r = analyzer.analyze(url, analyzer.OpenAILLM(key), caption, on_screen,
                             progress=lambda s: status.write(s))
    except Exception as e:
        st.error(C.redact_secrets(str(e)))
        st.stop()
    status.empty()

    if r["state"] == "error":
        st.error(C.esc(r.get("message", "Unknown error")))
        st.stop()
    if r["state"] == "thin":
        st.warning(C.esc(r.get("message", "Too little text to analyse.")))
        st.stop()

    color = VERDICT_COLORS.get(r["verdict"], "gray")
    st.markdown(f"## :{color}[**{C.esc(r['verdict'])}**]")
    st.caption(C.esc(r.get("verdict_rule", "")))

    st.markdown(f"**{C.esc(r['name'])}** — {C.esc(r['what_it_is'])}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Browse", f"{r['scores']['browse']}/5")
    c2.metric("Create", f"{r['scores']['create']}/5")
    c3.metric("Independent sources", r["scores"]["n_independent"])
    c4.metric("Crowdedness", r["scores"]["crowded"])

    rpt = r["report"]
    st.markdown(f"**Summary:** {C.esc(rpt['summary'])}")
    if rpt.get("bottom_line"):
        st.markdown(f"**Bottom line:** {C.esc(rpt['bottom_line'])}")

    if rpt.get("quick_start"):
        st.markdown("**Quick start:**")
        for i, step in enumerate(rpt["quick_start"], 1):
            st.markdown(f"{i}. {C.esc(step)}")

    if rpt.get("hooks"):
        st.markdown("**Content hooks:**")
        for h in rpt["hooks"]:
            st.markdown(f"- [{C.esc(h['type'])}] {C.esc(h['text'])}")

    if rpt.get("distinct_angle"):
        st.markdown(f"**Distinct angle:** {C.esc(rpt['distinct_angle']['text'])}")

    with st.expander("Claims"):
        for c in r["claims"]:
            em = STATUS_EMOJI.get(c["verdict"], "?")
            st.markdown(f"[{em} {C.esc(c['verdict'])}] {C.esc(c['text'])}")

    with st.expander("Verified facts"):
        for f in r["facts"]:
            em = STATUS_EMOJI.get(f["status"], "?")
            st.markdown(f"[{em} {C.esc(f['status'])}] {C.esc(f['text'])}")

    with st.expander("Evidence detail"):
        if r.get("dropped_facts"):
            st.markdown(f"**Rejected facts (quote not on page):** {len(r['dropped_facts'])}")
        if r["research"].get("rejected"):
            st.markdown(f"**Rejected research findings:** {len(r['research']['rejected'])}")
        if rpt.get("hooks_rejected"):
            st.markdown(f"**Rejected hooks:** {len(rpt['hooks_rejected'])}")
            for h in rpt["hooks_rejected"]:
                st.caption(f"  {C.esc(h.get('reason',''))} — {C.esc(h['text'][:80])}")
        if r["research"].get("lookalikes"):
            st.markdown(f"**Lookalike domains:** {', '.join(C.esc(d) for d in r['research']['lookalikes'])}")
        st.caption(f"Models used: {', '.join(r.get('models', []))}")
