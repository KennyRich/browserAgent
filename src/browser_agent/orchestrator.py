import asyncio

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
)

from browser_agent.agents.planner import format_planner_prompt
from browser_agent.browser.session import BrowserSession
from browser_agent.config import Settings
from browser_agent.display import Display
from browser_agent.models import BrowserState, ParallelStep, PlannerAction, StepResult


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        planner: Agent[None, PlannerAction],
        executor: Agent[BrowserSession, str],
        display: Display,
    ) -> None:
        self._settings = settings
        self._planner = planner
        self._executor = executor
        self._display = display

    async def run_task(self, task: str, session: BrowserSession) -> tuple[str, int]:
        history: list[StepResult] = []

        for step in range(1, self._settings.max_steps + 1):
            browser_state = await self._get_truncated_state(session)
            recent = history[-3:]
            prompt = format_planner_prompt(task, browser_state, recent)

            self._display.show_step_header(step, self._settings.max_steps)
            action = await self._stream_planner(prompt)

            if action.is_complete:
                self._display.show_planner_result(action.reasoning, "Task complete")
                return action.final_answer or "Task completed.", step

            if action.parallel_instructions:
                self._display.show_planner_result(action.reasoning, "parallel execution")
                self._display.show_parallel_instructions(action.parallel_instructions)
                results = await self._execute_parallel(action.parallel_instructions, session)
                for result in results:
                    self._display.show_step_result(result.success, result.message)
                history.extend(results)
            else:
                self._display.show_planner_result(action.reasoning, action.instruction)
                result = await self._stream_executor(action.instruction, session)
                self._display.show_step_result(result.success, result.message)
                history.append(result)

        return "Max steps reached without completing the task.", self._settings.max_steps

    async def _stream_planner(self, prompt: str) -> PlannerAction:
        with self._display.console.status("  Planning...", spinner="dots"):
            result = await self._planner.run(prompt)
        return result.output

    async def _stream_executor(
        self, instruction: str, session
    ) -> StepResult:
        try:
            final_output = ""
            async for event in self._executor.run_stream_events(
                instruction, deps=session
            ):
                if isinstance(event, FunctionToolCallEvent):
                    self._display.show_tool_call(
                        event.part.tool_name, str(event.part.args)
                    )
                elif isinstance(event, FunctionToolResultEvent):
                    content = str(event.result.content)
                    self._display.show_tool_result(content)
                elif isinstance(event, PartDeltaEvent):
                    if hasattr(event.delta, "content_delta"):
                        self._display.stream_token(event.delta.content_delta)
                elif isinstance(event, AgentRunResultEvent):
                    final_output = event.result.output

            browser_state = await self._get_truncated_state(session)
            return StepResult(
                success=True,
                message=final_output,
                browser_state=browser_state,
            )
        except Exception as e:
            browser_state = await self._get_truncated_state(session)
            return StepResult(
                success=False,
                message=str(e),
                browser_state=browser_state,
            )

    async def _execute_parallel(
        self, steps: list[ParallelStep], session: BrowserSession
    ) -> list[StepResult]:
        existing_tabs = {tab["id"] for tab in await session.list_tabs()}
        for step in steps:
            if step.tab_id not in existing_tabs:
                await session.open_tab()

        semaphore = asyncio.Semaphore(self._settings.max_concurrent)

        async def run_with_limit(step: ParallelStep) -> StepResult:
            async with semaphore:
                tab_session = session.tab_view(step.tab_id)
                return await self._stream_executor(step.instruction, tab_session)

        return await asyncio.gather(*[run_with_limit(s) for s in steps])

    async def _get_truncated_state(self, session) -> BrowserState:
        state = await session.get_state()
        state.text_content = state.text_content[: self._settings.max_text_length]
        return state
