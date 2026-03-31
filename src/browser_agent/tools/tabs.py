from pydantic_ai import RunContext

from browser_agent.browser.session import BrowserSession


async def open_new_tab(ctx: RunContext[BrowserSession], url: str | None = None) -> str:
    """Open a new browser tab, optionally navigating to a URL. The new tab becomes the active tab.

    Args:
        url: Optional URL to navigate to in the new tab.
    """
    try:
        tab_id = await ctx.deps.open_tab(url)
        location = f" at {url}" if url else ""
        return f"Opened new tab {tab_id}{location}. This is now the active tab."
    except Exception as e:
        return f"Failed to open new tab: {e}"


async def switch_tab(ctx: RunContext[BrowserSession], tab_id: int) -> str:
    """Switch the active browser tab to the specified tab ID.

    Args:
        tab_id: The integer ID of the tab to switch to.
    """
    try:
        ctx.deps.switch_tab(tab_id)
        page = ctx.deps.page
        return f"Switched to tab {tab_id} ({page.url})"
    except Exception as e:
        return f"Failed to switch to tab {tab_id}: {e}"


async def close_tab(ctx: RunContext[BrowserSession], tab_id: int) -> str:
    """Close a browser tab by its ID. If it was the active tab, another tab becomes active.

    Args:
        tab_id: The integer ID of the tab to close.
    """
    try:
        await ctx.deps.close_tab(tab_id)
        return f"Closed tab {tab_id}. Active tab is now {ctx.deps.active_tab_id}."
    except Exception as e:
        return f"Failed to close tab {tab_id}: {e}"


async def list_tabs(ctx: RunContext[BrowserSession]) -> str:
    """List all open browser tabs with their IDs, URLs, and titles."""
    try:
        tabs = await ctx.deps.list_tabs()
        lines = []
        for tab in tabs:
            marker = " (active)" if tab["active"] else ""
            lines.append(f"  Tab {tab['id']}: {tab['title']} - {tab['url']}{marker}")
        return "\n".join(lines) if lines else "No tabs open."
    except Exception as e:
        return f"Failed to list tabs: {e}"
