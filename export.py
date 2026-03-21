"""Export all scrobbles from Last.fm to data/scrobbles_raw.json.

Supports resumption: saves checkpoint every 10 pages to data/export_state.json.
Rate-limited to ~4 req/sec. Retries on 5xx/429 with backoff.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

load_dotenv()

API_KEY = os.getenv("LASTFM_API_KEY")
USERNAME = os.getenv("LASTFM_USERNAME", "Denya")
BASE_URL = "https://ws.audioscrobbler.com/2.0/"
PER_PAGE = 200
RATE_DELAY = 0.25  # 4 req/sec
CHECKPOINT_EVERY = 10
MAX_RETRIES = 3
DATA_DIR = Path(__file__).parent / "data"

console = Console()


def fetch_page(client: httpx.Client, page: int, **extra_params) -> dict:
    """Fetch a single page of recent tracks with retry logic."""
    params = {
        "method": "user.getRecentTracks",
        "user": USERNAME,
        "api_key": API_KEY,
        "limit": PER_PAGE,
        "page": page,
        "format": "json",
        "extended": 1,
        **extra_params,
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(BASE_URL, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                console.print(f"[yellow]Rate limited, waiting {wait}s...[/yellow]")
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = 5 * (attempt + 1)
                console.print(
                    f"[yellow]Server error {resp.status_code}, retry in {wait}s...[/yellow]"
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            if attempt < MAX_RETRIES - 1:
                console.print(f"[yellow]Timeout, retrying ({attempt + 1})...[/yellow]")
                time.sleep(5)
            else:
                raise
    raise RuntimeError(f"Failed to fetch page {page} after {MAX_RETRIES} retries")


def parse_scrobble(track: dict) -> dict | None:
    """Extract relevant fields from a track object. Skip now-playing."""
    if track.get("@attr", {}).get("nowplaying") == "true":
        return None
    date_info = track.get("date")
    if not date_info:
        return None
    images = track.get("image", [])
    image_url = ""
    for img in reversed(images):
        if img.get("#text"):
            image_url = img["#text"]
            break
    return {
        "artist": track.get("artist", {}).get("name", ""),
        "track": track.get("name", ""),
        "album": track.get("album", {}).get("#text", ""),
        "timestamp": int(date_info.get("uts", 0)),
        "loved": track.get("loved", "0") == "1",
        "artist_mbid": track.get("artist", {}).get("mbid", ""),
        "track_mbid": track.get("mbid", ""),
        "album_mbid": track.get("album", {}).get("mbid", ""),
        "image_url": image_url,
    }


def load_state() -> tuple[list[dict], int]:
    """Load existing scrobbles and last completed page from checkpoint."""
    state_file = DATA_DIR / "export_state.json"
    raw_file = DATA_DIR / "scrobbles_raw.json"
    if state_file.exists() and raw_file.exists():
        state = json.loads(state_file.read_text())
        scrobbles = json.loads(raw_file.read_text())
        last_page = state.get("last_completed_page", 0)
        console.print(
            f"[green]Resuming from page {last_page + 1} "
            f"({len(scrobbles)} scrobbles loaded)[/green]"
        )
        return scrobbles, last_page
    return [], 0


def save_state(scrobbles: list[dict], page: int) -> None:
    """Save checkpoint: scrobbles and last completed page."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "scrobbles_raw.json").write_text(
        json.dumps(scrobbles, separators=(",", ":"))
    )
    (DATA_DIR / "export_state.json").write_text(
        json.dumps({"last_completed_page": page, "count": len(scrobbles)})
    )


def main() -> None:
    if not API_KEY:
        console.print("[red]Error: LASTFM_API_KEY not set in .env[/red]")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    scrobbles, start_page = load_state()

    with httpx.Client() as client:
        # First request to get total pages
        console.print(f"[bold]Fetching scrobbles for [cyan]{USERNAME}[/cyan]...[/bold]")
        first = fetch_page(client, 1)
        attrs = first["recenttracks"]["@attr"]
        total_pages = int(attrs["totalPages"])
        total_tracks = int(attrs["total"])
        console.print(
            f"[bold]Total: [cyan]{total_tracks:,}[/cyan] scrobbles, "
            f"[cyan]{total_pages:,}[/cyan] pages[/bold]"
        )

        # Always process page 1 (on resume, new scrobbles may have shifted pages;
        # deduplication at the end handles any duplicates)
        for track in first["recenttracks"]["track"]:
            s = parse_scrobble(track)
            if s:
                scrobbles.append(s)
        if start_page == 0:
            start_page = 1
        save_state(scrobbles, start_page)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Fetching pages",
                total=total_pages,
                completed=start_page,
            )

            for page in range(start_page + 1, total_pages + 1):
                time.sleep(RATE_DELAY)
                data = fetch_page(client, page)
                tracks = data.get("recenttracks", {}).get("track", [])
                for track in tracks:
                    s = parse_scrobble(track)
                    if s:
                        scrobbles.append(s)
                progress.update(task, completed=page)
                progress.update(
                    task,
                    description=f"Fetching pages ({len(scrobbles):,} scrobbles)",
                )

                if page % CHECKPOINT_EVERY == 0:
                    save_state(scrobbles, page)

        # Final save
        save_state(scrobbles, total_pages)

    # Deduplicate by (artist, track, timestamp)
    seen = set()
    unique = []
    for s in scrobbles:
        key = (s["artist"], s["track"], s["timestamp"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    scrobbles = unique

    # Sort by timestamp descending (newest first)
    scrobbles.sort(key=lambda s: s["timestamp"], reverse=True)

    # Final save with deduplication
    (DATA_DIR / "scrobbles_raw.json").write_text(
        json.dumps(scrobbles, separators=(",", ":"))
    )

    console.print(
        f"\n[bold green]Done![/bold green] "
        f"Exported [cyan]{len(scrobbles):,}[/cyan] unique scrobbles "
        f"to data/scrobbles_raw.json"
    )


def update_main() -> None:
    """Fetch only new scrobbles since last export."""
    if not API_KEY:
        console.print("[red]Error: LASTFM_API_KEY not set in .env[/red]")
        sys.exit(1)

    raw_file = DATA_DIR / "scrobbles_raw.json"
    if not raw_file.exists():
        console.print("[red]No existing scrobbles_raw.json found. Run full export first.[/red]")
        sys.exit(1)

    existing = json.loads(raw_file.read_text())
    console.print(f"Loaded [cyan]{len(existing):,}[/cyan] existing scrobbles")

    # Data is sorted newest-first, so first entry has the latest timestamp
    latest_ts = max(s["timestamp"] for s in existing)
    console.print(f"Latest scrobble: [cyan]{latest_ts}[/cyan] ({time.strftime('%Y-%m-%d %H:%M', time.gmtime(latest_ts))})")

    new_scrobbles: list[dict] = []
    with httpx.Client() as client:
        console.print(f"[bold]Fetching new scrobbles for [cyan]{USERNAME}[/cyan] since {time.strftime('%Y-%m-%d', time.gmtime(latest_ts))}...[/bold]")
        page = 1
        while True:
            data = fetch_page(client, page, **{"from": latest_ts + 1})
            tracks = data.get("recenttracks", {}).get("track", [])
            if not tracks:
                break
            page_count = 0
            for track in tracks:
                s = parse_scrobble(track)
                if s:
                    new_scrobbles.append(s)
                    page_count += 1

            attrs = data["recenttracks"]["@attr"]
            total_pages = int(attrs["totalPages"])
            console.print(f"  Page {page}/{total_pages} — {page_count} scrobbles")

            if page >= total_pages:
                break
            page += 1
            time.sleep(RATE_DELAY)

    if not new_scrobbles:
        console.print("[green]Already up to date! No new scrobbles.[/green]")
        return

    # Merge new + existing
    merged = new_scrobbles + existing

    # Deduplicate by (artist, track, timestamp)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for s in merged:
        key = (s["artist"], s["track"], s["timestamp"])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    # Sort by timestamp descending (newest first)
    unique.sort(key=lambda s: s["timestamp"], reverse=True)

    raw_file.write_text(json.dumps(unique, separators=(",", ":")))
    console.print(
        f"\n[bold green]Done![/bold green] "
        f"Added [cyan]{len(new_scrobbles):,}[/cyan] new scrobbles. "
        f"Total: [cyan]{len(unique):,}[/cyan]"
    )


if __name__ == "__main__":
    if "--update" in sys.argv:
        update_main()
    else:
        main()
