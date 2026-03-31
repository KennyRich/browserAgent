from pydantic_ai import RunContext

from browser_agent.models import AgentDeps, BrowserCloseRequested


async def close_browser(ctx: RunContext[AgentDeps]) -> str:
    """Close the browser and end the session. Use only when the user explicitly asks to close or stop the browser."""
    raise BrowserCloseRequested("User requested browser close.")
