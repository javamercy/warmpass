from datetime import datetime
from time import perf_counter
from typing import Annotated

import typer
from rich.console import Console

from warmpass.agents.models import WarmupAgentType, WarmupStatus
from warmpass.warmup.factory import create_warmup_service

app = typer.Typer(help="Warm up a specific agent immediately")


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@app.command(help="Warm up a specific agent immediately.")
def warmup(
    agent: Annotated[
        WarmupAgentType, typer.Option(help="The name of the agent to warm up.")
    ],
) -> None:
    service = create_warmup_service(agent)
    console = Console(stderr=True)

    typer.echo(f"{_timestamp()} INFO Warmup started: agent={agent.value}")
    started_at = perf_counter()

    if console.is_terminal:
        with console.status(f"[bold green]Warming up {agent.value}...", spinner="dots"):
            result = service.warmup()
    else:
        result = service.warmup()

    duration = perf_counter() - started_at

    if result.status == WarmupStatus.SUCCESS:
        typer.echo(
            f"{_timestamp()} INFO Warmup completed: "
            f"agent={agent.value} duration={duration:.2f}s"
        )
        return

    typer.echo(
        f"{_timestamp()} ERROR Warmup failed: "
        f"agent={agent.value} "
        f"status={result.status.value} "
        f"duration={duration:.2f}s "
        f"exit_code={result.exit_code} "
        f"message={result.message}"
    )
    raise typer.Exit(code=1)
