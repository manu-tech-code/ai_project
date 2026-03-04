import typer

app = typer.Typer()


@app.command()
def analyze(repo: str) -> None:
    typer.echo(f"Queued analysis for {repo}")
