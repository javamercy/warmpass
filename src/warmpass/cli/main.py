import typer

from .schedule import app as schedule_app
from .warmup import app as warmup_app

app = typer.Typer()

app.add_typer(schedule_app, name="schedule")
app.add_typer(warmup_app)


@app.callback()
def main() -> None:
    pass


if __name__ == "__main__":
    app()
