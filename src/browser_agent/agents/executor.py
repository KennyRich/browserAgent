from pydantic_ai import Agent
from pydantic_ai.models import Model

from browser_agent.browser.session import BrowserSession
from browser_agent.tools import ALL_TOOLS

EXECUTOR_SYSTEM_PROMPT = """\
You are a browser executor. You receive a single instruction and carry it out \
using the available browser tools.

Rules:
- Use the tools to perform the requested action.
- Identify elements by their visible text, labels, placeholders, or ARIA roles.
- After performing an action, call get_page_state to confirm the result.
- If an element is not found, report the failure clearly.
- Do not guess or fabricate results.\
"""


def create_executor(model: Model, max_retries: int = 3) -> Agent[BrowserSession, str]:
    return Agent(
        model,
        tools=ALL_TOOLS,
        deps_type=BrowserSession,
        system_prompt=EXECUTOR_SYSTEM_PROMPT,
        retries=max_retries,
    )
