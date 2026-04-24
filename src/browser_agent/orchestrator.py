import asyncio
import time
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
from browser_agent.session_logger import SessionLogger


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        planner: Agent[None, PlannerAction],
        executor: Agent[AgentDeps, str],
        display: Display,
        memory: MemoryStore,
        model=None,
        input_queue: asyncio.Queue | None = None,
        logger: SessionLogger | None = None,
    ) -> None:
        self._settings = settings
        self._planner = planner
        self._executor = executor
        self._display = display
        self._memory = memory
        self._model = model
        self._input_queue = input_queue or asyncio.Queue()
        self._logger = logger
        self._cached_state: BrowserState | None = None
        self._cached_url: str = ""

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

    def _drain_queue(self) -> str:
        messages = []
        while not self._input_queue.empty():
            try:
                msg = self._input_queue.get_nowait()
                if msg == "__INTERRUPT__":
                    continue
                messages.append(msg)
            except asyncio.QueueEmpty:
                break
        return messages[-1] if messages else ""

    async def run_task(self, task: str, session: BrowserSession) -> tuple[str, int]:
        if await self._memory.total_length() > self._settings.max_memory_length:
            if self._model:
                self._display.show_summarizing_status()
                await self._memory.summarize(self._model)

        history: list[StepResult] = []
        conversation_context = await self._memory.format_context()
        deps = AgentDeps(
            browser=session, memory=self._memory,
            display=self._display, settings=self._settings,
            input_queue=self._input_queue,
        )
        user_guidance = ""
        self._cached_state = None
        self._cached_url = ""
        log_path = self._init_run_log(task)

        if self._logger:
            self._logger.log("session_start", 0, {
                "provider": self._settings.provider,
                "model": self._settings.model_name,
                "vision": self._settings.use_vision,
                "headless": self._settings.headless,
                "task": task,
            })

        for step in range(1, self._settings.max_steps + 1):
            step_start = time.perf_counter()
            queued = self._drain_queue()
            if queued:
                user_guidance = queued
                await self._display.clear_queued()
                self._display.show_user_guidance(user_guidance)
                if self._logger:
                    self._logger.log("user_guidance", step, {"text": user_guidance})

            browser_state = await self._get_state_cached(session)
            if self._logger:
                self._logger.log("browser_state", step, {
                    "url": browser_state.url,
                    "title": browser_state.title,
                    "element_count": len(browser_state.interactive_elements),
                })
            recent = history[-3:]
            prompt = format_planner_prompt(
                task, browser_state, recent, conversation_context, user_guidance
            )

            screenshot = await self._capture_screenshot(session)

            self._display.show_step_header(step, self._settings.max_steps)
            await self._display.show_planning_status()

            planner_start = time.perf_counter()
            if self._logger:
                self._logger.log("planner_start", step, {"prompt_length": len(prompt)})

            action = await self._planner.run(self._build_prompt(prompt, screenshot))
            action = action.output

            planner_ms = int((time.perf_counter() - planner_start) * 1000)
            if self._logger:
                self._logger.log("planner_result", step, {
                    "reasoning": action.reasoning,
                    "instruction": action.instruction,
                    "is_complete": action.is_complete,
                }, duration_ms=planner_ms)

            queued_during_planning = self._drain_queue()
            if queued_during_planning:
                await self._display.clear_queued()
                self._display.show_user_guidance(queued_during_planning)
                action.instruction = queued_during_planning
                action.is_complete = False
                action.parallel_instructions = None
                user_guidance = queued_during_planning

            self._display.set_status_text("Working...", "cyan")
            if not queued_during_planning:
                user_guidance = ""

            if action.is_complete:
                await self._display.show_planner_result(action.reasoning, "Task complete")
                self._log_step(log_path, step, action)
                answer = action.final_answer or "Task completed."
                await self._memory.add_conversation(task, answer, step)
                if self._logger:
                    self._logger.log("session_end", step, {
                        "final_answer": answer,
                        "total_steps": step,
                        "duration_ms": self._logger.elapsed_ms(),
                    })
                    self._logger.write_summary(task, answer)
                return answer, step

            if action.parallel_instructions:
                await self._display.show_planner_result(action.reasoning, "parallel execution")
                self._display.show_parallel_instructions(action.parallel_instructions)
                results = await self._execute_parallel(action.parallel_instructions, session, deps)
                for result in results:
                    self._display.show_step_result(result.success, result.message)
                    if self._logger:
                        step_ms = int((time.perf_counter() - step_start) * 1000)
                        self._logger.log("step_result", step, {
                            "success": result.success,
                            "message": result.message[:500],
                        }, duration_ms=step_ms)
                        if not result.success:
                            self._logger.log("error", step, {
                                "message": result.message[:500],
                                "screenshot_path": None,
                            })
                self._log_step(log_path, step, action, results)
                history.extend(results)
                self._invalidate_cache()
            else:
                await self._display.show_planner_result(action.reasoning, action.instruction)
                result, mid_guidance = await self._stream_executor(action.instruction, deps, screenshot, step)
                if mid_guidance:
                    user_guidance = mid_guidance
                self._display.show_step_result(result.success, result.message)
                self._log_step(log_path, step, action, result)
                history.append(result)
                if self._logger:
                    step_ms = int((time.perf_counter() - step_start) * 1000)
                    self._logger.log("step_result", step, {
                        "success": result.success,
                        "message": result.message[:500],
                    }, duration_ms=step_ms)
                    if not result.success:
                        screenshot_path = None
                        if screenshot and self._settings.use_vision:
                            screenshot_path = self._logger.save_error_screenshot(step, screenshot)
                        self._logger.log("error", step, {
                            "message": result.message[:500],
                            "screenshot_path": screenshot_path,
                        })
                self._invalidate_cache()

                if not result.success and self._looks_like_popup_block(result.message):
                    self._display.show_step_header(step, self._settings.max_steps)
                    await self._display.show_planner_result("Auto-dismissing popup/overlay", "Click accept/dismiss button")
                    dismiss_result, _ = await self._stream_executor(
                        "Click on any cookie accept, agree, OK, close, or dismiss button visible on the page",
                        deps,
                    )
                    self._display.show_step_result(dismiss_result.success, dismiss_result.message)
                    self._invalidate_cache()

        answer = "Max steps reached without completing the task."
        await self._memory.add_conversation(task, answer, self._settings.max_steps)
        if self._logger:
            self._logger.log("session_end", 0, {
                "final_answer": answer,
                "total_steps": self._settings.max_steps,
                "duration_ms": self._logger.elapsed_ms(),
            })
            self._logger.write_summary(task, answer)
        return answer, self._settings.max_steps

    def _looks_like_popup_block(self, message: str) -> bool:
        patterns = ["timeout", "overlay", "intercepting pointer events",
                    "element is not visible", "covered by"]
        msg_lower = message.lower()
        return any(p in msg_lower for p in patterns)

    async def _get_state_cached(self, session) -> BrowserState:
        current_url = session.page.url
        if self._cached_state and self._cached_url == current_url:
            return self._cached_state
        state = await session.get_state()
        state.text_content = state.text_content[: self._settings.max_text_length]
        self._cached_state = state
        self._cached_url = current_url
        return state

    def _invalidate_cache(self) -> None:
        self._cached_state = None
        self._cached_url = ""

    async def _capture_screenshot(self, session: BrowserSession) -> bytes | None:
        if not self._settings.use_vision:
            return None
        try:
            return await session.page.screenshot(type="jpeg", quality=50)
        except Exception:
            return None

    def _build_prompt(self, text, screenshot):
        if screenshot is None:
            return text
        from pydantic_ai import BinaryContent
        return [text, BinaryContent(data=screenshot, media_type="image/jpeg")]

    async def _stream_executor(
        self, instruction: str, deps: AgentDeps,
        screenshot: bytes | None = None,
        step: int = 0,
    ) -> tuple[StepResult, str]:
        mid_guidance = ""
        self._display.set_status_text("Executing...", "cyan")

        try:
            final_output = ""
            executor_start = time.perf_counter()
            tool_start: float | None = None
            current_tool: str = ""
            if self._logger:
                self._logger.log("executor_start", step, {"instruction": instruction[:500]})
            prompt = self._build_prompt(instruction, screenshot)
            async for event in self._executor.run_stream_events(
                prompt, deps=deps
            ):
                if isinstance(event, FunctionToolCallEvent):
                    self._display.flush_stream()
                    self._display.show_tool_call(
                        event.part.tool_name, str(event.part.args)
                    )
                    tool_start = time.perf_counter()
                    current_tool = event.part.tool_name
                    if self._logger:
                        self._logger.log("tool_call", step, {
                            "tool_name": event.part.tool_name,
                            "args": str(event.part.args)[:500],
                        })
                elif isinstance(event, FunctionToolResultEvent):
                    self._display.flush_stream()
                    content = str(event.result.content)
                    self._display.show_tool_result(content)
                    tool_ms = int((time.perf_counter() - tool_start) * 1000) if tool_start else None
                    if self._logger:
                        self._logger.log("tool_result", step, {
                            "tool_name": current_tool,
                            "result": content[:500],
                            "success": not content.startswith("Failed"),
                        }, duration_ms=tool_ms)
                    tool_start = None
                elif isinstance(event, PartDeltaEvent):
                    if hasattr(event.delta, "content_delta"):
                        self._display.stream_token(event.delta.content_delta)
                elif isinstance(event, AgentRunResultEvent):
                    final_output = event.result.output

                queued = self._drain_queue()
                if queued:
                    self._display.flush_stream()
                    await self._display.clear_queued()
                    self._display.show_user_guidance(queued)
                    mid_guidance = queued

            self._display.flush_stream()
            executor_ms = int((time.perf_counter() - executor_start) * 1000)
            if self._logger:
                self._logger.log("executor_result", step, {
                    "output": final_output[:500],
                }, duration_ms=executor_ms)
            browser_state = await self._get_state_cached(deps.browser)
            return StepResult(
                success=True,
                message=final_output,
                browser_state=browser_state,
            ), mid_guidance
        except BrowserCloseRequested:
            raise
        except Exception as e:
            self._display.flush_stream()
            return StepResult(
                success=False,
                message=str(e),
                browser_state=BrowserState(url="", title="", text_content="", interactive_elements=[]),
            ), mid_guidance

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
                tab_deps = AgentDeps(
                    browser=tab_session, memory=deps.memory,
                    display=deps.display, settings=deps.settings,
                    input_queue=deps.input_queue,
                )
                result, _ = await self._stream_executor(step.instruction, tab_deps)
                return result

        return await asyncio.gather(*[run_with_limit(s) for s in steps])
