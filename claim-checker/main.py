#!/usr/bin/env python3
"""
AI Hype Claim Checker
=====================
Paste an AI tool's URL (landing page, GitHub repo) or an Instagram caption,
and get a breakdown of what's real, what's hype, and whether it's worth
covering on a content page.

Built for the @aistuff.muu research workflow.
"""

import sys
import json
import argparse
from fetcher import fetch
from analyzer import analyze


# ── Pretty Printing ──────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"


def verdict_color(verdict: str) -> str:
    v = verdict.lower()
    if v == "confirmed":
        return GREEN
    elif v == "partially_true":
        return YELLOW
    elif v == "exaggerated":
        return RED
    return WHITE


def content_verdict_style(verdict: str) -> str:
    v = verdict.upper()
    if "COVER IT" in v:
        return GREEN + BOLD
    elif "COVER THE GAP" in v:
        return YELLOW + BOLD
    elif "SKIP" in v:
        return RED + BOLD
    return WHITE + BOLD


def print_header():
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════╗
║           AI HYPE CLAIM CHECKER                  ║
║     What's real? What's hype? Should you cover it?║
╚══════════════════════════════════════════════════╝{RESET}
""")


def print_fetch_result(content: dict):
    if not content["ok"]:
        print(f"\n{RED}{BOLD}✗ FETCH FAILED{RESET}")
        print(f"  {content['error']}")
        return False

    src = content["source_type"]
    if src == "github":
        meta = content.get("meta", {})
        print(f"\n{GREEN}✓ Fetched GitHub repo:{RESET} {content['owner']}/{content['repo']}")
        print(f"  {DIM}⭐ {meta.get('stars', '?')} stars | {meta.get('language', '?')} | Last push: {meta.get('last_push', '?')[:10]}{RESET}")
    elif src == "web":
        print(f"\n{GREEN}✓ Fetched page:{RESET} {content.get('title', content['url'])}")
        if content.get("final_url") != content.get("url"):
            print(f"  {DIM}↳ Redirected to: {content['final_url']}{RESET}")
    elif src == "instagram":
        print(f"\n{YELLOW}⚠ Instagram detected{RESET} — caption needed manually")
    return True


def print_claims(claims_data: dict):
    print(f"\n{BOLD}{'─' * 50}{RESET}")
    print(f"{BOLD}{MAGENTA}🔍 TOOL: {claims_data.get('tool_name', 'Unknown')}{RESET}")
    print(f"   {claims_data.get('tool_summary', '')}")
    print(f"\n{BOLD}📋 EXTRACTED CLAIMS:{RESET}")

    for i, claim in enumerate(claims_data.get("claims", []), 1):
        cat = claim.get("category", "").replace("_", " ").title()
        print(f"\n  {BOLD}{i}. [{cat}]{RESET} {claim['claim']}")
        if claim.get("quote"):
            print(f"     {DIM}\"{claim['quote']}\"{RESET}")


def print_verification(result: dict):
    print(f"\n{BOLD}{'─' * 50}{RESET}")
    print(f"{BOLD}🔬 CLAIM VERIFICATION:{RESET}")

    for i, vc in enumerate(result.get("verified_claims", []), 1):
        color = verdict_color(vc["verdict"])
        verdict_label = vc["verdict"].upper().replace("_", " ")
        print(f"\n  {BOLD}{i}. {vc['claim']}{RESET}")
        print(f"     {color}→ {verdict_label}{RESET}")
        print(f"     {vc.get('evidence', '')}")
        flags = vc.get("red_flags", [])
        if flags:
            print(f"     {RED}🚩 {', '.join(flags)}{RESET}")


def print_tryability(result: dict):
    tryability = result.get("tryability", {})
    score = tryability.get("score", "?")
    score_bar = "█" * int(score) + "░" * (5 - int(score)) if isinstance(score, int) else "?????"

    print(f"\n{BOLD}{'─' * 50}{RESET}")
    print(f"{BOLD}🧪 TRYABILITY: [{score_bar}] {score}/5{RESET}")
    print(f"   Free tier:      {tryability.get('free_tier', '?')}")
    print(f"   Setup time:     {tryability.get('setup_time', '?')}")
    print(f"   Visible result: {tryability.get('visible_result', '?')}")

    blockers = tryability.get("blockers", [])
    if blockers:
        print(f"   {RED}Blockers: {', '.join(blockers)}{RESET}")
    else:
        print(f"   {GREEN}No blockers!{RESET}")


def print_verdict(result: dict):
    cv = result.get("content_verdict", {})
    verdict = cv.get("verdict", "UNKNOWN")
    style = content_verdict_style(verdict)

    hype_score = result.get("hype_score", "?")
    hype_bar = "🔥" * int(hype_score) if isinstance(hype_score, int) else "?"

    print(f"\n{BOLD}{'═' * 50}{RESET}")
    print(f"\n{style}📣 CONTENT VERDICT: {verdict}{RESET}")
    print(f"   Hype Score: {hype_bar} ({hype_score}/10)")
    print(f"\n   {BOLD}Why:{RESET} {cv.get('reason', '')}")
    if cv.get("angle"):
        print(f"\n   {CYAN}{BOLD}💡 Content Angle:{RESET} {cv['angle']}")

    print(f"\n{BOLD}{'═' * 50}{RESET}")
    summary = result.get("summary", "")
    if summary:
        print(f"\n{DIM}{summary}{RESET}")


def print_error_result(result: dict):
    err = result.get("error", "")
    if err == "not_ai_tool":
        print(f"\n{YELLOW}{BOLD}⚠ NOT AN AI TOOL{RESET}")
        print(f"  {result['message']}")
    elif err == "no_claims":
        print(f"\n{YELLOW}{BOLD}⚠ NO CLAIMS FOUND{RESET}")
        print(f"  {result['message']}")
    else:
        print(f"\n{RED}{BOLD}✗ ANALYSIS ERROR{RESET}")
        print(f"  {result.get('message', result.get('error', 'Unknown error'))}")


# ── Main Flow ────────────────────────────────────────────────────────

def run_check(input_text: str, caption: str = None, output_json: bool = False):
    """Run the full claim-checking pipeline."""

    print_header()

    # Step 1: Fetch
    print(f"{BOLD}Step 1/3:{RESET} Fetching content...")
    content = fetch(input_text)

    # Handle Instagram manual caption
    if content.get("needs_manual_input"):
        if caption:
            content = {
                "ok": True,
                "source_type": "instagram",
                "url": input_text,
                "caption": caption,
                "text": caption,
            }
        else:
            print(f"\n{YELLOW}Instagram reel detected.{RESET}")
            print("Paste the reel's caption below (press Enter twice when done):\n")
            lines = []
            while True:
                line = input()
                if line == "":
                    if lines and lines[-1] == "":
                        break
                    lines.append(line)
                else:
                    lines.append(line)
            caption_text = "\n".join(lines).strip()
            if not caption_text:
                print(f"{RED}No caption provided. Exiting.{RESET}")
                return None
            content = {
                "ok": True,
                "source_type": "instagram",
                "url": input_text,
                "caption": caption_text,
                "text": caption_text,
            }

    if not print_fetch_result(content):
        return content

    # Step 2: Extract & Verify
    print(f"\n{BOLD}Step 2/3:{RESET} Extracting claims...")
    print(f"{BOLD}Step 3/3:{RESET} Verifying & scoring...\n")

    result = analyze(content)

    # Check for errors
    if result.get("error"):
        print_error_result(result)
        if output_json:
            print(f"\n{DIM}JSON output:{RESET}")
            print(json.dumps(result, indent=2))
        return result

    # Print results
    print_claims(result.get("claims_data", {}))
    print_verification(result)
    print_tryability(result)
    print_verdict(result)

    if output_json:
        print(f"\n{DIM}Full JSON output saved.{RESET}")
        with open("last_result.json", "w") as f:
            json.dump(result, f, indent=2)
        print(f"{DIM}→ last_result.json{RESET}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="AI Hype Claim Checker — Verify AI tool claims and get content verdicts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py https://github.com/owner/cool-ai-tool
  python main.py https://some-ai-tool.com
  python main.py https://instagram.com/reel/xyz --caption "This AI tool is insane..."
  python main.py https://github.com/owner/repo --json
        """
    )
    parser.add_argument("url", help="URL of the AI tool (GitHub repo, landing page, or Instagram reel)")
    parser.add_argument("--caption", "-c", help="Instagram caption (if URL is an Instagram reel)")
    parser.add_argument("--json", "-j", action="store_true", help="Also save full JSON output")

    args = parser.parse_args()
    run_check(args.url, caption=args.caption, output_json=args.json)


if __name__ == "__main__":
    main()
