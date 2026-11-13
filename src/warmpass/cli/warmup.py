from datetime import datetime
from time import perf_counter
from typing import Annotated

import typer
from rich.console import Console

from warmpass.agents.base import WarmupError
from warmpass.agents.models import AgentType
from warmpass.warmup.factory import create_warmup_service

app = typer.Typer(help="Warm up a specific agent immediately.")


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@app.command("warmup", help="Warm up a specific agent immediately.")
def warmup(
    agent: Annotated[AgentType, typer.Option(help="The name of the agent to warm up.")],
) -> None:
    console = Console(stderr=True)

    typer.echo(f"{_timestamp()} INFO Warmup started: agent={agent.value}")
    started_at = perf_counter()

    try:
        service = create_warmup_service(agent)
        if console.is_terminal:
            with console.status(
                f"[bold green]Warming up {agent.value}...", spinner="dots"
            ):
                service.warmup()
        else:
            service.warmup()
    except WarmupError as exc:
        duration = perf_counter() - started_at
        typer.echo(
            f"{_timestamp()} ERROR Warmup failed: "
            f"agent={agent.value} duration={duration:.2f}s message={exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    duration = perf_counter() - started_at
    typer.echo(
        f"{_timestamp()} INFO Warmup completed: "
        f"agent={agent.value} duration={duration:.2f}s"
    )
