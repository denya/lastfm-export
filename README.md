# lastfm-export

Export your Last.fm scrobbles and generate an interactive statistics dashboard.

**Features:**
- Full scrobble history export via Last.fm API
- Incremental updates — fetch only new scrobbles since last export
- Resumable — checkpoints every 10 pages, safe to interrupt and restart
- Pre-aggregated stats: yearly/monthly/weekly/hourly breakdowns, top artists/tracks/albums per year, listening patterns, loved tracks
- Interactive HTML viewer with dark/light mode, ECharts charts, year filtering, and drill-down data

## Setup

```bash
uv sync
uv run setup.py   # interactive — prompts for API key & username, validates them
```

Or manually: `cp .env.example .env` and fill in your values.

## Usage

```bash
uv run export.py             # Full export (first time)
uv run export.py --update    # Incremental update (only new scrobbles)
uv run generate_stats.py     # Generate stats from exported data
open index.html              # View interactive report
```

## Screenshots

### Year overview (2014)
![2014 stats overview](screenshots/2014-overview.jpg)

### Top artists & tracks (2014)
![2014 top artists and tracks](screenshots/2014-top-artists-tracks.jpg)

### Listening patterns (2014)
![2014 listening patterns](screenshots/2014-listening-patterns.jpg)

## License

MIT
