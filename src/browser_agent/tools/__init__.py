from browser_agent.tools.datetime import get_datetime
from browser_agent.tools.extraction import extract_links, extract_text, get_page_state
from browser_agent.tools.interaction import (
    click,
    scroll_down,
    scroll_up,
    select_option,
    type_text,
)
from browser_agent.tools.markdown import page_to_markdown
from browser_agent.tools.navigation import go_back, go_forward, navigate_to
from browser_agent.tools.screenshot import take_screenshot
from browser_agent.tools.tabs import close_tab, list_tabs, open_new_tab, switch_tab

ALL_TOOLS = [
    navigate_to,
    go_back,
    go_forward,
    click,
    type_text,
    select_option,
    scroll_down,
    scroll_up,
    extract_text,
    extract_links,
    get_page_state,
    page_to_markdown,
    take_screenshot,
    get_datetime,
    open_new_tab,
    switch_tab,
    close_tab,
    list_tabs,
]
