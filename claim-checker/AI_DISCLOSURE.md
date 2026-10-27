# AI Usage Disclosure

## AI Tools Used

### 1. Claude (Anthropic) — Claude Code
**Role**: Development partner for the entire project.
- **Architecture design**: Designed the 9-step pipeline (classify → plan → collect → extract → validate → gaps → write → critique → hooks) after the initial single-pass approach produced unreliable output.
- **Code generation**: Claude wrote the initial drafts of all Python modules (`fetcher.py`, `analyzer.py`, `app.py`), which I reviewed, tested, and iterated on across multiple sessions.
- **Bug analysis and fixing**: Claude analyzed and fixed 9 prioritized bugs including domain logic, verdict computation, parse tolerance, XSS protection, SSRF prevention, and prompt injection fencing.
- **Prompt engineering**: Collaboratively designed the GPT-4o prompts for each pipeline step. Claude suggested returning `evidence_ids` instead of verdicts to prevent the model from deciding its own scores.
- **Code review**: Claude identified security issues (key leakage between Streamlit sessions, `unsafe_allow_html` with model text, private IP access) and fixed them.
- **Documentation**: Claude helped draft the README, this disclosure, and the technical note, which I reviewed and edited.
- **Development branch**: All work done on `claude/brave-mccarthy-xs1zcw` via Claude Code remote sessions.

### 2. OpenAI GPT-4o — Paid API
**Role**: The LLM backbone of the tool itself.
- Classifies tools and plans research queries (Chat Completions API with JSON mode)
- Searches the web for independent evidence (Responses API with `web_search` tool)
- Extracts structured facts with quotes and source IDs
- Writes reports citing validated fact IDs
- Critiques its own reports against evidence (separate call)
- Generates reel hooks from evidence
- Used via the `openai` Python SDK (>=1.66.0 for Responses API support)

### 3. Streamlit — Web framework
**Role**: Frontend hosting and deployment.
- Provides the web interface, password gate, and usage counter
- Deployed at ideahypeanalyser.streamlit.app
- Secrets management for API keys

## How I Verified AI-Generated Code and Outputs

1. **Code review**: Read through every function Claude generated. Understood the flow before running anything. Made changes where the logic didn't match my intent.
2. **Bug analysis**: Identified 9 bugs in the generated code by testing with real URLs (Prompt Motion, gstack) and comparing output against manual research. Provided Claude with specific code fixes for each.
3. **Output validation**: Cross-checked GPT-4o's claim verdicts against what I could verify manually (e.g., checking if a tool actually requires paid API keys when it claims to be "free").
4. **Iterative improvement**: Went through multiple rounds of testing → feedback → rewrite. The 9-step pipeline replaced an earlier single-pass approach that produced unreliable results.
5. **Security review**: Identified key leakage, XSS, and SSRF vulnerabilities in the generated code and required fixes.

## What I Understand and Can Explain

- The full 9-step pipeline and why each step exists
- Why code computes verdicts instead of the model (prevents "everything is CONFIRMED")
- How domain-based independence works and why it replaced the whitelist
- How prompt injection fencing prevents malicious page content from hijacking the analysis
- The BeautifulSoup parsing, sub-page crawling, and priority sorting
- How the OpenAI Responses API with web_search differs from Chat Completions
- The tryability scoring criteria and why "free to browse" differs from "free to create"
- All edge cases and how they're handled (dead links, thin content, login walls, Instagram)
- The security measures (SSRF blocking, XSS escaping, key isolation, prompt fencing)
