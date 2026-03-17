import typer
from github_agent.agent import run_agent

app = typer.Typer()

@app.command()
def run(query: str):
    run_agent(query)

if __name__ == "__main__":
    app()