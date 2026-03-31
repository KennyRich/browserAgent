from urllib.parse import quote_plus

from pydantic_ai import RunContext

from browser_agent.models import AgentDeps


async def _search(ctx: RunContext[AgentDeps], engine_url: str, query: str) -> str:
    page = ctx.deps.browser.page
    url = f"{engine_url}{quote_plus(query)}"
    try:
        await page.goto(url, wait_until="domcontentloaded")
        text = await page.inner_text("body", timeout=10000)
        return text.strip()[:4000]
    except Exception as e:
        return f"Search failed: {e}"


async def search_bing(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web using Bing and return the results.

    Args:
        query: The search query.
    """
    return await _search(ctx, "https://www.bing.com/search?q=", query)


async def search_duckduckgo(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web using DuckDuckGo and return the results.

    Args:
        query: The search query.
    """
    return await _search(ctx, "https://duckduckgo.com/?q=", query)


async def search_brave(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web using Brave Search and return the results.

    Args:
        query: The search query.
    """
    return await _search(ctx, "https://search.brave.com/search?q=", query)
