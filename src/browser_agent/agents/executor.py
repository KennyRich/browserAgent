from pydantic_ai import Agent
from pydantic_ai.models import Model

from browser_agent.models import AgentDeps
from browser_agent.tools import ALL_TOOLS

EXECUTOR_SYSTEM_PROMPT = """\
You are a browser executor. You receive a single instruction and carry it out \
using the available browser tools.

Rules:
- Use the tools to perform the requested action.
- Identify elements by their visible text, labels, placeholders, or ARIA roles.
- After performing an action, call get_page_state to confirm the result.
- If an element is not found, report the failure clearly.
- Do not guess or fabricate results.
- Use save_finding to store important facts, data, or results that may be useful in future tasks.
- Use recall_finding or search_memory to retrieve previously saved information.\
"""


def create_executor(model: Model, max_retries: int = 3) -> Agent[AgentDeps, str]:
    return Agent(
        model,
        tools=ALL_TOOLS,
        deps_type=AgentDeps,
        system_prompt=EXECUTOR_SYSTEM_PROMPT,
        retries=max_retries,
    )
