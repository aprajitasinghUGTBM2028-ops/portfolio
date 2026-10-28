import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from datetime import date
import analyzer as A
import fetcher as F

PAGE = ("Prompt Motion is a collection of motion videos made with Claude Opus 5.5, with the prompts behind them. "
        "You can customize any prompt for your own project, and it is free to browse. "
        "We had 200k+ visits in the first week after launch, according to our sponsor page. ") * 2

class FakeLLM:
    used = {"fake"}
    def json(self, system, user, temperature=0.2):
        if "extract up to 14 facts" in user:
            return {"facts": [
                {"text": "A collection of motion videos made with Claude", "quote": "Prompt Motion is a collection of motion videos made with Claude Opus 5.5", "url": "https://prompt-motion.com/", "category": "capability"},
                {"text": "Customize any prompt", "quote": "You can customize any prompt for your own project", "url": "https://prompt-motion.com/", "category": "capability"},
                {"text": "200k+ visits in week one", "quote": "We had 200k+ visits in the first week after launch", "url": "https://prompt-motion.com/", "category": "popularity"},
                {"text": "Used by 5 million studios", "quote": "Trusted by five million studios worldwide", "url": "https://prompt-motion.com/", "category": "popularity"}],
                "access": {"free_to_browse": True, "needs_account": False, "paid_dependency": True, "needs_code": False,
                           "setup_minutes": 10, "claims_free": True, "access_quote": "it is free to browse"},
                "name": "Prompt Motion", "what_it_is": "Gallery of motion prompts", "audience": "designers"}
        if "Below is a research note" in user or "merged research note" in user:
            return {"findings": [
                {"text": "HN thread discusses it", "quote": "x" * 5, "url": "https://evil.example/post", "date": "2026-10-20", "kind": "discussion", "platform": "other"}],
                "lookalike_domains": ["promptmotion.com", "unrelated.org"], "alternatives": ["Runway", "Canva"]}
        if "marketing claims" in user or "most important marketing claims" in user:
            return {"claims": [
                {"text": "Free to customize", "category": "capability", "supports": ["F2"], "contradicts": []},
                {"text": "200k visits in week one", "category": "popularity", "supports": ["F3"], "contradicts": []}]}
        if "quick_start" in user and "scroll-stopping" not in user:
            return {"summary": "A gallery. Fine.", "quick_start": ["Open site", "Copy a prompt", "Pay for Claude to render"],
                    "bottom_line": "Mostly a prompt library.", "virality_notes": "Decent", "uniqueness": "Nothing notable"}
        if "scroll-stopping" in user:
            return {"hooks": [
                {"text": "The site says 200k+ visits in week one, but outside sources are thin", "type": "data", "fact_ids": ["F3"]},
                {"text": "9 million people use this every day without noticing", "type": "story", "fact_ids": ["F3"]},
                {"text": "Is this the future of motion design?", "type": "gap", "fact_ids": ["F1"]}],
                "distinct_angle": {"text": "Free to browse, but rendering needs a paid model", "fact_ids": ["F2"]}}
        return {}
    def search(self, prompt):
        return {"text": "Some note about the tool", "sources": [{"url": "https://news.ycombinator.com/item?id=1", "title": "HN"}]}

def fake_fetch(url, caption="", on_screen=""):
    return {"ok": True, "kind": "web", "url": "https://prompt-motion.com/", "title": "PM", "thin": False,
            "login_wall": False, "meta": {}, "pages": [{"url": "https://prompt-motion.com/", "text": PAGE}], "text": PAGE}

def test_pipeline_rejects_bad_material(monkeypatch):
    monkeypatch.setattr(F, "fetch", fake_fetch)
    steps = []
    r = A.analyze("https://prompt-motion.com/", FakeLLM(), today=date(2026, 10, 28), progress=steps.append)
    assert r["state"] == "ok"
    assert len(steps) >= 6
    assert len(r["dropped_facts"]) == 1                       # invented "five million studios" quote
    assert not any("million" in f["text"] for f in r["facts"])
    assert r["research"]["rejected"]                          # finding on a URL the search tool never returned
    assert any(isinstance(x, dict) and "reason" in x for x in r["research"]["rejected"])
    assert r["research"]["lookalikes"] == ["promptmotion.com"]
    texts = [h["text"] for h in r["report"]["hooks"]]
    assert texts == ["The site says 200k+ visits in week one, but outside sources are thin"]
    assert len(r["report"]["hooks_rejected"]) == 2            # invented number + question
    assert r["claims"][1]["verdict"] == "UNVERIFIABLE"        # popularity claim with no independent source
    assert r["scores"]["create"] == 3 and r["scores"]["n_independent"] == 0
    assert "needs a paid service" in r["scores"]["create_reasons"]
    assert r["verdict"] == "COVER THE GAP"                    # free claim + paid dependency

def test_thin_page_and_error(monkeypatch):
    monkeypatch.setattr(F, "fetch", lambda *a, **k: {**fake_fetch(""), "thin": True})
    assert A.analyze("https://x.com", FakeLLM())["state"] == "thin"
    monkeypatch.setattr(F, "fetch", lambda *a, **k: {"ok": False, "error": "HTTP 404", "kind": "web", "url": "u"})
    r = A.analyze("https://x.com/dead", FakeLLM())
    assert r["state"] == "error" and "404" in r["message"]

def test_platforms_tracked(monkeypatch):
    monkeypatch.setattr(F, "fetch", fake_fetch)
    r = A.analyze("https://prompt-motion.com/", FakeLLM(), today=date(2026, 10, 28))
    assert "platforms" in r["research"]
