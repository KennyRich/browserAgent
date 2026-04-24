"""Intent-based element tools: smart_find, smart_click, smart_fill."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic_ai import RunContext

from browser_agent.models import AgentDeps
from browser_agent.smart_locator import PageIndex

_model_cache: Any = None


def _get_embedding_model() -> Any:
    global _model_cache
    if _model_cache is None:
        from sentence_transformers import SentenceTransformer
        _model_cache = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _model_cache


async def _get_index(ctx: RunContext[AgentDeps]) -> PageIndex:
    page = ctx.deps.browser.page
    index = ctx.deps.page_index
    if index is not None and index.url == page.url:
        return index
    model = _get_embedding_model()
    index = PageIndex()
    await index.build(page, model)
    ctx.deps.page_index = index
    return index


async def _resolve_and_act(
    ctx: RunContext[AgentDeps],
    intent: str,
    action: str,
    text: str | None = None,
) -> str:
    for attempt in (1, 2):
        try:
            index = await _get_index(ctx)
            model = _get_embedding_model()
            candidates = index.search(intent, model, top_k=5)
            if not candidates:
                if attempt == 1:
                    ctx.deps.page_index = None
                    await asyncio.sleep(0.3)
                    continue
                return f"No elements found for intent: '{intent}'"

            el, score = candidates[0]
            page = ctx.deps.browser.page

            loc = page.get_by_role(el.role, name=el.name, exact=True)
            try:
                count = await loc.count()
            except Exception:
                count = 0

            if count > 1 and el.nearest_heading:
                scoped = page.get_by_role(
                    "region", name=el.nearest_heading
                ).get_by_role(el.role, name=el.name, exact=True)
                try:
                    if await scoped.count() == 1:
                        loc = scoped
                except Exception:
                    pass

            if count == 0:
                loc = page.get_by_text(el.name, exact=True).first
            else:
                loc = loc.first

            if action == "click":
                await loc.click()
                return (
                    f"Clicked [{el.to_text()}] (score: {score:.2f})"
                )
            elif action == "fill":
                try:
                    await loc.fill(text)
                except Exception:
                    await loc.click()
                    await page.keyboard.press("Control+a")
                    await page.keyboard.type(text, delay=20)
                return (
                    f"Typed '{text}' into [{el.to_text()}] (score: {score:.2f})"
                )
        except Exception as exc:
            if attempt == 2:
                index = await _get_index(ctx)
                model = _get_embedding_model()
                candidates = index.search(intent, model, top_k=3)
                candidate_text = "\n".join(
                    f"  [{s:.2f}] {e.to_text()}" for e, s in candidates
                ) if candidates else "  (none)"
                return (
                    f"Failed to {action} '{intent}': {exc}\n"
                    f"Top candidates:\n{candidate_text}"
                )
            ctx.deps.page_index = None
            await asyncio.sleep(0.3)

    return f"Failed to {action} '{intent}': exhausted retries"


async def smart_find(
    ctx: RunContext[AgentDeps], intent: str, top_k: int = 5
) -> str:
    """Find elements by natural language intent. Returns ranked matches with
    scores, roles, names, and semantic context. Use this to inspect the page
    before acting, especially when element text is ambiguous.

    Args:
        intent: Natural language description of what to find (e.g., "the login button",
                "email input field", "checkout link").
        top_k: Maximum number of candidates to return (default 5).
    """
    if not ctx.deps.settings.use_smart_locator:
        return "Smart locator is disabled. Use find_elements() instead."

    try:
        _get_embedding_model()
    except ImportError:
        return "Missing dependencies. Install with: uv pip install '.[smart]'"

    index = await _get_index(ctx)
    model = _get_embedding_model()
    candidates = index.search(intent, model, top_k=top_k)

    if not candidates:
        return f"No elements found for intent: '{intent}'"

    lines = [f'"{intent}": {len(candidates)} candidate(s)']
    for el, score in candidates:
        lines.append(f"  [{score:.2f}] {el.to_text()}")
    return "\n".join(lines)


async def smart_click(ctx: RunContext[AgentDeps], intent: str) -> str:
    """Find an element by natural language intent and click it. Self-heals on
    failure by re-indexing the page and retrying once.

    Args:
        intent: Natural language description of what to click (e.g., "the sign up button",
                "checkout link", "close dialog button").
    """
    if not ctx.deps.settings.use_smart_locator:
        return "Smart locator is disabled. Use click() instead."

    try:
        _get_embedding_model()
    except ImportError:
        return "Missing dependencies. Install with: uv pip install '.[smart]'"

    return await _resolve_and_act(ctx, intent, "click")


async def smart_fill(
    ctx: RunContext[AgentDeps], intent: str, text: str
) -> str:
    """Find an input element by natural language intent and type text into it.
    Works with standard inputs, textareas, and contenteditable elements.
    Self-heals on failure by re-indexing the page and retrying once.

    Args:
        intent: Natural language description of the input (e.g., "the email field",
                "search box", "message body").
        text: The text to type into the field.
    """
    if not ctx.deps.settings.use_smart_locator:
        return "Smart locator is disabled. Use type_text() instead."

    try:
        _get_embedding_model()
    except ImportError:
        return "Missing dependencies. Install with: uv pip install '.[smart]'"

    return await _resolve_and_act(ctx, intent, "fill", text)
