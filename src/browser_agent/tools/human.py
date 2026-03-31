from pydantic_ai import RunContext

from browser_agent.models import AgentDeps

FORM_FIELD_DISCOVERY_JS = """
() => {
    const fields = [];
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (el.offsetParent === null) return;
        if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button') return;
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


async def ask_human(
    ctx: RunContext[AgentDeps],
    question: str,
    options: list[str] | None = None,
) -> str:
    """Ask the human user a question and return their answer. Use when you need clarification, a decision, or information only the user can provide.

    Args:
        question: The question to ask the user.
        options: Optional list of choices for the user to pick from. If provided, shows interactive selection with arrow keys. User can also type a custom answer.
    """
    display = ctx.deps.display
    if options:
        return display.prompt_human_choice(question, options)
    return display.prompt_human(question)


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

        value = display.prompt_form_field(i, len(fields), label, field_type)
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
                await locator.first.select_option(value, timeout=5000)
            else:
                locator = page.get_by_label(label).or_(
                    page.get_by_placeholder(placeholder) if placeholder else page.get_by_label(label)
                ).or_(
                    page.locator(f'input[name="{name}"]') if name else page.get_by_label(label)
                )
                await locator.first.fill(value, timeout=5000)

            safe_label = label.replace("password", "Password").replace("Password", "Password")
            filled_labels.append(safe_label)
        except Exception as e:
            filled_labels.append(f"{label} (failed: {e})")

    display.show_form_complete(filled_labels)

    summary_parts = []
    for i, field in enumerate(fields):
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

    ctx.deps.display.prompt_wait(instruction)

    state = await ctx.deps.browser.get_state()
    return f"Human completed action. Page is now at: {state.url} - {state.title}"
