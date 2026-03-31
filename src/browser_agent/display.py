import asyncio

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


class Display:
    def __init__(self) -> None:
        self._log = None
        self._input = None
        self._status = None
        self._app = None
        self._stream_buffer = ""
        self._is_password_mode = False
        self._choice_future: asyncio.Future | None = None

    def set_log(self, log) -> None:
        self._log = log

    def set_input(self, input_widget) -> None:
        self._input = input_widget

    def set_status(self, status_widget) -> None:
        self._status = status_widget

    def set_app(self, app) -> None:
        self._app = app

    def _write(self, content, **kwargs) -> None:
        if self._log:
            self._log.write(content, **kwargs)

    def set_input_mode(self, placeholder: str, password: bool = False) -> None:
        self._is_password_mode = password
        if self._input:
            self._input.placeholder = placeholder
            self._input.password = password
            if password:
                self._input.styles.border = ("solid", "red")
            else:
                self._input.styles.border = ("solid", "yellow")

    def reset_input_mode(self) -> None:
        self._is_password_mode = False
        if self._input:
            self._input.placeholder = "Type a task and press Enter..."
            self._input.password = False
            self._input.styles.border = ("solid", "cyan")
        self._cleanup_choices()

    def set_status_text(self, text: str, style: str = "dim") -> None:
        if self._status:
            self._status.update(Text(f" {text}", style=style))

    def stream_token(self, token: str) -> None:
        self._stream_buffer += token

    def flush_stream(self) -> None:
        if self._stream_buffer.strip():
            self._write(Text(self._stream_buffer.strip(), style="dim green"))
        self._stream_buffer = ""

    def _cleanup_choices(self) -> None:
        if self._choice_future and not self._choice_future.done():
            self._choice_future.cancel()
        self._choice_future = None
        if self._app:
            try:
                from textual.widgets import RadioSet
                choices_widget = self._app.query_one("#choices", RadioSet)
                choices_widget.remove()
            except Exception:
                pass

    async def show_choices(self, options: list[str]) -> str:
        if not options:
            return ""
        if not self._app:
            return options[0]

        from textual.widgets import RadioButton, RadioSet

        self._choice_future = asyncio.get_running_loop().create_future()

        radio_set = RadioSet(
            *[RadioButton(opt) for opt in options],
            id="choices",
        )
        await self._app.mount(radio_set, before=self._input)

        self._write(Text("  Use arrow keys to select, then press Enter", style="bold yellow"))
        self.set_status_text("Select an option...", "yellow")

        try:
            result = await self._choice_future
        finally:
            self._choice_future = None
            self._cleanup_choices()

        return result

    def resolve_choice(self, value: str) -> None:
        if self._choice_future and not self._choice_future.done():
            self._choice_future.set_result(value)

    def show_welcome(self) -> None:
        title = Text("Browser Agent", style="bold cyan")
        subtitle = Text(
            "General-purpose autonomous browser agent\n"
            "Type a task below and press Enter.",
            style="dim",
        )
        content = Text()
        content.append_text(title)
        content.append("\n")
        content.append_text(subtitle)
        self._write(Panel(content, border_style="cyan", padding=(1, 2)))

    def show_task(self, task: str) -> None:
        self._write(Panel(task, title="Task", border_style="blue", padding=(0, 2)))

    def show_step_header(self, step_num: int, max_steps: int) -> None:
        self._write(Text(f"  Step {step_num}/{max_steps}", style="bold cyan"))

    def show_planning_status(self) -> None:
        self.set_status_text("Planning...", "dim cyan")
        self._write(Text("  Planning...", style="dim"))

    def show_summarizing_status(self) -> None:
        self.set_status_text("Summarizing memory...", "dim")
        self._write(Text("  Summarizing memory...", style="dim"))

    def show_planner_result(self, reasoning: str, instruction: str) -> None:
        self._write(Text(f"  Thinking: {reasoning}", style="dim green"))
        self._write(Text(f"  Action:   {instruction}", style="dim green"))

    def show_tool_call(self, tool_name: str, args: str) -> None:
        line = Text()
        line.append(f"    [{tool_name}] ", style="dim green")
        line.append(args, style="dim green")
        self._write(line)

    def show_tool_result(self, result: str) -> None:
        truncated = result[:150] + "..." if len(result) > 150 else result
        self._write(Text(f"    -> {truncated}", style="dim green"))

    def show_parallel_instructions(self, instructions: list) -> None:
        for step in instructions:
            self._write(Text(f"    Tab {step.tab_id}: {step.instruction}", style="dim green"))

    def show_result(self, answer: str, steps_taken: int) -> None:
        self.set_status_text("Ready", "green")
        self.reset_input_mode()
        try:
            md = Markdown(answer)
            self._write(Panel(md, title="Result", subtitle=f"Completed in {steps_taken} steps", border_style="green", padding=(1, 2)))
        except Exception:
            self._write(Panel(answer, title="Result", subtitle=f"Completed in {steps_taken} steps", border_style="green", padding=(1, 2)))

    def show_error(self, message: str) -> None:
        self.set_status_text("Error", "red")
        self._write(Panel(message, title="Error", border_style="red", padding=(0, 2)))

    def show_step_result(self, success: bool, message: str) -> None:
        style = "dim green" if success else "bold red"
        icon = "+" if success else "x"
        truncated = message[:200] + "..." if len(message) > 200 else message
        self._write(Text(f"  [{icon}] {truncated}", style=style))

    def show_user_guidance(self, message: str) -> None:
        if self._is_password_mode:
            self._write(Text("  [user] ********", style="bold yellow"))
        else:
            self._write(Text(f"  [user] {message}", style="bold yellow"))

    def show_step(self, step_num: int, max_steps: int, reasoning: str, instruction: str) -> None:
        self.show_step_header(step_num, max_steps)
        self.show_planner_result(reasoning, instruction)

    def show_parallel_step(self, step_num: int, max_steps: int, reasoning: str, instructions: list) -> None:
        header = Text()
        header.append(f"  Step {step_num}/{max_steps}  ", style="bold cyan")
        header.append("parallel", style="dim magenta")
        self._write(header)
        self._write(Text(f"  Thinking: {reasoning}", style="dim green"))
        self.show_parallel_instructions(instructions)

    def prompt_human(self, question: str) -> None:
        self._write(Panel(question, title="Agent needs your input", border_style="yellow", padding=(0, 2)))
        self.set_input_mode("Type your answer...")
        self.set_status_text("Waiting for your input", "yellow")

    def prompt_human_choice(self, question: str, options: list[str]) -> None:
        self._write(Panel(question, title="Agent needs your choice", border_style="yellow", padding=(0, 2)))
        self.set_status_text("Select an option...", "yellow")

    def show_form_header(self, total_fields: int) -> None:
        self._write(Panel(
            f"The agent needs you to fill {total_fields} field{'s' if total_fields != 1 else ''}",
            title="Form Input",
            border_style="yellow",
            padding=(0, 2),
        ))
        self.set_status_text("Filling form...", "yellow")

    def prompt_form_field(self, index: int, total: int, label: str, field_type: str) -> None:
        subtitle = f"Type: {field_type}" if field_type not in ("text", "") else ""
        content = Text()
        content.append(label, style="bold")
        if subtitle:
            content.append(f"\n{subtitle}", style="dim")
        self._write(Panel(content, title=f"Field {index}/{total}", border_style="yellow", padding=(0, 2)))

        is_password = field_type == "password"
        placeholder = f"Enter {label}..." if not is_password else "Enter password..."
        self.set_input_mode(placeholder, password=is_password)

    def show_form_complete(self, fields: list[str]) -> None:
        self._write(Text(f"  Filled {len(fields)} fields: {', '.join(fields)}", style="dim green"))
        self.reset_input_mode()
        self.set_status_text("Working...", "cyan")

    def prompt_wait(self, instruction: str) -> None:
        self._write(Panel(instruction, title="Action needed in browser", border_style="yellow", padding=(0, 2)))
        self.set_input_mode("Type 'done' when finished...")
        self.set_status_text("Waiting for browser action", "yellow")

    def prompt_interrupt(self) -> None:
        self._write(Panel(
            "Task interrupted. Type a new task below.",
            title="Interrupted",
            border_style="red",
            padding=(0, 2),
        ))
        self.set_status_text("Interrupted", "red")
        self.reset_input_mode()
