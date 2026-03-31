from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

AGENT_THEME = Theme({
    "step.number": "bold cyan",
    "step.reasoning": "dim green",
    "step.instruction": "dim green",
    "tool.name": "dim green",
    "tool.args": "dim green",
    "tool.result": "dim green",
    "error": "bold red",
    "success": "dim green",
    "stream.label": "dim green",
    "stream.text": "dim green",
    "parallel": "dim magenta",
})


class Display:
    def __init__(self) -> None:
        self.console = Console(theme=AGENT_THEME)

    def show_welcome(self) -> None:
        title = Text("Browser Agent", style="bold cyan")
        subtitle = Text(
            "General-purpose autonomous browser agent\n"
            "Type a task and watch it work. Type 'quit' to exit.",
            style="dim",
        )
        content = Text()
        content.append_text(title)
        content.append("\n")
        content.append_text(subtitle)
        self.console.print(Panel(content, border_style="cyan", padding=(1, 2)))
        self.console.print()

    def show_task(self, task: str) -> None:
        self.console.print(
            Panel(task, title="Task", border_style="blue", padding=(0, 2))
        )
        self.console.print()

    def show_step_header(self, step_num: int, max_steps: int) -> None:
        header = Text()
        header.append(f"  Step {step_num}/{max_steps}  ", style="step.number")
        self.console.print(header)

    def show_step_header_parallel(self, step_num: int, max_steps: int) -> None:
        header = Text()
        header.append(f"  Step {step_num}/{max_steps}  ", style="step.number")
        header.append("  parallel", style="parallel")
        self.console.print(header)

    def start_stream(self, label: str) -> None:
        self.console.print(f"  {label}: ", style="stream.label", end="")

    def stream_token(self, token: str) -> None:
        self.console.print(token, end="", highlight=False, style="stream.text")

    def end_stream(self) -> None:
        self.console.print()

    def show_planner_result(self, reasoning: str, instruction: str) -> None:
        self.console.print(f"  Thinking: {reasoning}", style="step.reasoning")
        self.console.print(f"  Action:   {instruction}", style="step.instruction")
        self.console.print()

    def show_tool_call(self, tool_name: str, args: str) -> None:
        self.console.print(f"    [{tool_name}]", style="tool.name", end=" ")
        self.console.print(args, style="tool.args")

    def show_tool_result(self, result: str) -> None:
        truncated = result[:150] + "..." if len(result) > 150 else result
        self.console.print(f"    -> {truncated}", style="tool.result")

    def show_parallel_instructions(self, instructions: list) -> None:
        for step in instructions:
            self.console.print(
                f"    Tab {step.tab_id}: {step.instruction}", style="dim green"
            )
        self.console.print()

    def show_result(self, answer: str, steps_taken: int) -> None:
        footer = Text(f"\nCompleted in {steps_taken} steps", style="dim")
        content = Text()
        content.append(answer)
        content.append_text(footer)
        self.console.print()
        self.console.print(
            Panel(content, title="Result", border_style="green", padding=(1, 2))
        )
        self.console.print()

    def show_error(self, message: str) -> None:
        self.console.print()
        self.console.print(
            Panel(message, title="Error", border_style="red", padding=(0, 2))
        )
        self.console.print()

    def show_step_result(self, success: bool, message: str) -> None:
        style = "success" if success else "error"
        icon = "+" if success else "x"
        truncated = message[:200] + "..." if len(message) > 200 else message
        self.console.print(f"  [{icon}] {truncated}", style=style)
        self.console.print()

    # Keep for backward compat, delegate to new methods
    def show_step(
        self, step_num: int, max_steps: int, reasoning: str, instruction: str
    ) -> None:
        self.show_step_header(step_num, max_steps)
        self.show_planner_result(reasoning, instruction)

    def show_parallel_step(
        self, step_num: int, max_steps: int, reasoning: str, instructions: list
    ) -> None:
        self.show_step_header_parallel(step_num, max_steps)
        self.console.print(f"  Thinking: {reasoning}", style="step.reasoning")
        self.show_parallel_instructions(instructions)
