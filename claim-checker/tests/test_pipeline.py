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
            return {"summary": "A gallery of motion prompts. You need Claude Opus 5.5 to render them.",
                    "quick_start": ["Open site", "Copy a prompt", "Get Claude Pro plan", "Paste and render"],
                    "bottom_line": "Yes, make this reel. The visual transformation is strong content.",
                    "virality_notes": "Decent",
                    "uniqueness": "Nothing notable",
                    "tryability": {"the_site": "Free to browse, no signup", "the_tool": "Needs Claude Opus 5.5 (paid)", "time_to_result": "Under 5 min with Claude"},
                    "setup_steps": [{"step": "Browse gallery and pick a prompt", "time": "1"},
                                    {"step": "Get Claude Pro plan", "time": "5"},
                                    {"step": "Paste prompt and render", "time": "5"}],
                    "claims_table": [{"claim": "Free to customize prompts", "status": "confirmed", "detail": "Verified on site"},
                                     {"claim": "200k visits in week one", "status": "cannot_confirm", "detail": "Self-reported from sponsor page"}],
                    "how_people_use_it": "Creators use prompts for motion backgrounds in reels and shorts.",
                    "virality_scorecard": [{"dimension": "Trend fit", "score": 8, "max": 10, "reason": "AI motion is trending"},
                                           {"dimension": "Uniqueness", "score": 5, "max": 10, "reason": "Prompt galleries exist"},
                                           {"dimension": "Tryability", "score": 7, "max": 10, "reason": "Free to browse, paid to render"},
                                           {"dimension": "Shareability", "score": 7, "max": 10, "reason": "Visual output is shareable"},
                                           {"dimension": "Overall", "score": 7, "max": 10, "reason": "Strong if you show the render"}],
                    "why_viral": "One line of text becomes a full motion graphic.",
                    "why_not_viral": "Render step is behind a paywall.",
                    "risk_warnings": ["Traffic numbers are self-reported"],
                    "sources": ["https://prompt-motion.com/"]}
        if "scroll-stopping" in user:
            return {"hooks": [
                {"text": "I copied one prompt from this free site and had a motion graphic ready for my reel", "type": "story", "fact_ids": ["F1"]},
                {"text": "9 million people use this every day without noticing", "type": "gap", "fact_ids": ["F3"]},
                {"text": "Is this the future of motion design?", "type": "challenge", "fact_ids": ["F1"]}],
                "reel_structure": {"hook_0_2s": "Result playing full screen", "demo_2_8s": "Copy prompt, paste into Claude", "reveal_8_15s": "Side by side prompt vs output", "cta_15_20s": "The catch + CTA"},
                "distinct_angle": {"text": "Free to browse, but rendering needs a paid model", "fact_ids": ["F2"]}}
        return {}
    def search(self, prompt):
        if "pricing" in prompt.lower():
            return {"text": "Claude Pro costs $20/month. API access via Anthropic starts at $3 per million input tokens.",
                    "sources": [{"url": "https://anthropic.com/pricing", "title": "Pricing"}]}
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
    assert not any("5 million" in f["text"] for f in r["facts"])
    assert r["research"]["rejected"]                          # finding on a URL the search tool never returned
    assert any(isinstance(x, dict) and "reason" in x for x in r["research"]["rejected"])
    assert r["research"]["lookalikes"] == ["promptmotion.com"]
    texts = [h["text"] for h in r["report"]["hooks"]]
    assert texts == ["I copied one prompt from this free site and had a motion graphic ready for my reel"]
    assert len(r["report"]["hooks_rejected"]) == 2            # invented number + question
    assert r["claims"][1]["verdict"] == "UNVERIFIABLE"        # popularity claim with no independent source
    assert r["scores"]["create"] == 3
    assert "needs a paid service" in r["scores"]["create_reasons"]
    assert r["scores"]["n_independent"] >= 0                     # pricing investigation may add independent sources
    assert r["verdict"] == "COVER THE GAP"                    # free claim + paid dependency

def test_new_report_fields(monkeypatch):
    monkeypatch.setattr(F, "fetch", fake_fetch)
    r = A.analyze("https://prompt-motion.com/", FakeLLM(), today=date(2026, 10, 28))
    rpt = r["report"]
    assert rpt["tryability"]["the_site"]
    assert rpt["tryability"]["the_tool"]
    assert len(rpt["setup_steps"]) >= 2
    assert all("step" in s and "time" in s for s in rpt["setup_steps"])
    assert len(rpt["claims_table"]) >= 1
    assert rpt["how_people_use_it"]
    assert len(rpt["virality_scorecard"]) == 5
    assert all(item["dimension"] and item["score"] for item in rpt["virality_scorecard"])
    assert rpt["why_viral"]
    assert rpt["why_not_viral"]
    assert rpt["reel_structure"]["hook_0_2s"]
    assert isinstance(rpt["risk_warnings"], list)
    assert isinstance(rpt["sources_list"], list)

def test_access_inference(monkeypatch):
    monkeypatch.setattr(F, "fetch", fake_fetch)
    facts = {
        "F1": {"id": "F1", "text": "Uses Claude Opus 5.5 to render", "quote": "q", "url": "u",
               "category": "capability", "status": "SITE_SAYS", "origin": "official", "date": None},
        "F2": {"id": "F2", "text": "Free to browse gallery", "quote": "q", "url": "u",
               "category": "access", "status": "SITE_SAYS", "origin": "official", "date": None},
    }
    acc = {"free_to_browse": None, "needs_account": None, "paid_dependency": None,
           "needs_code": None, "setup_minutes": None, "claims_free": None}
    result = A._infer_access(acc, facts)
    assert result["paid_dependency"] is True
    assert result["free_to_browse"] is True
    assert result["setup_minutes"] is not None

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

def test_investigate_stage_pricing(monkeypatch):
    monkeypatch.setattr(F, "fetch", fake_fetch)
    r = A.analyze("https://prompt-motion.com/", FakeLLM(), today=date(2026, 10, 28))
    assert "investigation" in r
    inv = r["investigation"]["investigated"]
    assert any("pricing" in i for i in inv)
    pricing_facts = [f for f in r["facts"] if f["category"] == "pricing"]
    assert len(pricing_facts) >= 1

def test_investigate_skips_when_no_paid_dep(monkeypatch):
    """If no paid dependency, no pricing investigation should run."""
    facts = {"F1": {"id": "F1", "text": "A free tool", "quote": "q", "url": "u",
                    "category": "capability", "status": "SITE_SAYS", "origin": "official", "date": None}}
    access = {"paid_dependency": False, "free_to_browse": True}
    doc = {"kind": "web", "meta": {}, "url": "https://example.com"}
    result = A.stage_investigate(FakeLLM(), facts, access, doc, date(2026, 10, 28))
    assert result["investigated"] == []

def test_dep_parsing():
    """Test dependency file parsing directly (code, no LLM)."""
    reqs = F._parse_requirements("flask>=2.0\nrequests\n# comment\nopenai>=1.0")
    assert "flask" in reqs
    assert "requests" in reqs
    assert "openai" in reqs
    assert len(reqs) == 3

    pkg = F._parse_package_json('{"dependencies":{"react":"^18","openai":"^4"},"devDependencies":{"jest":"^29"}}')
    assert "react" in pkg
    assert "openai" in pkg
    assert "jest" in pkg

    pyproj = F._parse_pyproject('[project]\ndependencies = [\n  "anthropic>=0.5",\n  "click",\n]\n')
    assert "anthropic" in pyproj
    assert "click" in pyproj

def test_check_paid_deps():
    assert A._check_paid_deps(["openai", "flask", "requests"]) == ["OpenAI API"]
    assert A._check_paid_deps(["anthropic", "click"]) == ["Anthropic API"]
    assert A._check_paid_deps(["flask", "requests"]) == []

def test_user_context_passed(monkeypatch):
    monkeypatch.setattr(F, "fetch", fake_fetch)
    ctx = {"budget": "Free only", "experience": "Non-technical", "use_case": "Instagram Reels"}
    r = A.analyze("https://prompt-motion.com/", FakeLLM(), today=date(2026, 10, 28), user_context=ctx)
    assert r["state"] == "ok"

def test_cross_verify_upgrades_corroborated():
    """UNCHECKED independent fact matching a SITE_SAYS fact gets upgraded to CORROBORATED."""
    facts = {
        "F1": {"id": "F1", "text": "Requires Muapi.ai API key for credits",
               "status": "SITE_SAYS", "origin": "official"},
        "F2": {"id": "F2", "text": "Users report needing paid credits from Muapi API",
               "status": "UNCHECKED", "origin": "independent"},
        "F3": {"id": "F3", "text": "Tutorial about cooking pasta at home",
               "status": "UNCHECKED", "origin": "independent"},
    }
    upgraded = A._cross_verify(facts)
    assert upgraded == 1
    assert facts["F2"]["status"] == "CORROBORATED"
    assert facts["F2"]["corroborated_by"] == "F1"
    assert facts["F3"]["status"] == "UNCHECKED"  # unrelated, stays UNCHECKED
