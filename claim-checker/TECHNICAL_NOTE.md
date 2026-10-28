# Technical Note — Litmus: Test the Promise

## Problem

In my content workflow I use AI agents to surface trending tools, pick the most promising ones, and then research each by hand: check the site, read Reddit threads, compare alternatives, and only then decide whether to cover it. That verification takes 30-60 minutes per tool and is the bottleneck. The people who feel it are creators and researchers who evaluate many AI tools every week and need to separate real capabilities from marketing before putting a tool in front of an audience.

Litmus automates that step. Paste a tool's URL (or an Instagram reel caption) and get a scored, evidence-linked report in about 60 seconds: can you actually use it today, how long does setup take, which claims are confirmed by independent sources, and should you cover it, skip it, or cover the gap.

## Approach

A 9-step pipeline with code validation between the AI steps. It replaced an earlier single-pass approach that was unreliable.

1. **Fetch** (code) — Scrapes the tool's page, extracts text, follows key sub-pages (pricing, docs, blog).
2. **Classify & Plan** (AI) — Identifies the tool type, pulls claims with exact quotes, and plans search queries.
3. **Search** (AI + web search) — Looks for independent mentions on Reddit, Hacker News, YouTube and LinkedIn.
4. **Extract** (AI) — Produces structured facts with exact quotes and source URLs.
5. **Validate** (code) — Checks that each quote appears on its source page and that the source domain differs from the tool's own. Only quote-verified facts survive.
6. **Gaps** (AI) — Finds what is still unconfirmed and runs up to two more targeted searches.
7. **Report** (AI + code) — The model writes the report from validated fact IDs; scores are rule-based.
8. **Critique** (AI) — A separate call reviews the report against the raw evidence.
9. **Hooks** (AI + code) — Generates reel hooks; code checks that numbers come from facts and that self-reported numbers are attributed.

**Key design decisions:**

- The model never decides verdicts. It returns evidence IDs; code checks domain independence and quote presence and derives SITE_SAYS / INDEPENDENT / UNVERIFIABLE / CONTRADICTED. This stops the model from confirming its own guesses.
- Independence by domain. A source counts as independent only if its domain differs from the tool's. This replaced a whitelist that gave false matches (`"x.com" in "linux.com"`).
- Quote-level validation. No paraphrase is accepted as evidence.
- Rule-based scores. Browse and Create start at 5/5 and lose points for paywalls, logins, or code requirements.
- Per-feature claims. The prompt extracts each capability claim separately instead of summarizing them into one generic claim.
- Prompt-injection fencing. Page content is wrapped in `<data instructions="none">` tags and the closing sequence is escaped.

## Technical Implementation

- Python 3.9+ with the `openai` SDK.
- GPT-4o. Chat Completions (JSON mode) for classify, extract, report, critique and hooks; the Responses API with `web_search` for live evidence. One provider gives both structured output and live search, at roughly $0.05-0.15 per check.
- requests + BeautifulSoup4 for fetching, with SSRF protection, thin-content detection and sub-page priority sorting.
- Streamlit for a zero-install web app, with an optional password gate and a daily cap to protect the API budget.
- MCP server (`mcp_server.py`, FastMCP) so the same pipeline runs as a tool inside Claude Desktop.

## Testing

- **Offline test suite (31 tests).** The tests run the pipeline against a `FakeLLM` that returns deliberately bad output: quotes that are not on the page, findings from unrelated or look-alike domains, invented hook numbers, and injection text inside page content. They check that the code, not the model, rejects it. They also cover rule-based scores and verdict precedence, SSRF blocking, thin or error pages, and the Instagram caption requirement. They need no API key and cost nothing.
- **Real-URL runs.** Six runs are documented in the appendix PDF (VoiceStudio, Prompt Motion, Open Higgsfield AI, OpusJake, Knowledge Work Plugins via an Instagram caption, Cloudflare Skills). I compared the outputs against manual research. `live_check.py` reruns real URLs several times with a real key and reports a pass rate.
- **Edge cases.** Instagram URLs trigger a caption prompt (appendix, run 5). Dead links, non-AI pages and JS-rendered pages with almost no text return clear messages. A "free" tool that needs a paid API key is flagged as a contradiction (Open Higgsfield AI).

## What Failed and How I Handled It

- **Setup time parsing.** A "5-19 min" range was read as 519 minutes. Fixed; the Prompt Motion output in the appendix is the pre-fix run, kept for transparency.
- **Generic claims.** Early versions collapsed features into one vague claim. Fixed by extracting each claim separately.
- **Invented sources.** Early versions made up URLs. Evidence URLs are now checked against what was actually gathered, and unmatched ones are downgraded to UNVERIFIABLE.
- **Run-to-run variance and score inflation.** Web search results differ between runs, and the model drifts toward generous virality scores. Code clamps ranges and the critique step catches some of it, but not all.

## Limitations and Next Steps

Current limitations:

- Instagram reels can't be auto-fetched (auth wall). The app asks for the caption instead. In Claude, a connector may read reels from the connected account, but public reels from other accounts need a separate scraper or transcript service with its own key. I did not rely on that path.
- Multi-tool captions and multi-feature claims are only partly verified in one pass; the tool confirms a tool exists more reliably than each individual feature.
- Verdict wording. The verdict text says "N verified independent sources" but counts all independent sources, including unverified ones; the score table shows the real verified/unverified split. The model-written "bottom line" can also differ from the code-computed verdict (for example "Skip" vs "COVER IT"). The verdict is the evidence-based one and the bottom line is editorial. I did not change the appendix outputs.
- Hook numbers. Hooks may use illustrative numbers; the report labels them "not verified".
- Verification relies on web search, not live-testing the tool, and login-walled pages can't be analyzed.

With one more day I would focus on personalization: connect Instagram through MCP to get reel transcripts or frames, feed that structured data through the Litmus MCP so Claude has full context, and write the output in my own voice with my evaluation priorities. I would also fix the verdict wording, measure consistency across repeated runs, and add browser automation to actually try free tiers.
