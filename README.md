# Browser Agent

A general-purpose autonomous browser agent that takes any natural language task — reading articles, filling forms, comparing products, researching topics, interacting with web apps — navigates the web autonomously, and returns results.

Built for [PyData London 2026](https://pydata.org/).

## Architecture

Dual-agent design with sequential orchestration:

```
User Task (Textual TUI)
     |
     v
┌──────────────┐
│ Orchestrator │  (+ MemoryStore, SessionLogger)
└──────┬───────┘
       │
       ├─── Planner Agent (reasoning, no tools)
       │       Returns structured PlannerAction
       │
       ├─── Executor Agent (36 browser tools)
       │       Performs the action via Playwright
       │
       ├─── Result fed back to Planner
       │       ...repeat until task complete
       │
       └─── Final answer + persisted memory
```

The **Planner** decides what to do. The **Executor** does it. The **Orchestrator** coordinates them in a loop, feeding results back until the task is complete or the step limit is reached. A persistent **MemoryStore** (SQLite) preserves findings and conversation history across runs.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | [Pydantic AI](https://ai.pydantic.dev/) |
| LLM Providers | Ollama (local), OpenAI, Anthropic, Google |
| Browser | [Playwright](https://playwright.dev/python/) (async) |
| Anti-Detection | [playwright-stealth](https://pypi.org/project/playwright-stealth/) |
| Markdown | [markdownify](https://pypi.org/project/markdownify/) |
| Terminal UI | [Textual](https://textual.textualize.io/) + [Rich](https://rich.readthedocs.io/) |
| Persistent Memory | [aiosqlite](https://github.com/omnilib/aiosqlite) |
| Smart Locator | [sentence-transformers](https://www.sbert.net/) + [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) (optional) |
| Config | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| Package Manager | [uv](https://docs.astral.sh/uv/) |

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- One of: [Ollama](https://ollama.com/) running locally, an OpenAI / Anthropic / Google API key

### Setup

```bash
# Clone and enter project
cd browserAgent

# Install dependencies
uv sync

# (Optional) install smart-locator extras for intent-based element finding
uv sync --extra smart

# Install browser
uv run playwright install chromium

# Pull a local model (if using Ollama)
ollama pull qwen3.5:35b-a3b-coding-nvfp4

# Copy config (edit to customize provider, model, API keys, etc.)
cp .env.example .env

# Run
uv run browser-agent
```

### Usage

The app boots into a Textual TUI:

```
╭─ Browser Agent ──────────────────────────────────╮
│  Ready                                           │
│                                                  │
│  ▶ Type a task and press Enter...                │
╰──────────────────────────────────────────────────╯
```

```
> Go to Hacker News and tell me the top 3 stories
```

The agent will open a browser, navigate, interact with pages, and stream its progress in real-time.

### Slash Commands

| Command | Purpose |
|---------|---------|
| `/help` | Show available commands |
| `/settings` | Show current configuration |
| `/provider <name>` | Switch provider (`ollama`, `openai`, `anthropic`, `google`) |
| `/model <name>` | Switch model for the current provider |
| `/vision` | Toggle vision mode (send screenshots to the LLM) |
| `/smart` | Toggle smart locator (intent-based element finding) |
| `/headless` | Toggle headless browser mode |
| `/steps <n>` | Set the planner-executor step limit |
| `/retries <n>` | Set LLM validation retry count |
| `/concurrent <n>` | Set the max parallel tabs |
| `/connect [port]` | Launch + attach to a real Chrome instance via CDP (default port 9222) |
| `/disconnect` | Stop using CDP, fall back to standalone browser |
| `/memory` | List saved findings |
| `/clear` | Clear the output log |

Press `Ctrl+C` to interrupt the running task, `Ctrl+Q` to quit. Use `↑` / `↓` for input history and `Tab` to accept the slash-command suggestion.

## Features

### 36 Browser Tools

| Category | Tools |
|----------|-------|
| Navigation | `navigate_to`, `go_back`, `go_forward` |
| Interaction | `click`, `click_selector`, `type_text`, `press_key`, `select_option`, `scroll_up`, `scroll_down` |
| Discovery | `find_elements` (verify locators before acting) |
| Extraction | `extract_text`, `extract_links`, `get_page_state`, `page_to_markdown` |
| Search | `search_bing`, `search_duckduckgo`, `search_brave` |
| Tabs | `open_new_tab`, `switch_tab`, `close_tab`, `list_tabs` |
| Memory | `save_finding`, `recall_finding`, `search_memory`, `list_memories`, `delete_finding` |
| Smart Locator | `smart_find`, `smart_click`, `smart_fill` (require `[smart]` extra) |
| Human-in-the-loop | `ask_human`, `fill_form_with_human`, `wait_for_human` |
| Utility | `take_screenshot`, `get_datetime`, `close_browser` |

Tools use Playwright's accessibility locators (`get_by_text`, `get_by_role`, `get_by_label`) instead of brittle CSS selectors. `click_selector` is available when CSS is genuinely needed.

### Multi-Provider LLM Support

Switch providers at runtime via `/provider`. The `model_factory` builds a Pydantic AI `Model` for the active provider:

- **Ollama** — local inference (default: `qwen3.5:35b-a3b-coding-nvfp4`)
- **OpenAI** — `gpt-4o` and friends
- **Anthropic** — `claude-opus-4-7`, `claude-sonnet-4-6`, etc.
- **Google** — `gemini-2.0-flash`, etc.

Hosted Ollama (with `X-API-KEY` header) is supported via `AGENT_USE_HOSTED_MODEL` / `AGENT_HOSTED_OLLAMA_*`.

### Vision Mode

Enable via `/vision` or `AGENT_USE_VISION=true`. The orchestrator captures a JPEG screenshot each step and sends it alongside the prompt — useful with multimodal models (Claude, GPT-4o, Gemini).

### Smart Locator (optional)

When enabled (`/smart` or `AGENT_USE_SMART_LOCATOR=true`), the basic `click` / `type_text` / `find_elements` tools are swapped for embedding-based `smart_click` / `smart_fill` / `smart_find`. These build a `PageIndex` from the Chrome accessibility tree, enrich each interactive element with structural context (form, heading, sibling labels), and rank candidates with a sentence-transformer (`BAAI/bge-small-en-v1.5`) plus fuzzy matching. Install with `uv sync --extra smart`.

### Persistent Memory

A SQLite database (`memory.db`) stores three tables:

- **findings** — named facts the agent saves via `save_finding`. Recall across sessions with `recall_finding`, `search_memory`, or the `/memory` command.
- **conversations** — every `(task, answer, steps)` triple, keyed by session.
- **summaries** — when the cumulative conversation context exceeds `AGENT_MAX_MEMORY_LENGTH`, the orchestrator compresses earlier turns into a single summary using the active LLM.

### Human-in-the-Loop

The agent can pause and prompt you when it needs help:

- **`ask_human`** — open question or multiple-choice selection (rendered as a Textual `RadioSet`).
- **`fill_form_with_human`** — auto-detects visible form fields and prompts for each one (with masked input for password fields).
- **`wait_for_human`** — pauses for CAPTCHAs, 2FA, drag-and-drop, or anything else you need to do in the visible browser window.

You can also type new guidance at any moment while a task is running — it will be queued and injected into the next planner step.

### Chrome CDP Connection

`/connect [port]` launches a real Chrome instance (or attaches to an existing one) on a debug port and drives it over CDP. On first run a copy of your Chrome profile is taken to `/tmp/chrome-debug-profile` so logged-in sessions, cookies, and extensions are available without touching your real profile. `/disconnect` returns to a standalone Playwright browser.

### Multi-Tab Parallel Execution

The planner can emit `parallel_instructions` — a list of `(tab_id, instruction)` pairs — and the orchestrator dispatches them concurrently:

```
> Open HN, Reddit r/python, and GitHub trending — tell me what's hot in Python

  Step 1/15  open_new_tab("https://news.ycombinator.com")
  Step 2/15  open_new_tab("https://reddit.com/r/python")
  Step 3/15  open_new_tab("https://github.com/trending/python")
  Step 4/15  parallel
    Tab 1: Extract top stories from Hacker News
    Tab 2: Extract top posts from Reddit
    Tab 3: Extract trending repos from GitHub
```

Concurrency is gated by `asyncio.Semaphore(AGENT_MAX_CONCURRENT)` (default: 3).

### Real-Time Streaming

- Planner shows a spinner while thinking
- Executor streams tool calls, tool results, and token deltas as they happen via `run_stream_events`
- Queued user guidance appears as a banner without interrupting the active step

### Session Logging

Every run writes to `logs/<timestamp>_<session_id>/`:

- `events.jsonl` — structured event stream (planner / executor / tool / state / error events with durations)
- `summary.md` — human-readable per-step summary with timings and final answer
- `screenshots/step_NN_error.jpg` — captured automatically on tool failures in vision mode

### Anti-Bot Stealth

- Custom User-Agent (Chrome on macOS)
- `playwright-stealth` applied to every page
- Automation flags disabled (`--disable-blink-features=AutomationControlled`, `--enable-automation` removed)
- Realistic locale (`en-US`), timezone (`America/New_York`), and `Accept-Language` headers

### Error Recovery

- **Tools** catch exceptions and return descriptive error strings — failures become regular planner inputs, not crashes
- **Pydantic AI** retries on validation errors (configurable `max_retries`)
- **Orchestrator** caches browser state per URL, invalidates after actions, and auto-dismisses cookie/overlay popups when a step fails with a recognizable "intercepting pointer events" / timeout error
- **BrowserSession** ensures cleanup via async context manager

## Configuration

All settings live in `.env` with the `AGENT_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PROVIDER` | `ollama` | LLM provider (`ollama`, `openai`, `anthropic`, `google`) |
| `AGENT_MODEL_NAME` | `qwen3.5:35b-a3b-coding-nvfp4` | Model name for the active provider |
| `AGENT_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Local Ollama endpoint |
| `AGENT_OPENAI_API_KEY` | _(empty)_ | OpenAI API key |
| `AGENT_OPENAI_BASE_URL` | _(empty)_ | Optional OpenAI-compatible endpoint |
| `AGENT_ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key |
| `AGENT_GOOGLE_API_KEY` | _(empty)_ | Google API key |
| `AGENT_USE_HOSTED_MODEL` | `false` | Use a remote hosted Ollama instance |
| `AGENT_HOSTED_OLLAMA_BASE_URL` | _(empty)_ | Hosted Ollama endpoint |
| `AGENT_HOSTED_OLLAMA_API_KEY` | _(empty)_ | API key sent via `X-API-KEY` header |
| `AGENT_USE_VISION` | `false` | Send screenshots to the LLM each step |
| `AGENT_USE_SMART_LOCATOR` | `false` | Enable embedding-based element search (requires `[smart]` extra) |
| `AGENT_HEADLESS` | `false` | Hide the browser window |
| `AGENT_MAX_STEPS` | `15` | Max planner-executor cycles per task |
| `AGENT_MAX_RETRIES` | `3` | LLM output validation retries |
| `AGENT_MAX_CONCURRENT` | `3` | Max parallel tab executions |
| `AGENT_MAX_TEXT_LENGTH` | `2000` | Page text truncation limit |
| `AGENT_MAX_MEMORY_LENGTH` | `8000` | Trigger conversation summarization when context exceeds this |
| `AGENT_MEMORY_DB_PATH` | `memory.db` | SQLite path for persistent memory |
| `AGENT_LOGS_DIR` | `logs` | Directory for per-session structured logs |
| `AGENT_VIEWPORT_WIDTH` | `1280` | Browser viewport width |
| `AGENT_VIEWPORT_HEIGHT` | `720` | Browser viewport height |
| `AGENT_CHROME_CDP_URL` | _(empty)_ | Set automatically by `/connect`; pre-populate to attach on startup |
| `AGENT_LOG_EXPERIMENTS` | `false` | Also write per-run Markdown logs to `experiment_logs/` |

## Project Structure

```
browserAgent/
├── pyproject.toml
├── .env.example
├── memory.db                       # persistent SQLite memory (auto-created)
├── logs/                           # per-session structured logs
├── src/
│   └── browser_agent/
│       ├── main.py                 # Textual TUI entry point
│       ├── config.py               # Settings (pydantic-settings)
│       ├── models.py               # PlannerAction, BrowserState, StepResult, AgentDeps
│       ├── model_factory.py        # Builds a pydantic_ai Model from settings
│       ├── orchestrator.py         # Planner <-> Executor loop, vision, parallel exec
│       ├── memory.py               # MemoryStore (findings, conversations, summaries)
│       ├── smart_locator.py        # AX-tree PageIndex + sentence-transformer search
│       ├── session_logger.py       # JSONL events + Markdown summary writer
│       ├── display.py              # Textual / Rich rendering helpers
│       ├── agents/
│       │   ├── planner.py          # Planner agent + system prompt
│       │   └── executor.py         # Executor agent (all tools)
│       ├── tools/
│       │   ├── navigation.py       # navigate_to, go_back, go_forward
│       │   ├── interaction.py      # click, click_selector, type_text, press_key, select_option, scroll
│       │   ├── extraction.py       # extract_text, extract_links, get_page_state
│       │   ├── markdown.py         # page_to_markdown
│       │   ├── tabs.py             # open_new_tab, switch_tab, close_tab, list_tabs
│       │   ├── search.py           # search_bing, search_duckduckgo, search_brave
│       │   ├── memory_tools.py     # save/recall/search/list/delete_finding
│       │   ├── human.py            # ask_human, fill_form_with_human, wait_for_human
│       │   ├── smart_tools.py      # smart_find, smart_click, smart_fill
│       │   ├── dom_query.py        # find_elements (locator verification)
│       │   ├── browser_control.py  # close_browser
│       │   ├── screenshot.py       # take_screenshot
│       │   └── datetime.py         # get_datetime
│       └── browser/
│           └── session.py          # BrowserSession + TabSession (Playwright / CDP)
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

# Human-in-the-loop
Log into my GitHub and star anthropics/claude-code        # uses fill_form_with_human
Buy this on Amazon                                        # asks for shipping/payment via ask_human
Solve the CAPTCHA on this page                            # wait_for_human pauses for you

# Cross-session memory
Remember the top 5 HN stories as "hn_today"               # save_finding
What did I save about HN earlier?                         # recall_finding / search_memory
```

## How It Works

1. You type a task in the TUI.
2. The **Orchestrator** opens a `BrowserSession` (standalone Playwright or attached Chrome via CDP) and initializes the loop.
3. The **MemoryStore** is loaded — earlier conversation context (and any auto-summary) is included in the planner prompt.
4. The **Planner** receives the task, current browser state, recent step history, and any queued user guidance, and decides the next step (or marks the task complete).
5. The **Executor** carries out the instruction using its tool set. Tool calls, results, and token deltas stream back to the TUI in real time.
6. The result is fed back into the next planner prompt.
7. Repeat until the planner returns `is_complete=true`, the task is interrupted, or `max_steps` is reached.
8. The final answer + step count are displayed and persisted to `memory.db` and `logs/`.

The planner only ever sees the last 3 step results plus truncated page text, so the prompt stays within the model's context window even on long tasks.

## Future

- Stagehand integration (the tool layer is designed to be swappable)
- More providers (MLX local, hosted vLLM)
- Richer memory (vector store for `search_memory`)
