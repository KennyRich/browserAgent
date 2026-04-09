import asyncio
from datetime import datetime, timezone
from pathlib import Path

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
from browser_agent.memory import MemoryStore
from browser_agent.models import (
    AgentDeps,
    BrowserCloseRequested,
    BrowserState,
    ParallelStep,
    PlannerAction,
    StepResult,
)


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        planner: Agent[None, PlannerAction],
        executor: Agent[AgentDeps, str],
        display: Display,
        memory: MemoryStore,
        model=None,
    ) -> None:
        self._settings = settings
        self._planner = planner
        self._executor = executor
        self._display = display
        self._memory = memory
        self._model = model

    def _init_run_log(self, task: str) -> Path | None:
        if not self._settings.log_experiments:
            return None
        log_dir = Path("experiment_logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"{self._settings.model_name.replace(':', '_')}_{timestamp}.md"
        log_path.write_text(
            f"# Run Log\n\n"
            f"- **Model:** `{self._settings.model_name}`\n"
            f"- **Task:** {task}\n"
            f"- **Time:** {datetime.now(timezone.utc).isoformat()}\n\n"
            f"---\n\n"
        )
        return log_path

    def _log_step(self, log_path: Path | None, step: int, action: PlannerAction, result: StepResult | list[StepResult] | None = None) -> None:
        if log_path is None:
            return
        lines = [f"## Step {step}\n"]
        lines.append(f"### Reasoning\n\n{action.reasoning}\n")

        if action.is_complete:
            lines.append(f"### Final Answer\n\n{action.final_answer}\n")
        elif action.parallel_instructions:
            lines.append("### Parallel Instructions\n")
            for p in action.parallel_instructions:
                lines.append(f"- **Tab {p.tab_id}:** {p.instruction}")
            lines.append("")
        else:
            lines.append(f"### Instruction\n\n{action.instruction}\n")

        if result is not None:
            results = result if isinstance(result, list) else [result]
            lines.append("### Result\n")
            for r in results:
                status = "Success" if r.success else "Failure"
                lines.append(f"- **{status}:** {r.message}")
            lines.append("")

        lines.append("---\n\n")
        with open(log_path, "a") as f:
            f.write("\n".join(lines))

    async def run_task(self, task: str, session: BrowserSession) -> tuple[str, int]:
        if await self._memory.total_length() > self._settings.max_memory_length:
            if self._model:
                with self._display.console.status("  Summarizing memory...", spinner="dots"):
                    await self._memory.summarize(self._model)

        history: list[StepResult] = []
        conversation_context = await self._memory.format_context()
        deps = AgentDeps(browser=session, memory=self._memory, display=self._display, settings=self._settings)
        log_path = self._init_run_log(task)

        for step in range(1, self._settings.max_steps + 1):
            browser_state = await self._get_truncated_state(session)
            recent = history[-3:]
            prompt = format_planner_prompt(task, browser_state, recent, conversation_context)

            self._display.show_step_header(step, self._settings.max_steps)
            action = await self._stream_planner(prompt)

            if action.is_complete:
                self._display.show_planner_result(action.reasoning, "Task complete")
                self._log_step(log_path, step, action)
                answer = action.final_answer or "Task completed."
                await self._memory.add_conversation(task, answer, step)
                return answer, step

            if action.parallel_instructions:
                self._display.show_planner_result(action.reasoning, "parallel execution")
                self._display.show_parallel_instructions(action.parallel_instructions)
                results = await self._execute_parallel(action.parallel_instructions, session, deps)
                for result in results:
                    self._display.show_step_result(result.success, result.message)
                self._log_step(log_path, step, action, results)
                history.extend(results)
            else:
                self._display.show_planner_result(action.reasoning, action.instruction)
                result = await self._stream_executor(action.instruction, deps)
                self._display.show_step_result(result.success, result.message)
                self._log_step(log_path, step, action, result)
                history.append(result)

        answer = "Max steps reached without completing the task."
        await self._memory.add_conversation(task, answer, self._settings.max_steps)
        return answer, self._settings.max_steps

    async def _stream_planner(self, prompt: str) -> PlannerAction:
        with self._display.console.status("  Planning...", spinner="dots"):
            result = await self._planner.run(prompt)
        return result.output

    async def _stream_executor(self, instruction: str, deps: AgentDeps) -> StepResult:
        try:
            final_output = ""
            async for event in self._executor.run_stream_events(
                instruction, deps=deps
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

            browser_state = await self._get_truncated_state(deps.browser)
            return StepResult(
                success=True,
                message=final_output,
                browser_state=browser_state,
            )
        except BrowserCloseRequested:
            raise
        except Exception as e:
            browser_state = await self._get_truncated_state(deps.browser)
            return StepResult(
                success=False,
                message=str(e),
                browser_state=browser_state,
            )

    async def _execute_parallel(
        self, steps: list[ParallelStep], session: BrowserSession, deps: AgentDeps
    ) -> list[StepResult]:
        existing_tabs = {tab["id"] for tab in await session.list_tabs()}
        for step in steps:
            if step.tab_id not in existing_tabs:
                await session.open_tab()

        semaphore = asyncio.Semaphore(self._settings.max_concurrent)

        async def run_with_limit(step: ParallelStep) -> StepResult:
            async with semaphore:
                tab_session = session.tab_view(step.tab_id)
                tab_deps = AgentDeps(browser=tab_session, memory=deps.memory, display=deps.display, settings=deps.settings)
                return await self._stream_executor(step.instruction, tab_deps)

        return await asyncio.gather(*[run_with_limit(s) for s in steps])

    async def _get_truncated_state(self, session) -> BrowserState:
        state = await session.get_state()
        state.text_content = state.text_content[: self._settings.max_text_length]
        return state
