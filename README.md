# lastfm-export

Export your Last.fm scrobbles and generate an interactive statistics page.

## Setup

```bash
cp .env.example .env
# Fill in your Last.fm API key
uv sync
```

## Usage

```bash
uv run export.py        # Export scrobbles to data/
uv run generate_stats.py # Generate stats
open index.html          # View interactive report
```

## License

MIT
