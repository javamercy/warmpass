"""Root Typer application assembling the warmup and schedule commands."""

import typer

from .schedule import app as schedule_app
from .warmup import app as warmup_app

app = typer.Typer()

app.add_typer(schedule_app, name="schedule")
app.add_typer(warmup_app)


@app.callback()
def main() -> None:
    """Run and schedule coding agent warmups."""


if __name__ == "__main__":
    app()
