from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from browser_agent.browser.session import BrowserSession
    from browser_agent.memory import MemoryStore


@dataclass
class AgentDeps:
    browser: BrowserSession
    memory: MemoryStore


class BrowserCloseRequested(Exception):
    pass


class BrowserState(BaseModel):
    url: str
    title: str
    text_content: str
    interactive_elements: list[str]


class ParallelStep(BaseModel):
    tab_id: int
    instruction: str


class PlannerAction(BaseModel):
    instruction: str
    is_complete: bool
    final_answer: str | None = None
    reasoning: str
    parallel_instructions: list[ParallelStep] | None = None


class StepResult(BaseModel):
    success: bool
    message: str
    browser_state: BrowserState
