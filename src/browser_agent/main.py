import asyncio
import platform

from pydantic_ai.models import Model

from browser_agent.model_factory import create_model
from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Key
from textual.suggester import SuggestFromList
from textual.widgets import Collapsible, Footer, Header, Input, RadioSet, RichLog, Static
from textual.worker import Worker, WorkerState

from browser_agent.agents.executor import create_executor
from browser_agent.agents.planner import create_planner
from browser_agent.browser.session import BrowserSession
from browser_agent.config import Settings
from browser_agent.display import Display
from browser_agent.memory import MemoryStore
from browser_agent.models import BrowserCloseRequested
from browser_agent.orchestrator import Orchestrator
from browser_agent.session_logger import SessionLogger

DEFAULT_CSS = """
Screen {
    background: $surface;
}

#status {
    height: 1;
    padding: 0 2;
    background: $surface-darken-1;
    color: $text-muted;
}

#output {
    height: 1fr;
    scrollbar-size: 1 1;
}

RichLog {
    height: auto;
    min-height: 5;
    max-height: 20;
    padding: 0 1;
}

#loading {
    height: 3;
    color: cyan;
}

Collapsible {
    height: auto;
    padding: 0 1;
}

RadioSet {
    height: auto;
    max-height: 10;
    margin: 0 2;
    border: solid yellow;
}

#queued-msg {
    height: 1;
    padding: 0 2;
    background: #3a3000;
    color: yellow;
}

#input {
    height: 3;
    border: solid cyan;
    margin-bottom: 1;
}
"""

COMMANDS = [
    "/help", "/settings", "/provider", "/model", "/vision", "/smart", "/headless",
    "/steps", "/retries", "/concurrent",
    "/clear", "/memory", "/connect", "/disconnect",
]

HELP_TEXT = (
    "/provider <name>  Switch AI provider (ollama, openai, anthropic, google)\n"
    "/model <name>     Switch model for current provider\n"
    "/vision           Toggle vision mode (send screenshots to LLM)\n"
    "/smart            Toggle smart locator (intent-based element finding)\n"
    "/headless         Toggle headless mode\n"
    "/connect [port]   Launch Chrome + connect via CDP (default port 9222)\n"
    "/disconnect       Disconnect from Chrome, use standalone browser\n"
    "/steps <n>        Set max steps\n"
    "/retries <n>      Set max retries\n"
    "/concurrent <n>   Set max concurrent tabs\n"
    "/settings         Show current settings\n"
    "/clear            Clear the output log\n"
    "/memory           Show saved findings\n"
    "/help             Show this help"
)

CHROME_PATHS = {
    "Darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "Linux": "google-chrome",
    "Windows": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}

CHROME_PROFILES = {
    "Darwin": "~/Library/Application Support/Google/Chrome",
    "Linux": "~/.config/google-chrome",
    "Windows": "~/AppData/Local/Google/Chrome/User Data",
}


class BrowserAgentApp(App):
    TITLE = "Browser Agent"
    CSS = DEFAULT_CSS

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=True),
        Binding("ctrl+q", "quit_app", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings()
        self.agent_display = Display()
        self.input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._session: BrowserSession | None = None
        self._orchestrator: Orchestrator | None = None
        self._model: Model | None = None
        self._memory: MemoryStore | None = None
        self._running_task = False
        self._current_worker: Worker | None = None
        self._input_history: list[str] = []
        self._history_index: int = -1

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(" Ready", id="status")
        with VerticalScroll(id="output"):
            yield RichLog(id="log", markup=True, auto_scroll=True)
        yield Input(
            placeholder="Type a task and press Enter...",
            id="input",
            suggester=SuggestFromList(COMMANDS, case_sensitive=False),
        )
        yield Footer()

    async def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        output = self.query_one("#output", VerticalScroll)
        input_widget = self.query_one("#input", Input)
        status_widget = self.query_one("#status", Static)

        self.agent_display.set_log(log)
        self.agent_display.set_output_container(output)
        self.agent_display.set_input(input_widget)
        self.agent_display.set_status(status_widget)
        self.agent_display.set_app(self)

        self._model = self._create_model()
        self._memory = MemoryStore(self.settings.memory_db_path)
        await self._memory.initialize()
        self._rebuild_agents()

        self.agent_display.show_welcome()
        input_widget.focus()

    def on_key(self, event: Key) -> None:
        input_widget = self.query_one("#input", Input)
        if not input_widget.has_focus:
            return

        if event.key == "up" and self._input_history:
            event.prevent_default()
            if self._history_index == -1:
                self._history_index = len(self._input_history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
            input_widget.value = self._input_history[self._history_index]
            input_widget.cursor_position = len(input_widget.value)

        elif event.key == "tab":
            event.prevent_default()
            suggestion = getattr(input_widget, "_suggestion", "")
            if suggestion:
                input_widget.value = suggestion
                input_widget.cursor_position = len(input_widget.value)

        elif event.key == "down":
            event.prevent_default()
            if self._history_index == -1:
                return
            if self._history_index < len(self._input_history) - 1:
                self._history_index += 1
                input_widget.value = self._input_history[self._history_index]
            else:
                self._history_index = -1
                input_widget.value = ""
            input_widget.cursor_position = len(input_widget.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.control.value = ""

        if not text:
            return

        self._input_history.append(text)
        self._history_index = -1

        if text.lower() in ("quit", "exit", "q"):
            await self._cleanup()
            self.exit()
            return

        if text.startswith("/"):
            await self._handle_command(text)
            return

        if self._running_task:
            await self.agent_display.show_queued(text)
            await self.input_queue.put(text)
            return

        self._running_task = True
        self.agent_display.set_status_text("Working...", "cyan")
        self._current_worker = self.run_worker(self._run_task(text))

    def _preload_smart_model(self) -> None:
        try:
            from browser_agent.tools.smart_tools import _get_embedding_model
            _get_embedding_model()
            self._log_write(Text("  Smart locator model loaded", style="dim"))
        except Exception as e:
            self._log_write(Text(f"  Smart locator model failed: {e}", style="red"))

    def _create_model(self) -> Model:
        return create_model(self.settings)

    def _rebuild_agents(self, logger=None) -> None:
        from browser_agent.tools import ALL_TOOLS, BASIC_LOCATOR_TOOLS

        if self.settings.use_smart_locator:
            tools = [t for t in ALL_TOOLS if t not in BASIC_LOCATOR_TOOLS]
        else:
            tools = ALL_TOOLS

        planner = create_planner(self._model, max_retries=self.settings.max_retries)
        executor = create_executor(self._model, max_retries=self.settings.max_retries, tools=tools)
        self._orchestrator = Orchestrator(
            self.settings, planner, executor, self.agent_display, self._memory,
            model=self._model, input_queue=self.input_queue, logger=logger,
        )

    async def _connect_chrome(self, arg: str) -> None:
        import shutil
        from pathlib import Path

        port = int(arg) if arg.isdigit() else 9222

        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            await self._cleanup_session()
            self.settings.chrome_cdp_url = f"http://127.0.0.1:{port}"
            self._log_write(Text(f"  Connected to existing Chrome on port {port}", style="green"))
            return
        except (ConnectionRefusedError, OSError):
            pass

        chrome_path = CHROME_PATHS.get(platform.system())
        if not chrome_path:
            self._log_write(Text(f"  Chrome not found for {platform.system()}", style="red"))
            return

        debug_dir = Path(f"/tmp/chrome-debug-profile")
        real_profile = Path(CHROME_PROFILES.get(platform.system(), "")).expanduser()
        needs_copy = real_profile.exists() and not (debug_dir / "Default").exists()

        if needs_copy:
            self._log_write(Panel(
                "Copying your Chrome profile for remote debugging.\n"
                "Your original profile is NOT modified — only a copy is used.\n"
                "This may take a moment on first run...",
                title="First-time setup",
                border_style="yellow",
                padding=(0, 2),
            ))
            debug_dir.mkdir(parents=True, exist_ok=True)
            src_default = real_profile / "Default"
            if src_default.exists():
                shutil.copytree(
                    src_default, debug_dir / "Default",
                    ignore=shutil.ignore_patterns("Cache", "Code Cache", "GPUCache", "Service Worker", "blob_storage"),
                    dirs_exist_ok=True,
                )
            self._log_write(Text(f"  Profile copied to {debug_dir}", style="dim"))
        elif not real_profile.exists():
            debug_dir.mkdir(parents=True, exist_ok=True)
            self._log_write(Text(f"  No Chrome profile found, using fresh profile", style="dim"))
        else:
            self._log_write(Text(f"  Using existing debug profile", style="dim"))

        self._log_write(Text(f"  Launching Chrome with debugging on port {port}...", style="dim"))
        try:
            proc = await asyncio.create_subprocess_exec(
                chrome_path,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={debug_dir}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            self._log_write(Text(f"  Chrome started (PID: {proc.pid})", style="dim"))
        except FileNotFoundError:
            self._log_write(Text(f"  Chrome not found at: {chrome_path}", style="red"))
            return
        except Exception as e:
            self._log_write(Text(f"  Failed to launch: {e}", style="red"))
            return

        self._log_write(Text(f"  Waiting for debugging port...", style="dim"))
        for attempt in range(20):
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                break
            except (ConnectionRefusedError, OSError):
                await asyncio.sleep(0.5)
        else:
            stderr_output = ""
            if proc.stderr:
                try:
                    stderr_data = await asyncio.wait_for(proc.stderr.read(4096), timeout=1)
                    stderr_output = stderr_data.decode(errors="replace").strip()
                except Exception:
                    pass
            error_msg = f"  Chrome didn't open port {port}."
            if stderr_output:
                error_msg += f"\n  Chrome said: {stderr_output[:300]}"
            else:
                error_msg += "\n  Close ALL Chrome windows first, then /connect again."
            self._log_write(Text(error_msg, style="red"))
            return

        await self._cleanup_session()
        self.settings.chrome_cdp_url = f"http://127.0.0.1:{port}"
        self._log_write(Text(f"  Connected to Chrome on port {port}", style="green"))

    def _log_write(self, content) -> None:
        self.query_one("#log", RichLog).write(content)

    def _set_int_setting(self, name: str, attr: str, arg: str, rebuild: bool = False) -> None:
        if not arg.isdigit():
            self._log_write(Text(f"  Usage: /{name} <number>", style="red"))
            return
        setattr(self.settings, attr, int(arg))
        if rebuild:
            self._rebuild_agents()
        self._log_write(Text(f"  {name}: {arg}", style="green"))

    async def _handle_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        match cmd:
            case "/help":
                self._log_write(Panel(HELP_TEXT, title="Commands", border_style="cyan", padding=(0, 2)))

            case "/settings":
                s = self.settings
                lines = [
                    f"Provider:   {s.provider}",
                    f"Model:      {s.model_name}",
                ]
                if s.provider == "ollama":
                    lines.append(f"Ollama URL: {s.ollama_base_url}")
                lines.extend([
                    f"Vision:     {s.use_vision}",
                    f"Smart:      {s.use_smart_locator}",
                    f"Headless:   {s.headless}",
                    f"Max steps:  {s.max_steps}",
                    f"Max retries: {s.max_retries}",
                    f"Concurrent: {s.max_concurrent}",
                    f"Text limit: {s.max_text_length}",
                    f"Viewport:   {s.viewport_width}x{s.viewport_height}",
                ])
                self._log_write(Panel(
                    "\n".join(lines),
                    title="Settings", border_style="cyan", padding=(0, 2),
                ))

            case "/provider":
                from browser_agent.model_factory import DEFAULT_MODELS
                valid = tuple(DEFAULT_MODELS)
                if not arg:
                    self._log_write(Text(f"  Current provider: {self.settings.provider}", style="cyan"))
                    return
                if arg not in valid:
                    self._log_write(Text(f"  Unknown provider: {arg}. Use: {', '.join(valid)}", style="red"))
                    return
                self.settings.provider = arg
                self.settings.model_name = DEFAULT_MODELS[arg]
                self._model = self._create_model()
                self._rebuild_agents()
                self._log_write(Text(f"  Provider switched to: {arg} (model: {self.settings.model_name})", style="green"))

            case "/model":
                if not arg:
                    self._log_write(Text(f"  Current model: {self.settings.model_name}", style="cyan"))
                    return
                self.settings.model_name = arg
                self._model = self._create_model()
                self._rebuild_agents()
                self._log_write(Text(f"  Model switched to: {arg}", style="green"))

            case "/vision":
                self.settings.use_vision = not self.settings.use_vision
                state = "ON" if self.settings.use_vision else "OFF"
                self._log_write(Text(f"  Vision: {state} (screenshots sent to LLM each step)", style="green"))

            case "/smart":
                self.settings.use_smart_locator = not self.settings.use_smart_locator
                if self.settings.use_smart_locator:
                    self._preload_smart_model()
                self._rebuild_agents()
                state = "ON" if self.settings.use_smart_locator else "OFF"
                detail = "smart tools replace basic click/type" if self.settings.use_smart_locator else "basic click/type restored"
                self._log_write(Text(f"  Smart locator: {state} ({detail})", style="green"))

            case "/headless":
                self.settings.headless = not self.settings.headless
                await self._cleanup_session()
                self._log_write(Text(f"  Headless: {self.settings.headless} (browser restarts on next task)", style="green"))

            case "/steps":
                self._set_int_setting("steps", "max_steps", arg)

            case "/retries":
                self._set_int_setting("retries", "max_retries", arg, rebuild=True)

            case "/concurrent":
                self._set_int_setting("concurrent", "max_concurrent", arg)

            case "/clear":
                await self.agent_display.clear_output()

            case "/memory":
                if not self._memory:
                    self._log_write(Text("  Memory not initialized.", style="red"))
                    return
                findings = await self._memory.list_findings()
                if not findings:
                    self._log_write(Text("  No findings saved yet.", style="dim"))
                    return
                lines = [f"  [{f['key']}]: {f['preview']}" for f in findings]
                self._log_write(Panel("\n".join(lines), title="Saved Findings", border_style="cyan", padding=(0, 2)))

            case "/connect":
                await self._connect_chrome(arg)

            case "/disconnect":
                self.settings.chrome_cdp_url = ""
                await self._cleanup_session()
                self._log_write(Text("  Disconnected. Next task will use standalone browser.", style="green"))

            case _:
                self._log_write(Text(f"  Unknown command: {cmd}. Type /help for commands.", style="red"))

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.pressed:
            self.agent_display.resolve_choice(str(event.pressed.label))

    async def _run_task(self, task: str) -> None:
        if not self._session:
            try:
                session = BrowserSession(self.settings)
                await session.__aenter__()
                self._session = session
            except Exception as e:
                error_msg = str(e)
                if "ECONNREFUSED" in error_msg or "connect_over_cdp" in error_msg:
                    self.agent_display.show_error(
                        f"Failed to connect to Chrome. Make sure Chrome is running with --remote-debugging-port.\n"
                        f"Run /connect to launch Chrome, or /disconnect to use standalone browser."
                    )
                    self.settings.chrome_cdp_url = ""
                else:
                    self.agent_display.show_error(f"Failed to start browser: {error_msg}")
                return

        self.agent_display.show_task(task)

        logger = SessionLogger(self.settings.logs_dir, self._memory._session_id)
        self._rebuild_agents(logger=logger)

        try:
            answer, steps = await self._orchestrator.run_task(task, self._session)
            self.agent_display.show_result(answer, steps)
        except BrowserCloseRequested:
            self.agent_display.show_error("Browser closed by agent.")
            await self._cleanup_session()
        except asyncio.CancelledError:
            self.agent_display.prompt_interrupt()
            await self._cleanup_session()
        except Exception as e:
            self.agent_display.show_error(str(e))
            await self._cleanup_session()

    async def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker != self._current_worker:
            return
        if event.state in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED):
            self._running_task = False
            self._current_worker = None
            self.agent_display.set_status_text("Ready", "green")
            self.agent_display.reset_input_mode()
            await self.agent_display.clear_queued()
            self._drain_stale_queue()

    def _drain_stale_queue(self) -> None:
        while not self.input_queue.empty():
            try:
                self.input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def action_interrupt(self) -> None:
        if self._running_task and self._current_worker:
            self._current_worker.cancel()

    async def action_quit_app(self) -> None:
        await self._cleanup()
        self.exit()

    async def _cleanup_session(self) -> None:
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None

    async def _cleanup(self) -> None:
        await self._cleanup_session()
        if self._memory:
            await self._memory.close()


def main() -> None:
    import os
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "1"
    try:
        from browser_agent.tools.smart_tools import _get_embedding_model
        _get_embedding_model()
    except Exception:
        pass  # sentence-transformers not installed — smart tools will show clear error if used
    BrowserAgentApp().run()


if __name__ == "__main__":
    main()
