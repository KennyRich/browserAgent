import asyncio

from pydantic_ai import RunContext

from browser_agent.models import AgentDeps

FORM_FIELD_DISCOVERY_JS = """
() => {
    const fields = [];
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (el.offsetParent === null) return;
        if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button' || el.type === 'checkbox') return;
        const label = (
            el.labels?.[0]?.innerText?.trim() ||
            el.getAttribute('aria-label') ||
            el.getAttribute('placeholder') ||
            el.getAttribute('name') ||
            el.type ||
            'Unknown field'
        );
        fields.push({
            label: label,
            type: el.type || el.tagName.toLowerCase(),
            name: el.getAttribute('name') || '',
            placeholder: el.getAttribute('placeholder') || '',
            tag: el.tagName.toLowerCase()
        });
    });
    return fields;
}
"""


async def _wait_for_input(ctx: RunContext[AgentDeps]) -> str:
    if ctx.deps.input_queue is None:
        return ""
    result = await ctx.deps.input_queue.get()
    if result == "__INTERRUPT__":
        raise asyncio.CancelledError("User interrupted")
    return result


async def ask_human(
    ctx: RunContext[AgentDeps],
    question: str,
    options: list[str] | None = None,
) -> str:
    """Ask the human user a question and return their answer. Use when you need clarification, a decision, or information only the user can provide.

    Args:
        question: The question to ask the user.
        options: Optional list of choices for the user to pick from.
    """
    display = ctx.deps.display

    if options:
        display.prompt_human_choice(question, options)
        answer = await display.show_choices(options)
        display.show_user_guidance(f"Selected: {answer}")
        display.reset_input_mode()
        display.set_status_text("Working...", "cyan")
        return answer

    display.prompt_human(question)
    answer = await _wait_for_input(ctx)
    display.show_user_guidance(f"User answered: {answer}")
    display.reset_input_mode()
    display.set_status_text("Working...", "cyan")
    return answer


async def fill_form_with_human(ctx: RunContext[AgentDeps]) -> str:
    """Detect all form fields on the current page and prompt the user to fill each one. Use for login forms, registration forms, or any form requiring user credentials or personal data."""
    page = ctx.deps.browser.page
    display = ctx.deps.display

    try:
        fields = await page.evaluate(FORM_FIELD_DISCOVERY_JS)
    except Exception as e:
        return f"Failed to detect form fields: {e}"

    if not fields:
        return "No visible form fields found on the page."

    display.show_form_header(len(fields))

    filled_labels = []
    for i, field in enumerate(fields, 1):
        label = field["label"]
        field_type = field["type"]

        display.prompt_form_field(i, len(fields), label, field_type)
        value = await _wait_for_input(ctx)

        if field_type == "password":
            display.show_user_guidance("********")
        else:
            display.show_user_guidance(value)

        if not value:
            continue

        try:
            name = field["name"]
            placeholder = field["placeholder"]
            tag = field["tag"]

            if tag == "select":
                locator = page.get_by_label(label).or_(
                    page.locator(f'select[name="{name}"]') if name else page.get_by_label(label)
                )
                await locator.first.select_option(value, timeout=10000)
            else:
                locator = page.get_by_label(label).or_(
                    page.get_by_placeholder(placeholder) if placeholder else page.get_by_label(label)
                ).or_(
                    page.locator(f'input[name="{name}"]') if name else page.get_by_label(label)
                )
                await locator.first.fill(value, timeout=10000)

            filled_labels.append(label)
        except Exception as e:
            if field_type == "password":
                filled_labels.append(f"{label} (failed to fill)")
            else:
                filled_labels.append(f"{label} (failed: {e})")

    display.show_form_complete(filled_labels)

    summary_parts = []
    for field in fields:
        label = field["label"]
        if field["type"] == "password":
            summary_parts.append(f"{label}: ********")
        else:
            summary_parts.append(f"{label}: [filled]")

    return f"Filled {len(filled_labels)} fields: {', '.join(filled_labels)}. Values: {'; '.join(summary_parts)}"


async def wait_for_human(ctx: RunContext[AgentDeps], instruction: str) -> str:
    """Pause execution and ask the user to perform an action manually in the browser window (e.g. solve CAPTCHA, complete 2FA, drag-and-drop). Only works in headed mode (browser visible).

    Args:
        instruction: What the user needs to do in the browser.
    """
    if ctx.deps.settings.headless:
        return "Cannot wait for human action in headless mode. The browser window is not visible."

    display = ctx.deps.display
    display.prompt_wait(instruction)
    await _wait_for_input(ctx)

    display.reset_input_mode()
    display.set_status_text("Working...", "cyan")

    state = await ctx.deps.browser.get_state()
    return f"Human completed action. Page is now at: {state.url} - {state.title}"
