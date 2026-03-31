from pydantic_ai import Agent
from pydantic_ai.models import Model

from browser_agent.models import BrowserState, PlannerAction, StepResult

PLANNER_SYSTEM_PROMPT = """\
You are a task planner. You do NOT have browser tools. You do NOT call tools directly. \
Your ONLY job is to return a JSON response describing what a separate browser executor should do next.

You respond using the final_result tool with these fields:
- instruction: a natural language instruction for the executor (e.g. "Navigate to https://news.ycombinator.com")
- is_complete: set to true ONLY when you have gathered enough information to answer the user
- final_answer: your answer to the user (only when is_complete is true)
- reasoning: explain why you chose this step
- parallel_instructions: optional list of {tab_id, instruction} for concurrent execution on multiple tabs

The executor has these capabilities (you write instructions for it, you do not call them):
navigate_to, click, type_text, select_option, scroll_up, scroll_down, \
extract_text, extract_links, get_page_state, page_to_markdown, \
take_screenshot, get_datetime, open_new_tab, switch_tab, close_tab, list_tabs, \
save_finding, recall_finding, search_memory, list_memories, delete_finding, close_browser, \
search_bing, search_duckduckgo, search_brave.

Rules:
- Write one instruction per step. Be specific and actionable.
- If the browser is on a blank page, instruct navigation to a relevant URL.
- If a previous step failed, try a different approach.
- Do NOT set is_complete=true until you have the actual information needed to answer.
- For multi-tab workflows, first instruct opening tabs, then use parallel_instructions.
- Use save_finding to store important results that may be useful in future tasks.
- Use recall_finding or search_memory to retrieve previously saved information.
- Reference previous conversation context when the user refers to earlier tasks.\
"""


def create_planner(model: Model, max_retries: int = 3) -> Agent[None, PlannerAction]:
    return Agent(
        model,
        output_type=PlannerAction,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        retries=max_retries,
    )


def format_planner_prompt(
    task: str,
    browser_state: BrowserState,
    recent_history: list[StepResult],
    conversation_context: str = "",
) -> str:
    parts = [f"Task: {task}"]

    if conversation_context:
        parts.append(f"\nPrevious conversation:\n{conversation_context}")

    parts.append(
        f"\nCurrent browser state (active tab):\n"
        f"  URL: {browser_state.url}\n"
        f"  Title: {browser_state.title}\n"
        f"  Page text: {browser_state.text_content}\n"
        f"  Interactive elements: {', '.join(browser_state.interactive_elements)}"
    )

    if recent_history:
        parts.append("\nRecent steps:")
        for i, step in enumerate(recent_history, 1):
            status = "OK" if step.success else "FAILED"
            parts.append(f"  {i}. [{status}] {step.message}")

    parts.append("\nWhat should the executor do next?")
    return "\n".join(parts)
