"""Interactive setup — creates .env with Last.fm API key and username."""

import sys
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()
ENV_FILE = Path(__file__).parent / ".env"


def validate_api_key(api_key: str, username: str) -> bool:
    """Hit Last.fm API to verify the key works."""
    console.print("\n[dim]Validating API key...[/dim]")
    try:
        resp = httpx.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "user.getInfo",
                "user": username,
                "api_key": api_key,
                "format": "json",
            },
            timeout=10,
        )
        data = resp.json()
        if "error" in data:
            console.print(f"[red]API error: {data.get('message', 'unknown')}[/red]")
            return False
        user = data.get("user", {})
        playcount = int(user.get("playcount", 0))
        console.print(
            f"[green]Connected![/green] "
            f"User [bold]{user.get('name')}[/bold] — "
            f"[cyan]{playcount:,}[/cyan] scrobbles"
        )
        return True
    except httpx.HTTPError as e:
        console.print(f"[red]Connection failed: {e}[/red]")
        return False


def main() -> None:
    console.print(
        Panel(
            "[bold]lastfm-export setup[/bold]\n\n"
            "You need a Last.fm API key.\n"
            "Get one at [link=https://www.last.fm/api/account/create]last.fm/api/account/create[/link]",
            border_style="blue",
        )
    )

    # Check existing .env
    if ENV_FILE.exists():
        if not Confirm.ask("[yellow].env already exists. Overwrite?[/yellow]", default=False):
            console.print("[dim]Aborted.[/dim]")
            return

    api_key = Prompt.ask("\n[bold]Last.fm API key[/bold]").strip()
    if not api_key:
        console.print("[red]API key cannot be empty.[/red]")
        sys.exit(1)

    username = Prompt.ask("[bold]Last.fm username[/bold]").strip()
    if not username:
        console.print("[red]Username cannot be empty.[/red]")
        sys.exit(1)

    if not validate_api_key(api_key, username):
        if not Confirm.ask("[yellow]Save anyway?[/yellow]", default=False):
            console.print("[dim]Aborted.[/dim]")
            return

    ENV_FILE.write_text(f"LASTFM_API_KEY={api_key}\nLASTFM_USERNAME={username}\n")
    console.print(f"\n[green]Saved to {ENV_FILE}[/green]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  uv run export.py            # export scrobbles")
    console.print("  uv run generate_stats.py    # generate stats")
    console.print("  open index.html             # view report")


if __name__ == "__main__":
    main()
