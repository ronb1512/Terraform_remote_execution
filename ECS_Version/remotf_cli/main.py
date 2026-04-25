import typer
from remotf_cli.commands.setup import setup, cleanup, active
from remotf_cli.commands.execute import init, plan, apply, destroy

app = typer.Typer()

app.command()(setup)
app.command()(cleanup)
app.command()(active)
app.command()(init)
app.command()(plan)
app.command()(apply)
app.command()(destroy)

if __name__ == "__main__":
    app()