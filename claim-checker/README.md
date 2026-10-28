# Litmus — Test the Promise

**Paste an AI tool's URL. Get a verdict: what's real, what's hype, and whether it's worth covering.**

**[Try it live](https://ideahypeanalyser.streamlit.app)** (password hint: the app name, lowercase, no spaces)

Built for content researchers who evaluate dozens of AI tools weekly and need to quickly separate genuine capabilities from marketing fluff.

## The Problem

AI content pages discover 10-20 new AI tools per week through reels, tweets, and launches. Most make bold claims — "replaces your entire workflow," "no code needed," "completely free." Before investing hours into a feature or tutorial, a researcher needs to know:

- Do the claims actually hold up?
- Can someone try this tool in under 10 minutes?
- Is there a free tier, or is "free" just the landing page?
- What's the content angle — the real story vs. the marketing story?

Doing this manually takes 30-60 minutes per tool. This tool does it in under a minute.

## How It Works

The tool runs a 9-step AI pipeline:

```
URL → Fetch + sub-pages → Classify & plan → Search for evidence → Extract facts
    → Validate facts (code) → Fill gaps → Write report → Critique report → Hooks
```

1. **Classify & Plan** — AI identifies the tool type and plans what evidence to gather
2. **Build Sources** — Code indexes all fetched content by source ID
3. **Search for Evidence** — AI runs web searches (Reddit, Product Hunt, blogs) for independent verification
4. **Extract Facts** — AI extracts structured facts with exact quotes and source IDs
5. **Validate Facts** — Code checks quotes against source text, fixes statuses using domain comparison
6. **Find Gaps** — AI identifies missing evidence and runs additional searches if needed
7. **Write Report** — AI writes a report citing only validated fact IDs
8. **Critique Report** — A separate AI call checks the report against the evidence
9. **Write Hooks** — AI generates reel hooks from evidence, code validates numbers and attribution

**Key design decisions:**
- **Code computes verdicts, not the model** — the model returns evidence IDs, code derives SITE_SAYS/INDEPENDENT/UNVERIFIABLE/CONTRADICTED from source domains
- **Domain-based independence** — compares source URL domains against the tool's own domain, not a hardcoded whitelist
- **Prompt injection fencing** — all page content wrapped in `<data instructions="none">` tags
- **Score clamping** — all scores enforced by code (tryability 1-5, virality/hype 1-10)

## Setup

### Requirements
- Python 3.9+
- An OpenAI API key (GPT-4o with web search)

### Installation

```bash
git clone https://github.com/aprajitasinghUGTBM2028-ops/portfolio.git
cd portfolio/claim-checker
pip install -r requirements.txt
```

### Configuration

1. Copy the example secrets file:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
2. Edit `.streamlit/secrets.toml` with your OpenAI API key and optionally an app password.
   `APP_PASSWORD` is optional: if it is empty, the app shows no password prompt.

### Run

```bash
streamlit run app.py
```

Or use the [live deployment](https://ideahypeanalyser.streamlit.app).

## MCP Server (Claude Desktop)

The same pipeline is available as a tool inside Claude Desktop via `mcp_server.py`.

Add this to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "litmus": {
      "command": "python",
      "args": ["path/to/claim-checker/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

The `litmus_test` tool will appear in Claude Desktop.

## Tests

```bash
python -m pytest tests -q
```

31 offline tests using a FakeLLM — no API key needed. They verify that code validators reject bad model output (wrong quotes, same-domain sources, invented numbers, prompt injection).

For live integration tests (requires an API key):

```bash
python live_check.py
```

## Cost

Each check runs 5-7 API calls (one with web search). Estimated cost: **$0.05-0.15 per check** depending on page size and whether gap searches are needed. Set a monthly spend limit on your OpenAI key.

## Supported Input Types

| Input | How it works |
|-------|-------------|
| Landing page URL | Fetches page + sub-pages (pricing, blog, docs, sponsor) |
| GitHub repo URL | Fetches README via API with raw fallback |
| Instagram reel URL | Prompts for manual caption paste (Instagram blocks auto-fetch) |

## Project Structure

```
claim-checker/
├── app.py              # Streamlit web interface
├── fetcher.py          # URL fetching, sub-page crawling, SSRF protection
├── analyzer.py         # 9-step AI pipeline with code validators
├── checks.py           # Rule-based score clamping and validation helpers
├── mcp_server.py       # FastMCP server for Claude Desktop integration
├── live_check.py       # Live integration test runner
├── requirements.txt    # Python dependencies
├── .gitignore
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── tests/
│   ├── test_pipeline.py
│   └── test_consistency.py
├── README.md
├── TECHNICAL_NOTE.md
└── AI_DISCLOSURE.md
```

## Limitations

- **Instagram scraping**: Can't auto-fetch reel captions (auth wall). User pastes caption manually.
- **LLM accuracy**: GPT-4o's verification uses web search, not live-testing. It can't actually try the tool.
- **Run-to-run variance**: Different runs may produce slightly different results due to web search variability.
- **Rate limits**: GitHub API has rate limits for unauthenticated requests (fallback handles this).
- **JS-rendered pages**: Pages that require JavaScript to render return thin content and are rejected with a message to paste text manually.
