"""
Consistency test — runs several URLs through the pipeline and checks
that the output structure is valid and scores are in range.

Usage:
    export OPENAI_API_KEY='sk-...'
    cd claim-checker
    python -m tests.test_consistency

Runs each test URL once and prints a pass/fail summary.
For full consistency testing, run the same URL multiple times and compare.
"""

import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetcher import fetch
from analyzer import analyze

TEST_CASES = [
    {
        "name": "Web page (Prompt Motion)",
        "url": "https://promptmotion.co",
        "type": "web",
    },
    {
        "name": "GitHub repo (gstack)",
        "url": "https://github.com/user/gstack",
        "type": "github",
        "may_fail_fetch": True,
    },
    {
        "name": "Dead URL",
        "url": "https://this-domain-does-not-exist-12345.com",
        "expect_fetch_fail": True,
    },
    {
        "name": "Instagram (caption only)",
        "url": "https://instagram.com/reel/test",
        "provide_caption": "This AI tool is incredible! ToolName generates videos from text in 10 seconds, completely free.",
        "type": "instagram",
    },
]


def validate_result(result: dict, test_name: str) -> list:
    """Check that the result has valid structure and scores."""
    errors = []

    if result.get("error"):
        return [f"Analysis returned error: {result.get('error')}"]

    # Check score ranges
    hype = result.get("hype_score")
    if hype is not None:
        if not (1 <= int(hype) <= 10):
            errors.append(f"hype_score {hype} out of range 1-10")

    t = result.get("tryability", {})
    if isinstance(t, dict) and "score" in t:
        score = t["score"]
        if not (1 <= int(score) <= 5):
            errors.append(f"tryability.score {score} out of range 1-5")

    v = result.get("virality", {})
    if isinstance(v, dict):
        for k in ("visual_wow", "shareability", "trend_fit", "uniqueness", "virality_score"):
            val = v.get(k)
            if val is not None:
                if not (1 <= int(val) <= 10):
                    errors.append(f"virality.{k} = {val} out of range 1-10")

    # Check evidence statuses
    valid_statuses = {"SITE_SAYS", "INDEPENDENT", "UNVERIFIABLE", "CONTRADICTED"}
    for ev in result.get("evidence_list", []):
        if isinstance(ev, dict):
            status = ev.get("status", "")
            if status not in valid_statuses:
                errors.append(f"Invalid evidence status: {status}")

    # Check verdicts
    for vc in result.get("verified_claims", []):
        if isinstance(vc, dict):
            verdict = vc.get("verdict", "")
            if verdict and verdict not in valid_statuses:
                errors.append(f"Invalid verdict: {verdict}")

    # Check for no-independent warning
    stats = result.get("_evidence_stats", {})
    if stats.get("total", 0) > 0 and stats.get("independent", 0) == 0:
        errors.append("WARNING: No independent sources found (all evidence from tool's site)")

    return errors


def run_test(test: dict, api_key: str) -> tuple:
    """Run one test case. Returns (passed: bool, message: str)."""
    name = test["name"]
    url = test["url"]

    try:
        content = fetch(url)

        if test.get("expect_fetch_fail"):
            if not content.get("ok"):
                return True, f"Correctly failed to fetch: {content.get('error', '?')}"
            return False, "Expected fetch to fail but it succeeded"

        if content.get("needs_manual_input") and test.get("provide_caption"):
            content = {
                "ok": True,
                "source_type": "instagram",
                "url": url,
                "caption": test["provide_caption"],
                "text": test["provide_caption"],
            }

        if not content.get("ok"):
            if test.get("may_fail_fetch"):
                return True, f"Fetch failed (expected possible): {content.get('error', '?')}"
            return False, f"Fetch failed: {content.get('error', '?')}"

        result = analyze(content, api_key=api_key)

        if result.get("error"):
            return False, f"Analysis error: {result.get('error')} — {result.get('message', '')}"

        errors = validate_result(result, name)
        warnings = [e for e in errors if e.startswith("WARNING:")]
        real_errors = [e for e in errors if not e.startswith("WARNING:")]

        msg = "PASS"
        if warnings:
            msg += f" ({len(warnings)} warnings: {'; '.join(warnings)})"
        if real_errors:
            return False, f"Validation errors: {'; '.join(real_errors)}"

        # Print summary stats
        stats = result.get("_evidence_stats", {})
        msg += f" — evidence: {stats.get('total', '?')} total, {stats.get('independent', '?')} independent"
        msg += f" — hype: {result.get('hype_score', '?')}/10"

        return True, msg

    except Exception as e:
        return False, f"Exception: {type(e).__name__}: {e}\n{traceback.format_exc()}"


def main():
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Set OPENAI_API_KEY environment variable to run tests.")
        sys.exit(1)

    passed = 0
    failed = 0
    total = len(TEST_CASES)

    for test in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"TEST: {test['name']}")
        print(f"URL:  {test['url']}")
        print(f"{'='*60}")

        ok, msg = run_test(test, api_key)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {msg}")

        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'='*60}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
