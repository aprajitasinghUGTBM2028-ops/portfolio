"""Live checklist: runs the real pipeline N times per URL with YOUR key and reports pass rate.
Costs a little OpenAI credit.   OPENAI_API_KEY=sk-... python live_check.py [runs]"""
import os, sys
from analyzer import OpenAILLM, analyze
import checks as C

CASES = {
    "prompt-motion": "https://prompt-motion.com/",
    "gstack": "https://github.com/garrytan/gstack",
    "dead-link": "https://prompt-motion.com/this-page-does-not-exist-xyz",
}

def checklist(r, name):
    if name == "dead-link":
        return {"graceful error, no report": r["state"] in ("error", "thin")}
    if r["state"] != "ok":
        return {"report produced": False}
    solid = [f for f in r["facts"] if f["status"] == "INDEPENDENT"]
    ids = {f["id"] for f in r["facts"]}
    return {
        "scores within range": (1 <= r["scores"]["browse"] <= 5 and 1 <= r["scores"]["create"] <= 5
                                and r["scores"]["crowded"] in ("low", "medium", "high", "unknown")),
        "every independent fact has a URL on a different owner": all(f["url"] for f in solid),
        "every claim cites existing facts": all(set(c["evidence_ids"]) <= ids for c in r["claims"]),
        "no hook has an unattributed or invented number": all(h["ok"] for h in r["report"]["hooks"]),
        "no hook is a question": not any(h["text"].endswith("?") for h in r["report"]["hooks"]),
        "verdict is one of the allowed values": r["verdict"] in ("COVER IT", "COVER THE GAP", "SKIP", "INSUFFICIENT EVIDENCE"),
        "paid dependency is surfaced in quick start when present": (not r["access"].get("paid_dependency")) or any("paid" in s.lower() or "subscription" in s.lower() or "api" in s.lower() for s in r["report"]["quick_start"]),
    }

if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    llm = OpenAILLM(os.environ["OPENAI_API_KEY"])
    for name, url in CASES.items():
        tally, verdicts = {}, []
        for _ in range(runs):
            try:
                r = analyze(url, llm)
            except Exception as e:
                print(name, "crashed:", C.redact_secrets(e)); continue
            verdicts.append(r.get("verdict", r["state"]))
            for k, v in checklist(r, name).items():
                tally[k] = tally.get(k, 0) + bool(v)
        print(f"\n== {name}  verdicts across {runs} runs: {verdicts}")
        for k, v in tally.items():
            print(f"  {v}/{runs}  {k}")
