from pydantic_ai import RunContext

from browser_agent.models import AgentDeps


async def navigate_to(ctx: RunContext[AgentDeps], url: str) -> str:
    """Navigate the browser to a URL.

    Args:
        url: The full URL to navigate to.
    """
    try:
        await ctx.deps.browser.page.goto(url, wait_until="domcontentloaded")
        return f"Navigated to {ctx.deps.browser.page.url}"
    except Exception as e:
        return f"Failed to navigate to {url}: {e}"


async def go_back(ctx: RunContext[AgentDeps]) -> str:
    """Go back to the previous page in browser history."""
    try:
        await ctx.deps.browser.page.go_back(wait_until="domcontentloaded")
        return f"Went back to {ctx.deps.browser.page.url}"
    except Exception as e:
        return f"Failed to go back: {e}"


async def go_forward(ctx: RunContext[AgentDeps]) -> str:
    """Go forward to the next page in browser history."""
    try:
        await ctx.deps.browser.page.go_forward(wait_until="domcontentloaded")
        return f"Went forward to {ctx.deps.browser.page.url}"
    except Exception as e:
        return f"Failed to go forward: {e}"
