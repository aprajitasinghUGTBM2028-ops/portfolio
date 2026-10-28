# AI Usage Disclosure — Litmus: Test the Promise

## AI Tools Used in Building This Project

**Claude (Anthropic) — Claude Code** served as a development partner. Claude helped design the 9-step pipeline architecture, wrote initial drafts of all Python modules which I reviewed and iterated on, identified and fixed bugs (setup time parsing, claim extraction, security issues), and assisted with prompt engineering. Key design decisions — like having code compute verdicts instead of the model — emerged from collaborative debugging sessions. Claude also built the MCP server integration and helped write documentation.

**OpenAI GPT-4o (Paid API)** is the LLM backbone inside the tool itself. It classifies tools, plans search queries, extracts structured facts with quotes, writes evidence-linked reports, self-critiques, and generates content hooks. It uses both the Chat Completions API (JSON mode) and the Responses API (web_search tool). Critically, GPT-4o does not decide verdicts — it returns evidence IDs, and code derives the final judgment.

**Streamlit** hosts the web app at ideahypeanalyser.streamlit.app.

## How I Verified AI-Generated Code

1. **Read every function** Claude generated and understood the flow before running it. Made changes where logic didn't match my intent.
2. **Tested with real URLs** — tested against tools like Prompt Motion, gstack, and Knowledge Work Plugins. Compared output against manual research.
3. **Cross-checked verdicts** — verified GPT-4o's claim judgments against what I could confirm manually (e.g., checking if a "free" tool actually requires paid API keys).
4. **Iterative improvement** — multiple rounds of testing, feedback, and rewriting. The 9-step pipeline replaced an earlier single-pass approach that was unreliable.
5. **Found and fixed bugs** — caught the setup time parsing bug (showing 526 min instead of 18 min) and the overly generic claim extraction, then worked with Claude to fix both.

## What I Understand and Can Explain

- The full 9-step pipeline and why each step exists
- Why code computes verdicts instead of the model (prevents self-confirmation bias)
- How domain-based independence checking works for source verification
- The Instagram edge case flow (URL detection, caption paste, pending_reel state)
- The multi-tool caption limitation and why deep per-feature verification is hard
- How the MCP server exposes the same pipeline to Claude Desktop
- All security measures: SSRF blocking, XSS escaping, key isolation, prompt injection fencing
