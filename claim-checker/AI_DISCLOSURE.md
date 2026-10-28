# AI Usage Disclosure — Litmus: Test the Promise

## AI Used to Build This Project

**Claude (chat + code)** was my development partner. Claude helped design the 9-step pipeline architecture, wrote initial code drafts which I reviewed and iterated on across multiple sessions, identified and fixed bugs (setup time parsing showing 526 min instead of 18 min, overly generic claim extraction), and built the MCP server integration.

**GPT-4o API** is used inside the product itself, not for building it.

## How AI Is Used Inside the Product

GPT-4o powers the pipeline at runtime:
- **Extraction** — Classifies tools, plans search queries, pulls structured facts with quotes
- **Search** — Uses the Responses API with web_search to find independent sources on Reddit, HN, YouTube, LinkedIn
- **Writing** — Generates the scored report and reel hooks from verified evidence
- **Self-critique** — A separate call reviews the report against raw evidence

What GPT-4o does NOT do: decide verdicts, pick scores, or confirm its own claims. Code handles all of that.

## My Decisions

- **Problem selection**: Chose to automate the tool verification step of my content workflow, based on the bottleneck I described in my initial screening
- **Instagram edge case solution**: When reels can't be auto-fetched, take the caption as input instead. Designed the fallback flow (detect Instagram URL → prompt for caption → process)
- **MCP as a second delivery mode**: Proposed running the pipeline as an MCP inside Claude, so Claude can use its own connectors to fetch Instagram data, bypassing the caption limitation entirely
- **Real web search over hardcoded sources**: Decided the pipeline should actually search Google/Reddit/HN/YouTube/LinkedIn live, not check against a fixed list of sources
- **Code-computed verdicts**: Decided the model should return evidence IDs and code should derive verdicts — not let the model judge its own claims
- **Independent source verification**: Each claim is checked against sources from different domains. Same-domain sources don't count as independent confirmation
- **Quote-level validation**: Every fact must include a quote that actually appears on the source page — no paraphrasing accepted
- **Per-feature claim extraction**: Instructed the prompt to extract each specific capability claim separately instead of summarizing them into one generic claim
- **Multi-tool and multi-feature scoping**: Identified these as known limitations and scoped what the pipeline can realistically verify in one pass
- **All testing and bug catching**: Tested every output against real URLs, caught the 526 min setup time bug and the generic claims issue by reading the output myself

## AI's Contribution

- Code drafting from my specifications
- Prompt engineering for each pipeline step
- Bug fixes after I identified the issues
- Documentation drafts which I reviewed and edited

## How I Verified AI-Generated Code

- Read every function and understood the flow before running it
- Tested with real URLs (Prompt Motion, gstack, Knowledge Work Plugins) and compared against manual research
- Cross-checked GPT-4o's claim verdicts against what I could verify manually
- Multiple rounds of testing, feedback, and rewriting — the 9-step pipeline replaced an earlier single-pass approach that was unreliable
- Caught specific bugs myself (526 min setup time, generic claims) and worked with Claude to fix them
