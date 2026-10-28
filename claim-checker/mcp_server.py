"""MCP Server — exposes the AI Hype Claim Checker pipeline as a tool for Claude Desktop.

Install: pip install mcp
Run:     python mcp_server.py

Claude Desktop config (~/.claude/claude_desktop_config.json):
{
  "mcpServers": {
    "hype-checker": {
      "command": "python",
      "args": ["/path/to/mcp_server.py"],
      "env": {"OPENAI_API_KEY": "sk-..."}
    }
  }
}
"""
import os
import sys
from datetime import date

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(__file__))
import analyzer
import checks as C

mcp = FastMCP("AI Hype Claim Checker",
              instructions="Fact-checks AI tool claims using code-verified evidence.")


@mcp.tool()
def analyze_hype_claim(
    url: str,
    budget: str = "Free only",
    experience: str = "Non-technical",
) -> str:
    """Analyze an AI tool URL for hype vs reality.

    Fetches the page, extracts facts, verifies quotes against source text,
    searches Reddit/HN/X/YouTube for independent evidence, cross-verifies
    findings, and returns a scored, evidence-linked report.

    Args:
        url: The tool's URL (website or GitHub repo)
        budget: User's budget — "Free only", "Under $20/mo", "Under $50/mo", or "Flexible"
        experience: User's technical level — "Non-technical", "Some coding", or "Developer"
    """
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return "Error: OPENAI_API_KEY not set in environment."

    user_context = {"budget": budget, "experience": experience, "use_case": "Instagram Reels"}

    try:
        llm = analyzer.OpenAILLM(key)
        r = analyzer.analyze(url, llm, today=date.today(), user_context=user_context)
    except Exception as e:
        return f"Error: {C.redact_secrets(str(e))}"

    if r["state"] != "ok":
        return f"Could not analyze: {r.get('message', r['state'])}"

    rpt = r["report"]
    sc = r["scores"]
    lines = [
        f"# {r['name']}",
        f"{r['what_it_is']}",
        "",
        rpt.get("summary", ""),
        "",
        f"**Verdict:** {r['verdict']} — {r['verdict_rule']}",
        "",
        "Scores (rule-based, not LLM opinion):",
        f"- Browse: {sc['browse']}/5 (starts at 5; {'; '.join(sc.get('browse_reasons', [])) or 'no deductions'})",
        f"- Create: {sc['create']}/5 (starts at 5; {'; '.join(sc.get('create_reasons', [])) or 'no deductions'})",
        f"- Crowded: {sc['crowded']} ({sc.get('crowded_reason', '')})",
        f"- Independent sources: {sc['n_independent']} "
        f"({sc.get('n_confirmed_independent', 0)} verified, "
        f"{sc['n_independent'] - sc.get('n_confirmed_independent', 0)} unverified)",
        f"- Paid dependency: {'Yes' if sc.get('paid_dependency') else 'No'}",
        "",
    ]

    tryability = rpt.get("tryability") or {}
    if tryability:
        lines.append("## Tryability")
        for k in ("the_site", "the_tool", "time_to_result"):
            if tryability.get(k):
                lines.append(f"- {k}: {tryability[k]}")
        lines.append("")

    if rpt.get("quick_start"):
        lines.append("## Quick start")
        for i, step in enumerate(rpt["quick_start"], 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    hooks = rpt.get("hooks") or []
    if hooks:
        lines.append("## Content hooks")
        for h in hooks:
            tag = h.get("type", "hook")
            prin = f" ({h.get('principle', '')})" if h.get("principle") else ""
            lines.append(f"- **[{tag}]** {h['text']}{prin}")
            if h.get("why_it_works"):
                lines.append(f"  Why: {h['why_it_works']}")
            if h.get("unverified_numbers"):
                nums_str = ", ".join(f'"{n}"' for n in h["unverified_numbers"])
                lines.append(f"  [!] {nums_str} not verified — illustrative number for virality")
        lines.append("")

    if rpt.get("bottom_line"):
        lines.append(f"**Bottom line:** {rpt['bottom_line']}")
        lines.append("")

    lines.append("## Verified facts")
    for f in r["facts"]:
        lines.append(f"- [{f['status']}] {f['text']}")

    if r.get("research", {}).get("alternatives"):
        lines.append(f"\n**Alternatives:** {', '.join(r['research']['alternatives'])}")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
