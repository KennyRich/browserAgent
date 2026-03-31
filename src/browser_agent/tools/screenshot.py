from pathlib import Path

from pydantic_ai import RunContext

from browser_agent.browser.session import BrowserSession


async def take_screenshot(
    ctx: RunContext[BrowserSession], path: str | None = None
) -> str:
    """Take a screenshot of the current page and save it to a file. For human debugging only.

    Args:
        path: Optional file path to save the screenshot. Defaults to 'screenshot.png'.
    """
    save_path = Path(path) if path else Path("screenshot.png")
    try:
        await ctx.deps.page.screenshot(path=save_path)
        return f"Screenshot saved to {save_path}"
    except Exception as e:
        return f"Failed to take screenshot: {e}"
