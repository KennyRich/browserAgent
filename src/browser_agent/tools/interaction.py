from pydantic_ai import RunContext

from browser_agent.models import AgentDeps


async def click(ctx: RunContext[AgentDeps], description: str) -> str:
    """Click on a page element matching the given description.

    Args:
        description: Visible text, label, or ARIA role of the element to click.
    """
    page = ctx.deps.browser.page
    try:
        locator = page.get_by_role("link", name=description).or_(
            page.get_by_role("button", name=description)
        ).or_(
            page.get_by_text(description, exact=False)
        )
        await locator.first.click(timeout=5000)
        return f"Clicked on '{description}'"
    except Exception as e:
        return f"Failed to click '{description}': {e}"


async def type_text(
    ctx: RunContext[AgentDeps], selector_description: str, text: str
) -> str:
    """Type text into an input field matching the given description.

    Args:
        selector_description: Visible label, placeholder, or ARIA role of the input.
        text: The text to type into the field.
    """
    page = ctx.deps.browser.page
    try:
        locator = page.get_by_role("textbox", name=selector_description).or_(
            page.get_by_placeholder(selector_description)
        ).or_(
            page.get_by_label(selector_description)
        )
        await locator.first.fill(text, timeout=5000)
        return f"Typed '{text}' into '{selector_description}'"
    except Exception as e:
        return f"Failed to type into '{selector_description}': {e}"


async def select_option(
    ctx: RunContext[AgentDeps], selector_description: str, value: str
) -> str:
    """Select an option from a dropdown matching the given description.

    Args:
        selector_description: Visible label or ARIA role of the dropdown.
        value: The option value or visible text to select.
    """
    page = ctx.deps.browser.page
    try:
        locator = page.get_by_role("combobox", name=selector_description).or_(
            page.get_by_label(selector_description)
        )
        await locator.first.select_option(value, timeout=5000)
        return f"Selected '{value}' in '{selector_description}'"
    except Exception as e:
        return f"Failed to select '{value}' in '{selector_description}': {e}"


async def scroll_down(ctx: RunContext[AgentDeps]) -> str:
    """Scroll the page down by one viewport height."""
    try:
        await ctx.deps.browser.page.evaluate("window.scrollBy(0, window.innerHeight)")
        return "Scrolled down"
    except Exception as e:
        return f"Failed to scroll down: {e}"


async def scroll_up(ctx: RunContext[AgentDeps]) -> str:
    """Scroll the page up by one viewport height."""
    try:
        await ctx.deps.browser.page.evaluate("window.scrollBy(0, -window.innerHeight)")
        return "Scrolled up"
    except Exception as e:
        return f"Failed to scroll up: {e}"
