# AI Hype Claim Checker

**Paste an AI tool's URL. Get a verdict: what's real, what's hype, and whether it's worth covering.**

Built for content researchers who evaluate dozens of AI tools weekly and need to quickly separate genuine capabilities from marketing fluff.

## The Problem

AI content pages like [@aistuff.muu](https://instagram.com/aistuff.muu) discover 10-20 new AI tools per week through reels, tweets, and launches. Most make bold claims — "replaces your entire workflow," "no code needed," "completely free." Before investing hours into a feature or tutorial, a researcher needs to know:

- Do the claims actually hold up?
- Can someone try this tool in under 10 minutes?
- Is there a free tier, or is "free" just the landing page?
- What's the content angle — the real story vs. the marketing story?

Doing this manually takes 30-60 minutes per tool. This tool does it in under a minute — via CLI or a web interface.

## How It Works

```
Input (URL) → Fetch content → Extract claims → Verify each claim → Score tryability → Content verdict
```

**Pipeline:**
1. **Fetch** — Pulls content from GitHub READMEs, landing pages, or accepts pasted Instagram captions
2. **Extract Claims** — Gemini identifies 3-7 specific capability, performance, ease-of-use, scope, and cost claims
3. **Verify** — Each claim gets a verdict: Confirmed, Partially True, or Exaggerated, with evidence
4. **Tryability Score** — Free tier? Setup under 10 min? Visible result? Blockers?
5. **Content Verdict** — One of three outcomes:
   - **COVER IT** — Claims hold, tool is tryable, good content potential
   - **COVER THE GAP** — Overhyped, but the gap itself is the content angle
   - **SKIP** — Too expensive, too complex, or too boring

## Setup

### Requirements
- Python 3.9+
- A free Google Gemini API key

### Installation

```bash
git clone https://github.com/aprajitasinghUGTBM2028-ops/portfolio.git
cd portfolio
pip install -r claim-checker/requirements.txt
```

### API Key

Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey), then:

```bash
export GEMINI_API_KEY='your-key-here'
```

## Usage

### Web Interface (Streamlit)

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser, enter your Gemini API key in the sidebar, paste a URL, and click "Check it."

### CLI — Check a GitHub repo
```bash
python main.py https://github.com/assafelovic/gpt-researcher
```

### Check a landing page
```bash
python main.py https://some-ai-tool.com
```

### Check an Instagram reel (paste caption manually)
```bash
python main.py https://instagram.com/reel/xyz
# You'll be prompted to paste the caption
```

### With caption pre-provided
```bash
python main.py https://instagram.com/reel/xyz --caption "This AI tool is insane! It can..."
```

### Save JSON output
```bash
python main.py https://github.com/owner/repo --json
# Saves full analysis to last_result.json
```

## Example Output

```
╔══════════════════════════════════════════════════╗
║           AI HYPE CLAIM CHECKER                  ║
╚══════════════════════════════════════════════════╝

✓ Fetched GitHub repo: assafelovic/gpt-researcher
  ⭐ 16000 stars | Python | Last push: 2024-12-15

🔍 TOOL: GPT Researcher
   Open-source deep research agent for web and local research

📋 EXTRACTED CLAIMS:
  1. [Capability] Can generate detailed research reports from 20+ sources
  2. [Performance] Produces reports exceeding 2,000 words
  3. [Cost] Open source and free to use
  ...

🔬 CLAIM VERIFICATION:
  1. Can generate detailed research reports from 20+ sources
     → CONFIRMED
     README shows multi-agent architecture with crawler agents
  2. ...

🧪 TRYABILITY: [███░░] 3/5
   Free tier:      yes (open source)
   Setup time:     10-30 min
   Visible result: yes
   Blockers: Requires OpenAI API key, Tavily API key

═══════════════════════════════════════════════════

📣 CONTENT VERDICT: COVER THE GAP
   Hype Score: 🔥🔥🔥🔥🔥🔥 (6/10)

   Why: The tool is genuinely capable but claims "free" while requiring
   paid API keys (OpenAI + Tavily). The gap between "open source" and
   "actually free to run" is the content angle.

   💡 Content Angle: "This research agent is powerful but 'open source'
   doesn't mean 'free' — here's what it actually costs to run."
```

## Edge Cases Handled

| Scenario | Behavior |
|----------|----------|
| Dead link / domain down | Reports "Could not connect" with the URL |
| 404 page | Reports "Page not found" |
| Not an AI tool | Detects and reports "This doesn't appear to be an AI tool" |
| Instagram reel | Prompts for manual caption input (Instagram requires auth) |
| No claims found | Reports "Could not extract specific claims" |
| GitHub repo with no README | Reports "No README found" |
| Rate-limited GitHub API | Falls back to raw.githubusercontent.com |

## Project Structure

```
claim-checker/
├── app.py           # Streamlit web interface
├── main.py          # CLI interface and pretty output
├── fetcher.py       # URL fetching and content extraction
├── analyzer.py      # Gemini-powered claim extraction and verification
├── requirements.txt # Python dependencies
└── README.md        # This file
```

## Limitations

- **Instagram scraping**: Can't auto-fetch reel captions (requires login). User pastes caption manually.
- **LLM accuracy**: Gemini's verification is reasoning-based, not live-testing. It can't actually *try* the tool.
- **Single-pass**: Doesn't follow links from the page to verify claims against documentation.
- **Rate limits**: GitHub API has rate limits for unauthenticated requests (fallback handles this).
- **Network-dependent**: Requires internet access to fetch URLs and call Gemini API.

## What I'd Build Next (with another day)

1. **Auto-follow links** — Click through to docs/pricing pages for deeper verification
2. **Screenshot capture** — Visually show what the tool looks like
3. **Batch mode** — Check a list of URLs from a file
4. **History tracking** — Save past checks to compare tools
5. **Reel caption extraction** — Use browser automation to grab Instagram captions
6. **Live testing** — Actually try free-tier tools and report real results
