# AI Usage Disclosure

## AI Tools Used

### 1. Claude (Anthropic) — Claude Pro subscription
**Role**: Development partner for the entire project.
- **Project design**: Brainstormed the tool concept, refined the pipeline architecture, and scoped the project for the time constraint.
- **Code generation**: Claude wrote the initial drafts of all three Python modules (`fetcher.py`, `analyzer.py`, `main.py`), which I reviewed, tested, and iterated on.
- **Prompt engineering**: Collaboratively designed the Gemini prompts for claim extraction and verification. Claude suggested the two-call architecture (extract then verify) after the single-call approach produced less structured output.
- **Documentation**: Claude helped draft the README, this disclosure, and the technical note, which I reviewed and edited.
- **Debugging**: Used Claude to diagnose issues with GitHub API rate limiting and to design the fallback fetching strategy.

### 2. Google Gemini 1.5 Flash — Free API tier
**Role**: The LLM backbone of the tool itself.
- Performs claim extraction from fetched content
- Verifies each claim against the source material
- Scores tryability and generates content verdicts
- Used via the `google-generativeai` Python SDK

## How I Verified AI-Generated Code and Outputs

1. **Code review**: Read through every function Claude generated. Understood the flow before running anything. Made changes where the logic didn't match my intent.
2. **Module testing**: Tested the fetcher independently against real URLs before connecting it to the analyzer.
3. **Edge case testing**: Manually tested dead links, non-AI URLs, Instagram URLs, and GitHub repos to verify error handling worked.
4. **Prompt iteration**: Ran the Gemini prompts against multiple tools and refined them when the output was too generic or incorrectly structured.
5. **Output validation**: Cross-checked Gemini's claim verdicts against what I could verify manually (e.g., checking if a GitHub repo actually requires paid API keys when the tool says it does).

## What I Understand and Can Explain

- The full pipeline: URL → fetch → extract claims → verify → score → verdict
- Why two LLM calls work better than one for this task
- How BeautifulSoup parsing works and why certain HTML elements are stripped
- The GitHub API fallback chain (API → raw.githubusercontent → page scrape)
- How Gemini's structured output is parsed and error-handled (including the markdown code fence stripping)
- The tryability scoring criteria and why each factor matters for content decisions
- All edge cases and how they're handled
