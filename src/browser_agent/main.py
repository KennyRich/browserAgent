import asyncio

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from browser_agent.agents.executor import create_executor
from browser_agent.agents.planner import create_planner
from browser_agent.browser.session import BrowserSession
from browser_agent.config import Settings
from browser_agent.display import Display
from browser_agent.memory import MemoryStore
from browser_agent.models import BrowserCloseRequested
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

    memory = MemoryStore(settings.memory_db_path)
    await memory.initialize()

    orchestrator = Orchestrator(
        settings, planner, executor, display, memory, model=model
    )

    display.show_welcome()

    session = None
    try:
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

            if not session:
                session = BrowserSession(settings)
                await session.__aenter__()

            display.show_task(task)

            try:
                answer, steps = await orchestrator.run_task(task, session)
                display.show_result(answer, steps)
            except BrowserCloseRequested:
                display.console.print("Browser closed. Goodbye!", style="dim")
                break
            except Exception as e:
                display.show_error(str(e))
    finally:
        if session:
            await session.__aexit__(None, None, None)
        await memory.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
