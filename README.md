# Browser Agent

A general-purpose autonomous browser agent that takes any natural language task — reading articles, filling forms, comparing products, researching topics, interacting with web apps — navigates the web autonomously, and returns results.

Built for [PyData London 2026](https://pydata.org/).

## Architecture

Dual-agent design with sequential orchestration:

```
User Task (CLI)
     |
     v
┌──────────────┐
│ Orchestrator │
└──────┬───────┘
       │
       ├─── Planner Agent (reasoning, no tools)
       │       Returns structured PlannerAction
       │
       ├─── Executor Agent (18 browser tools)
       │       Performs the action via Playwright
       │
       ├─── Result fed back to Planner
       │       ...repeat until task complete
       │
       └─── Final answer returned to user
```

The **Planner** decides what to do. The **Executor** does it. The **Orchestrator** coordinates them in a loop, feeding results back until the task is complete or the step limit is reached.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | [Pydantic AI](https://ai.pydantic.dev/) |
| LLM | [Ollama](https://ollama.com/) (local, any model) |
| Browser | [Playwright](https://playwright.dev/python/) (async) |
| Anti-Detection | [playwright-stealth](https://pypi.org/project/playwright-stealth/) |
| Markdown | [markdownify](https://pypi.org/project/markdownify/) |
| Terminal UI | [Rich](https://rich.readthedocs.io/) |
| Config | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| Package Manager | [uv](https://docs.astral.sh/uv/) |

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- [Ollama](https://ollama.com/) running locally

### Setup

```bash
# Clone and enter project
cd browserAgent

# Install dependencies
uv sync

# Install browser
playwright install chromium

# Pull your model
ollama pull qwen3.5:35b-a3b-coding-nvfp4

# Copy config (edit to customize)
cp .env.example .env

# Run
uv run browser-agent
```

### Usage

```
╭──────────────────────────────────────╮
│  Browser Agent                       │
│  General-purpose autonomous browser  │
│  Type a task and watch it work.      │
╰──────────────────────────────────────╯

> Go to Hacker News and tell me the top 3 stories
```

The agent will open a browser, navigate, interact with pages, and stream its progress in real-time.

## Features

### 18 Browser Tools

| Category | Tools |
|----------|-------|
| Navigation | `navigate_to`, `go_back`, `go_forward` |
| Interaction | `click`, `type_text`, `select_option`, `scroll_up`, `scroll_down` |
| Extraction | `extract_text`, `extract_links`, `get_page_state`, `page_to_markdown` |
| Tabs | `open_new_tab`, `switch_tab`, `close_tab`, `list_tabs` |
| Utility | `take_screenshot`, `get_datetime` |

Tools use Playwright's accessibility locators (`get_by_text`, `get_by_role`, `get_by_label`) instead of brittle CSS selectors.

### Multi-Tab Parallel Execution

The agent can open multiple tabs and work on them simultaneously:

```
> Open HN, Reddit r/python, and GitHub trending — tell me what's hot in Python

  Step 1/15
  Action: open_new_tab("https://news.ycombinator.com")

  Step 2/15
  Action: open_new_tab("https://reddit.com/r/python")

  Step 3/15
  Action: open_new_tab("https://github.com/trending/python")

  Step 4/15  parallel
    Tab 1: Extract top stories from Hacker News
    Tab 2: Extract top posts from Reddit
    Tab 3: Extract trending repos from GitHub
```

Concurrency is gated by `asyncio.Semaphore` (default: 3 concurrent tabs).

### HTML-to-Markdown Conversion

The `page_to_markdown` tool converts page HTML to clean markdown, stripping navigation, scripts, ads, and other clutter. Ideal for research tasks where the LLM needs to read and understand page content.

### Real-Time Streaming

- Planner shows a spinner while thinking
- Executor streams tool calls and results as they happen
- No blank waiting periods

### Anti-Bot Stealth

- Custom User-Agent (Chrome on macOS)
- `playwright-stealth` applied to all pages
- Automation flags disabled (`--disable-blink-features=AutomationControlled`)
- Realistic locale, timezone, and Accept-Language headers

### Error Recovery

Each layer handles failures gracefully:
- **Tools** catch exceptions and return descriptive error strings
- **Pydantic AI** retries on validation errors (configurable `max_retries`)
- **Orchestrator** feeds failures back to the Planner for re-planning
- **BrowserSession** ensures cleanup via async context manager

## Configuration

All settings via `.env` file with `AGENT_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_MODEL_NAME` | `qwen3.5:35b-a3b-coding-nvfp4` | Ollama model |
| `AGENT_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama endpoint |
| `AGENT_HEADLESS` | `false` | Hide browser window |
| `AGENT_MAX_STEPS` | `15` | Max planner-executor cycles |
| `AGENT_MAX_RETRIES` | `3` | LLM output validation retries |
| `AGENT_MAX_CONCURRENT` | `3` | Max parallel tab executions |
| `AGENT_MAX_TEXT_LENGTH` | `4000` | Page text truncation limit |
| `AGENT_VIEWPORT_WIDTH` | `1280` | Browser viewport width |
| `AGENT_VIEWPORT_HEIGHT` | `720` | Browser viewport height |

## Project Structure

```
browserAgent/
├── pyproject.toml
├── .env.example
├── src/
│   └── browser_agent/
│       ├── main.py                 # CLI entry point
│       ├── config.py               # Settings (pydantic-settings)
│       ├── models.py               # PlannerAction, BrowserState, StepResult
│       ├── orchestrator.py         # Planner <-> Executor loop
│       ├── display.py              # Rich terminal output
│       ├── agents/
│       │   ├── planner.py          # Planner agent (reasoning only)
│       │   └── executor.py         # Executor agent (18 tools)
│       ├── tools/
│       │   ├── navigation.py       # navigate_to, go_back, go_forward
│       │   ├── interaction.py      # click, type_text, select_option, scroll
│       │   ├── extraction.py       # extract_text, extract_links, get_page_state
│       │   ├── markdown.py         # page_to_markdown
│       │   ├── tabs.py             # open_new_tab, switch_tab, close_tab, list_tabs
│       │   ├── screenshot.py       # take_screenshot
│       │   └── datetime.py         # get_datetime
│       └── browser/
│           └── session.py          # BrowserSession + TabSession
└── docs/
    └── superpowers/specs/
        └── 2026-03-31-browser-agent-design.md
```

## Example Tasks

```
# Research
Go to Hacker News and tell me the top 3 stories right now

# Form interaction
Go to Wikipedia and look up the population of Lagos, Nigeria

# Multi-step workflow
Go to GitHub trending, filter by Python, and summarize the top repo

# Multi-tab parallel research
Open HN, Reddit r/python, and GitHub trending — compare what's popular in Python today

# Deep reading
Go to paulgraham.com/articles.html, pick the most recent essay, and summarize it

# Time-aware tasks
What time is it? Then check timeanddate.com to verify
```

## How It Works

1. You type a task in the CLI
2. The **Orchestrator** creates a browser session and starts the loop
3. The **Planner** receives the task + current browser state and decides the next step
4. The **Executor** carries out the instruction using browser tools
5. The result is fed back to the Planner
6. Repeat until the Planner has enough info and returns a final answer
7. The answer is displayed in a styled panel

The Planner only sees the last 3 steps of history and truncated page text to stay within the LLM's context window.
