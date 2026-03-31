import asyncio

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from browser_agent.agents.executor import create_executor
from browser_agent.agents.planner import create_planner
from browser_agent.browser.session import BrowserSession
from browser_agent.config import Settings
from browser_agent.display import Display
from browser_agent.orchestrator import Orchestrator


async def run() -> None:
    settings = Settings()
    display = Display()

    model = OpenAIChatModel(
        model_name=settings.model_name,
        provider=OllamaProvider(base_url=settings.ollama_base_url),
    )

    planner = create_planner(model, max_retries=settings.max_retries)
    executor = create_executor(model, max_retries=settings.max_retries)
    orchestrator = Orchestrator(settings, planner, executor, display)

    display.show_welcome()

    while True:
        try:
            task = display.console.input("[bold cyan]> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            display.console.print("\nGoodbye!", style="dim")
            break

        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            display.console.print("Goodbye!", style="dim")
            break

        display.show_task(task)

        try:
            async with BrowserSession(settings) as session:
                answer, steps = await orchestrator.run_task(task, session)
                display.show_result(answer, steps)
        except Exception as e:
            display.show_error(str(e))


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
