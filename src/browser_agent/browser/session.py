from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

from browser_agent.config import Settings
from browser_agent.models import BrowserState

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

async def _build_state(page: Page) -> BrowserState:
    url = page.url
    title = await page.title()

    try:
        text_content = await page.inner_text("body", timeout=5000)
    except Exception:
        text_content = ""

    try:
        elements = await page.evaluate("""
            () => {
                const items = [];
                document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [role="link"], [role="tab"]'
                ).forEach(el => {
                    const tag = el.tagName.toLowerCase();
                    const text = el.innerText?.trim() || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
                    const type = el.getAttribute('type') || '';
                    if (text || type) {
                        items.push(`[${tag}${type ? ':' + type : ''}] ${text}`.trim());
                    }
                });
                return items.slice(0, 50);
            }
        """)
    except Exception:
        elements = []

    return BrowserState(
        url=url,
        title=title,
        text_content=text_content,
        interactive_elements=elements,
    )


_stealth = Stealth()


class BrowserSession:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._tabs: dict[int, Page] = {}
        self._active_tab_id: int = 0
        self._next_tab_id: int = 0

    @property
    def page(self) -> Page:
        if not self._tabs:
            raise RuntimeError("Browser session not started. Use 'async with' context manager.")
        if self._active_tab_id not in self._tabs:
            raise RuntimeError(f"Active tab {self._active_tab_id} no longer exists.")
        return self._tabs[self._active_tab_id]

    @property
    def active_tab_id(self) -> int:
        return self._active_tab_id

    async def open_tab(self, url: str | None = None) -> int:
        if self._context is None:
            raise RuntimeError("Browser session not started.")
        page = await self._context.new_page()
        await _stealth.apply_stealth_async(page)
        tab_id = self._next_tab_id
        self._next_tab_id += 1
        self._tabs[tab_id] = page
        self._active_tab_id = tab_id
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return tab_id

    def switch_tab(self, tab_id: int) -> None:
        if tab_id not in self._tabs:
            raise ValueError(f"Tab {tab_id} does not exist. Open tabs: {list(self._tabs.keys())}")
        self._active_tab_id = tab_id

    async def close_tab(self, tab_id: int) -> None:
        if tab_id not in self._tabs:
            raise ValueError(f"Tab {tab_id} does not exist.")
        page = self._tabs.pop(tab_id)
        await page.close()
        if self._active_tab_id == tab_id:
            if self._tabs:
                self._active_tab_id = next(iter(self._tabs))
            else:
                fallback = await self._context.new_page()
                await _stealth.apply_stealth_async(fallback)
                new_id = self._next_tab_id
                self._next_tab_id += 1
                self._tabs[new_id] = fallback
                self._active_tab_id = new_id

    async def list_tabs(self) -> list[dict]:
        tabs = []
        for tab_id, page in self._tabs.items():
            try:
                title = await page.title()
            except Exception:
                title = ""
            tabs.append({
                "id": tab_id,
                "url": page.url,
                "title": title,
                "active": tab_id == self._active_tab_id,
            })
        return tabs

    def get_tab_page(self, tab_id: int) -> Page:
        if tab_id not in self._tabs:
            raise ValueError(f"Tab {tab_id} does not exist.")
        return self._tabs[tab_id]

    def tab_view(self, tab_id: int) -> "TabSession":
        return TabSession(self, tab_id)

    async def get_state(self) -> BrowserState:
        return await _build_state(self.page)

    async def __aenter__(self) -> "BrowserSession":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._settings.headless,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            viewport={
                "width": self._settings.viewport_width,
                "height": self._settings.viewport_height,
            },
        )
        page = await self._context.new_page()
        await _stealth.apply_stealth_async(page)
        self._tabs[0] = page
        self._active_tab_id = 0
        self._next_tab_id = 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


class TabSession:
    def __init__(self, session: BrowserSession, tab_id: int) -> None:
        self._session = session
        self._tab_id = tab_id

    @property
    def page(self) -> Page:
        return self._session.get_tab_page(self._tab_id)

    @property
    def active_tab_id(self) -> int:
        return self._session.active_tab_id

    async def get_state(self) -> BrowserState:
        return await _build_state(self.page)

    async def open_tab(self, url: str | None = None) -> int:
        return await self._session.open_tab(url)

    def switch_tab(self, tab_id: int) -> None:
        self._session.switch_tab(tab_id)

    async def close_tab(self, tab_id: int) -> None:
        await self._session.close_tab(tab_id)

    async def list_tabs(self) -> list[dict]:
        return await self._session.list_tabs()

    def get_tab_page(self, tab_id: int) -> Page:
        return self._session.get_tab_page(tab_id)

    def tab_view(self, tab_id: int) -> "TabSession":
        return self._session.tab_view(tab_id)
