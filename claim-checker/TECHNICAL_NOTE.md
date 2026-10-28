# Technical Note — Litmus: Test the Promise

## The Problem

During my initial screening, I described my content workflow: I use AI agents to surface trending tools, pick the most promising ones, then manually research each — checking the site, reading Reddit threads, comparing alternatives — before deciding whether to cover it. That manual verification takes 30-60 minutes per tool and is the bottleneck. Litmus automates it.

## What Litmus Does

Paste a tool's URL (or an Instagram reel caption) and get a scored, evidence-linked report in about 60 seconds. It tells you: Can you actually use this tool today? How long does setup take? What claims are confirmed by independent sources vs unverified? Should you cover it, skip it, or cover the gap?

## Architecture — The 9-Step Pipeline

1. **Fetch** — Scrapes the tool's website, extracts text, follows key sub-pages
2. **Classify & Plan** — GPT-4o identifies the tool type and generates targeted search queries
3. **Search** — GPT-4o's web_search tool checks Reddit, Hacker News, YouTube, LinkedIn for independent mentions
4. **Extract** — Pulls structured facts with exact quotes and source URLs from every page
5. **Validate** — Code (not the model) verifies: Does the quote actually appear on that page? Is the source domain different from the tool's own domain? Only independent, quote-verified facts survive.
6. **Gaps** — Identifies what's still unconfirmed and runs a second targeted search
7. **Report** — GPT-4o writes a scored report, but scores are rule-based: Browse and Create start at 5/5, deducting for paywalls, logins, code requirements. The model doesn't pick the numbers.
8. **Critique** — A separate GPT-4o call reviews the report against raw evidence, flags anything unsupported
9. **Hooks** — Generates reel-ready content angles from verified evidence

**Key design decision:** The model never decides verdicts. It returns evidence IDs. Code checks domain independence and quote presence. This prevents the model from confirming its own guesses.

## How It Can Be Used

1. **Streamlit web app** — Anyone can visit the link and paste a URL. No install needed.
2. **MCP server for Claude Desktop** — The same pipeline runs as a tool inside Claude, so you can fact-check a tool mid-conversation.

## Known Limitations

- **Multi-tool captions** — When a reel caption lists multiple tools, the pipeline can't deeply verify each one in a single pass.
- **Instagram reels can't be auto-fetched** — The app detects Instagram URLs and asks the user to paste the caption manually.
- **Multi-feature verification depth** — If a tool claims 11 capabilities, the pipeline confirms the tool exists but may not verify each individual feature claim.

## If I Had One More Day

I'd focus on personalization. Right now, within the time constraint, Litmus gives a standard shareable output. With more time, I'd connect Instagram via MCP to fetch reels frame-by-frame or through transcripts, then feed that structured data through the Litmus MCP so Claude has full context. The output would speak my voice instead of being generic — it would actually understand how I evaluate tools, what I prioritize, and how I frame things for my audience.
