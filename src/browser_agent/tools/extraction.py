from pydantic_ai import RunContext

from browser_agent.models import AgentDeps


async def extract_text(
    ctx: RunContext[AgentDeps], selector_description: str | None = None
) -> str:
    """Extract text content from the page or a specific element.

    Args:
        selector_description: Optional visible text or label to target a specific element. If None, extracts the full page text.
    """
    page = ctx.deps.browser.page
    try:
        if selector_description:
            locator = page.get_by_text(selector_description, exact=False)
            text = await locator.first.inner_text(timeout=5000)
        else:
            text = await page.inner_text("body", timeout=5000)
        return text.strip()
    except Exception as e:
        return f"Failed to extract text: {e}"


async def extract_links(ctx: RunContext[AgentDeps]) -> str:
    """Extract all links from the current page with their text and URLs."""
    page = ctx.deps.browser.page
    try:
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .slice(0, 50)
                .map(a => `${a.innerText.trim()} -> ${a.href}`)
                .filter(s => s.length > 5)
        """)
        return "\n".join(links) if links else "No links found on the page."
    except Exception as e:
        return f"Failed to extract links: {e}"


async def get_page_state(ctx: RunContext[AgentDeps]) -> str:
    """Get the current browser page state including URL, title, visible text, and interactive elements."""
    state = await ctx.deps.browser.get_state()
    return (
        f"URL: {state.url}\n"
        f"Title: {state.title}\n"
        f"Text: {state.text_content[:2000]}\n"
        f"Interactive elements: {', '.join(state.interactive_elements)}"
    )
