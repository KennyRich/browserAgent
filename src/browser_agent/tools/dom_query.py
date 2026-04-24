from pydantic_ai import RunContext

from browser_agent.models import AgentDeps

JS_FIND_ELEMENTS = """
({queries, mode, role, limit}) => {
    const results = {};

    function isVisible(el) {
        if (el.offsetParent === null && getComputedStyle(el).position !== 'fixed') return false;
        if (el.getAttribute('aria-hidden') === 'true') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    function implicitRole(el) {
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute('type') || '').toLowerCase();
        if (tag === 'a' && el.hasAttribute('href')) return 'link';
        if (tag === 'button') return 'button';
        if (tag === 'input' && (type === 'submit' || type === 'button')) return 'button';
        if (tag === 'input' && ['text','email','password','search','tel','url','number',''].includes(type)) return 'textbox';
        if (tag === 'input' && type === 'checkbox') return 'checkbox';
        if (tag === 'input' && type === 'radio') return 'radio';
        if (tag === 'textarea') return 'textbox';
        if (tag === 'select') return 'combobox';
        if (['h1','h2','h3','h4','h5','h6'].includes(tag)) return 'heading';
        return '';
    }

    function describeElement(el) {
        const tag = el.tagName.toLowerCase();
        const text = (el.innerText || el.textContent || '').trim().slice(0, 80);
        const ariaRole = el.getAttribute('role') || implicitRole(el);
        const ariaLabel = el.getAttribute('aria-label') || '';
        const placeholder = el.getAttribute('placeholder') || '';
        const elTitle = el.getAttribute('title') || '';
        const type = el.getAttribute('type') || '';
        const name = el.getAttribute('name') || '';
        const id = el.id || '';

        let suggestedLocator = '';
        if (ariaRole && (ariaLabel || text)) {
            suggestedLocator = 'use "' + (ariaLabel || text) + '" with ' +
                (ariaRole === 'link' || ariaRole === 'button' ? 'click()' :
                 ariaRole === 'textbox' ? 'type_text()' :
                 ariaRole === 'combobox' ? 'select_option()' : 'click()');
        } else if (ariaLabel) {
            suggestedLocator = 'use "' + ariaLabel + '" with type_text()';
        } else if (placeholder) {
            suggestedLocator = 'use "' + placeholder + '" with type_text()';
        } else if (text) {
            suggestedLocator = 'use "' + text + '" with click()';
        }

        const info = {tag, text};
        if (ariaRole) info.role = ariaRole;
        if (ariaLabel) info.aria_label = ariaLabel;
        if (placeholder) info.placeholder = placeholder;
        if (elTitle) info.title = elTitle;
        if (type) info.type = type;
        if (name) info.name = name;
        if (id) info.id = id;
        if (suggestedLocator) info.suggested_locator = suggestedLocator;

        return info;
    }

    let candidates;
    if (role) {
        const roleMap = {
            button: 'button, input[type="submit"], input[type="button"], [role="button"]',
            link: 'a[href], [role="link"]',
            textbox: 'input:not([type]), input[type="text"], input[type="email"], input[type="password"], input[type="search"], input[type="tel"], input[type="url"], input[type="number"], textarea, [role="textbox"]',
            combobox: 'select, [role="combobox"]',
            checkbox: 'input[type="checkbox"], [role="checkbox"]',
            radio: 'input[type="radio"], [role="radio"]',
            tab: '[role="tab"]',
            heading: 'h1, h2, h3, h4, h5, h6, [role="heading"]',
        };
        const selector = roleMap[role] || `[role="${role}"]`;
        candidates = Array.from(document.querySelectorAll(selector));
    } else {
        candidates = Array.from(document.querySelectorAll(
            'a, button, input, select, textarea, [role], [aria-label], label, h1, h2, h3, h4, h5, h6, p, span, div, li, td, th, summary'
        ));
    }

    candidates = candidates.filter(el => isVisible(el));

    for (const query of queries) {
        const matches = [];
        const q = query.toLowerCase().trim();

        if (mode === 'css') {
            try {
                const els = Array.from(document.querySelectorAll(query)).filter(el => isVisible(el));
                for (const el of els.slice(0, limit)) {
                    matches.push(describeElement(el));
                }
            } catch(e) {
                matches.push({error: 'Invalid CSS selector: ' + e.message});
            }
        } else {
            for (const el of candidates) {
                if (matches.length >= limit) break;

                const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
                const title = (el.getAttribute('title') || '').toLowerCase();
                const value = (el.getAttribute('value') || '').toLowerCase();

                let matched = false;

                if (mode === 'auto' || mode === 'text') {
                    if (text.includes(q) || value.includes(q)) matched = true;
                }
                if (!matched && (mode === 'auto' || mode === 'label')) {
                    if (ariaLabel.includes(q)) matched = true;
                }
                if (!matched && (mode === 'auto' || mode === 'placeholder')) {
                    if (placeholder.includes(q)) matched = true;
                }
                if (!matched && mode === 'auto') {
                    if (title.includes(q)) matched = true;
                    if (!matched && (q.includes('.') || q.includes('#') || q.includes('['))) {
                        try { matched = el.matches(query); } catch(e) {}
                    }
                }

                if (matched) {
                    matches.push(describeElement(el));
                }
            }
        }

        results[query] = {count: matches.length, matches: matches};
    }

    return results;
}
"""


async def find_elements(
    ctx: RunContext[AgentDeps],
    queries: list[str],
    mode: str = "auto",
    role: str | None = None,
    limit: int = 5,
) -> str:
    """Find elements on the page matching candidate descriptions.

    Call BEFORE click/type_text to verify which locators exist and get exact
    text for reliable interaction. Returns matches with suggested locator text.

    Args:
        queries: List of candidate text, labels, placeholders, or CSS selectors to search for.
        mode: Search mode - "auto" (try all), "text" (visible text), "css" (CSS selector),
              "label" (aria-label), "placeholder" (placeholder attr).
        role: Optional ARIA role filter ("button", "link", "textbox", "combobox")
              to only search elements with that role.
        limit: Max matches per query (default 5).
    """
    page = ctx.deps.browser.page
    try:
        raw = await page.evaluate(
            JS_FIND_ELEMENTS,
            {"queries": queries, "mode": mode, "role": role, "limit": limit},
        )

        lines = []
        for query, data in raw.items():
            count = data["count"]
            if count == 0:
                lines.append(f'"{query}": no matches')
            else:
                lines.append(f'"{query}": {count} match(es)')
                for m in data["matches"]:
                    if "error" in m:
                        lines.append(f"  ERROR: {m['error']}")
                        continue
                    parts = [f"  <{m['tag']}>"]
                    if m.get("role"):
                        parts.append(f'role="{m["role"]}"')
                    if m.get("text"):
                        parts.append(f'text="{m["text"]}"')
                    if m.get("aria_label"):
                        parts.append(f'aria-label="{m["aria_label"]}"')
                    if m.get("placeholder"):
                        parts.append(f'placeholder="{m["placeholder"]}"')
                    if m.get("title"):
                        parts.append(f'title="{m["title"]}"')
                    if m.get("type"):
                        parts.append(f'type="{m["type"]}"')
                    if m.get("name"):
                        parts.append(f'name="{m["name"]}"')
                    if m.get("id"):
                        parts.append(f'id="{m["id"]}"')
                    if m.get("suggested_locator"):
                        parts.append(f'-> {m["suggested_locator"]}')
                    lines.append(" ".join(parts))
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to query DOM: {e}"
