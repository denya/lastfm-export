"""Generate pre-aggregated stats from scrobbles_raw.json → data/stats.js.

Output format: window.LASTFM_STATS = { meta, yearly, monthly, weekly,
daily_counts, top_artists, top_tracks, top_albums, hourly, dow, loved }
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

DATA_DIR = Path(__file__).parent / "data"
console = Console()


def load_scrobbles() -> list[dict]:
    raw = DATA_DIR / "scrobbles_raw.json"
    if not raw.exists():
        console.print("[red]Error: data/scrobbles_raw.json not found. Run export.py first.[/red]")
        raise SystemExit(1)
    scrobbles = json.loads(raw.read_text())
    console.print(f"Loaded [cyan]{len(scrobbles):,}[/cyan] scrobbles")
    return scrobbles


def ts_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def generate(scrobbles: list[dict]) -> dict:
    # Prepare counters
    yearly_counts: Counter = Counter()
    monthly_counts: Counter = Counter()
    weekly_counts: Counter = Counter()
    daily_counts: Counter = Counter()
    hourly_counts: Counter = Counter()
    dow_counts: Counter = Counter()

    yearly_artists: dict[str, set] = defaultdict(set)
    yearly_tracks: dict[str, set] = defaultdict(set)
    yearly_albums: dict[str, set] = defaultdict(set)

    overall_artists: Counter = Counter()
    overall_tracks: Counter = Counter()
    overall_albums: Counter = Counter()

    yearly_artist_counts: dict[str, Counter] = defaultdict(Counter)
    yearly_track_counts: dict[str, Counter] = defaultdict(Counter)
    yearly_album_counts: dict[str, Counter] = defaultdict(Counter)

    all_artists: set = set()
    all_tracks: set = set()
    all_albums: set = set()

    loved_tracks: list[dict] = []

    # Artist image map (best available)
    artist_images: dict[str, str] = {}

    for s in scrobbles:
        dt = ts_to_dt(s["timestamp"])
        year = str(dt.year)
        month = dt.strftime("%Y-%m")
        week = dt.strftime("%G-W%V")
        day = dt.strftime("%Y-%m-%d")
        hour = dt.hour
        dow = dt.weekday()  # 0=Mon

        yearly_counts[year] += 1
        monthly_counts[month] += 1
        weekly_counts[week] += 1
        daily_counts[day] += 1
        hourly_counts[hour] += 1
        dow_counts[dow] += 1

        artist = s["artist"]
        track = s["track"]
        album = s["album"]
        artist_track = f"{artist} — {track}"
        artist_album = f"{artist} — {album}" if album else ""

        all_artists.add(artist)
        all_tracks.add(artist_track)
        if album:
            all_albums.add(artist_album)

        yearly_artists[year].add(artist)
        yearly_tracks[year].add(artist_track)
        if album:
            yearly_albums[year].add(artist_album)

        overall_artists[artist] += 1
        overall_tracks[artist_track] += 1
        if album:
            overall_albums[artist_album] += 1

        yearly_artist_counts[year][artist] += 1
        yearly_track_counts[year][artist_track] += 1
        if album:
            yearly_album_counts[year][artist_album] += 1

        if s.get("image_url") and artist and artist not in artist_images:
            artist_images[artist] = s["image_url"]

        if s.get("loved"):
            loved_tracks.append({
                "artist": artist,
                "track": track,
                "album": album,
                "timestamp": s["timestamp"],
            })

    # Build output
    years_sorted = sorted(yearly_counts.keys())
    timestamps = [s["timestamp"] for s in scrobbles if s["timestamp"]]
    min_ts = min(timestamps) if timestamps else 0
    max_ts = max(timestamps) if timestamps else 0

    meta = {
        "total_scrobbles": len(scrobbles),
        "unique_artists": len(all_artists),
        "unique_tracks": len(all_tracks),
        "unique_albums": len(all_albums),
        "loved_count": len(loved_tracks),
        "first_scrobble": min_ts,
        "last_scrobble": max_ts,
        "years": years_sorted,
    }

    yearly = []
    for y in years_sorted:
        yearly.append({
            "year": y,
            "scrobbles": yearly_counts[y],
            "unique_artists": len(yearly_artists.get(y, set())),
            "unique_tracks": len(yearly_tracks.get(y, set())),
            "unique_albums": len(yearly_albums.get(y, set())),
        })

    monthly = [
        {"month": m, "count": monthly_counts[m]}
        for m in sorted(monthly_counts.keys())
    ]

    weekly = [
        {"week": w, "count": weekly_counts[w]}
        for w in sorted(weekly_counts.keys())
    ]

    daily = [
        {"date": d, "count": daily_counts[d]}
        for d in sorted(daily_counts.keys())
    ]

    hourly = [hourly_counts.get(h, 0) for h in range(24)]

    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow = [{"day": dow_names[d], "count": dow_counts.get(d, 0)} for d in range(7)]

    def top_n(counter: Counter, n: int) -> list[dict]:
        return [
            {"name": name, "count": count}
            for name, count in counter.most_common(n)
        ]

    def top_n_per_year(yearly_counter: dict[str, Counter], n: int) -> dict:
        return {
            year: top_n(counter, n)
            for year, counter in sorted(yearly_counter.items())
        }

    top_artists = {
        "overall": top_n(overall_artists, 100),
        "by_year": top_n_per_year(yearly_artist_counts, 50),
    }

    top_tracks = {
        "overall": top_n(overall_tracks, 100),
        "by_year": top_n_per_year(yearly_track_counts, 50),
    }

    top_albums = {
        "overall": top_n(overall_albums, 100),
        "by_year": top_n_per_year(yearly_album_counts, 50),
    }

    # Per-artist yearly trend (for top 20 artists)
    artist_trends = {}
    for name, _ in overall_artists.most_common(20):
        artist_trends[name] = {
            y: yearly_artist_counts[y].get(name, 0) for y in years_sorted
        }

    stats = {
        "meta": meta,
        "yearly": yearly,
        "monthly": monthly,
        "weekly": weekly,
        "daily_counts": daily,
        "top_artists": top_artists,
        "top_tracks": top_tracks,
        "top_albums": top_albums,
        "artist_trends": artist_trends,
        "artist_images": {
            name: artist_images.get(name, "")
            for name, _ in overall_artists.most_common(100)
        },
        "hourly": hourly,
        "dow": dow,
        "loved": loved_tracks,
    }

    return stats


def generate_scrobbles_js(scrobbles: list[dict]) -> None:
    """Generate string-interned scrobbles.js for drill-down data."""
    artist_to_idx: dict[str, int] = {}
    track_to_idx: dict[str, int] = {}
    album_to_idx: dict[str, int] = {}
    artists: list[str] = []
    tracks: list[str] = []
    albums: list[str] = []

    def get_idx(value: str, lookup: dict[str, int], arr: list[str]) -> int:
        if value not in lookup:
            lookup[value] = len(arr)
            arr.append(value)
        return lookup[value]

    encoded: list[list] = []
    for s in scrobbles:
        ai = get_idx(s["artist"], artist_to_idx, artists)
        ti = get_idx(s["track"], track_to_idx, tracks)
        li = get_idx(s.get("album", ""), album_to_idx, albums)
        entry = [ai, ti, li, s["timestamp"]]
        if s.get("loved"):
            entry.append(1)
        encoded.append(entry)

    data = {"a": artists, "t": tracks, "l": albums, "s": encoded}
    output = DATA_DIR / "scrobbles.js"
    js = "window.LASTFM_SCROBBLES=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
    output.write_text(js, encoding="utf-8")

    size_mb = output.stat().st_size / (1024 * 1024)
    console.print(
        f"  scrobbles.js:    [cyan]{size_mb:.1f} MB[/cyan] "
        f"({len(artists):,} artists, {len(tracks):,} tracks, {len(albums):,} albums)"
    )


def main() -> None:
    scrobbles = load_scrobbles()
    console.print("Generating stats...")
    stats = generate(scrobbles)

    output = DATA_DIR / "stats.js"
    js = "window.LASTFM_STATS = " + json.dumps(stats, separators=(",", ":")) + ";\n"
    output.write_text(js)

    size_kb = output.stat().st_size / 1024
    console.print(
        f"[bold green]Done![/bold green] "
        f"stats.js: [cyan]{size_kb:.0f} KB[/cyan]"
    )
    console.print(f"  Total scrobbles: [cyan]{stats['meta']['total_scrobbles']:,}[/cyan]")
    console.print(f"  Unique artists:  [cyan]{stats['meta']['unique_artists']:,}[/cyan]")
    console.print(f"  Unique tracks:   [cyan]{stats['meta']['unique_tracks']:,}[/cyan]")
    console.print(f"  Loved tracks:    [cyan]{stats['meta']['loved_count']:,}[/cyan]")
    console.print(f"  Date range:      [cyan]{stats['meta']['years'][0]}[/cyan] – [cyan]{stats['meta']['years'][-1]}[/cyan]")

    console.print("Generating scrobbles.js (string-interned)...")
    generate_scrobbles_js(scrobbles)


if __name__ == "__main__":
    main()
