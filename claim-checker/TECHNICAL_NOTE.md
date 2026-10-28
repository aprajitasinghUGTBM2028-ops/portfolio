# Technical Note — Litmus: Test the Promise

## The Problem

Every week, Instagram creators discover dozens of new AI tools through reels. Each comes with bold claims — "completely free," "no code needed," "replaces your entire workflow." Manually verifying these takes 30-60 minutes per tool: checking the site, searching Reddit, reading GitHub, comparing alternatives. Most creators skip this and repeat the marketing pitch. Their audiences deserve better.

## What Litmus Does

Litmus takes a tool's URL (or an Instagram caption) and runs a 9-step verification pipeline. It fetches the tool's page, extracts specific claims, searches Reddit, Hacker News, YouTube, and LinkedIn for independent evidence, then produces a scored report with a verdict. The entire analysis takes about 60 seconds.

The output includes: a tryability assessment (can you actually use it today?), setup steps with time estimates, a claims table showing what's confirmed vs unconfirmed, content hooks for reels, and a clear verdict (Cover It / Skip It / Cover the Gap).

## How AI Is Used — And Where It Isn't

The pipeline uses GPT-4o for extraction (pulling claims from pages), search (finding independent sources), and writing (the report). But the critical decisions are made by code, not the model:

- **Verdicts are code-computed.** The model returns evidence IDs. Code checks whether each source's domain matches the tool's domain. Only sources from different domains count as independent. This prevents the model from marking its own guesses as "confirmed."
- **Quotes are verified against page text.** Every fact must include a quote that actually appears on the source page. If the quote isn't found, the fact is rejected.
- **Scores use rules, not opinions.** Browse and Create scores start at 5/5 and deduct points based on access flags (needs account, needs payment, needs code, large download). The model doesn't pick the numbers.

## How It Can Be Used

1. **Streamlit web app** — Anyone can visit the link and paste a URL. No install needed.
2. **MCP server for Claude Desktop** — The same pipeline runs as a tool inside Claude, so you can fact-check a tool mid-conversation.

## Known Limitations

- **Instagram reels can't be auto-fetched** — the app detects Instagram URLs and asks the user to paste the caption manually.
- **Multi-tool captions** — when a caption lists many tools, the app can identify them but can't deeply verify each one's specific feature claims in a single pass.
- **Multi-feature verification depth** — if a tool claims 11 different capabilities, the pipeline verifies the tool exists and is open source, but may not confirm each individual feature.
- **Run-to-run variance** — web search results differ between runs, so scores can shift slightly.
- **Login-walled pages** — can't analyze content behind authentication.

## What I'd Add With More Time

- Browser automation to actually try signing up and test the tool
- Persistent history so users can compare analyses over time
- Deeper sub-page crawling to verify individual feature claims
