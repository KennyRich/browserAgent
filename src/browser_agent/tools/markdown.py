from markdownify import markdownify
from pydantic_ai import RunContext

from browser_agent.browser.session import BrowserSession

STRIP_TAGS = [
    "nav", "script", "style", "footer", "aside",
    "svg", "noscript", "iframe", "form", "header",
]


async def page_to_markdown(ctx: RunContext[BrowserSession]) -> str:
    """Convert the current page content to clean, readable markdown.

    Strips navigation, scripts, ads, and other non-content elements.
    Useful for research tasks where you need to read and understand page content.
    """
    page = ctx.deps.page
    try:
        html = await page.content()
        md = markdownify(html, strip=STRIP_TAGS).strip()
        lines = [line for line in md.splitlines() if line.strip()]
        return "\n".join(lines)[:8000]
    except Exception as e:
        return f"Failed to convert page to markdown: {e}"
