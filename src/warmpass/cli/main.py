from typing import Annotated

import typer
from rich.console import Console

from warmpass.agents.factory import get_warmup_agent_by_type
from warmpass.agents.models import WarmupAgentType
from warmpass.warmup.service import WarmupService

app = typer.Typer()


@app.callback()
def main() -> None:
    pass


@app.command()
def warmup(
    agent: Annotated[
        WarmupAgentType, typer.Option(help="The name of the agent to warm up.")
    ],
) -> None:
    warmup_agent = get_warmup_agent_by_type(agent)
    console = Console(stderr=True)

    with console.status(f"[bold green]Warming up {agent.value}...", spinner="dots"):
        result = WarmupService(warmup_agent).warmup()

    typer.echo(result.message)


if __name__ == "__main__":
    app()
