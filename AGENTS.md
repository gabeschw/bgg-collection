# AGENTS.md

## Project

Downloads a BGG user's board game collection via the BoardGameGeek XML API, enriches each game with stats, and generates a printable HTML report plus CSV.

## Commands

```bash
uv run python create_collection_html.py    # main script
uv sync                                    # install dependencies
```

No tests, lint, or CI.

## Architecture

- **Single script**: `create_collection_html.py` runs the full pipeline (download → merge → HTML/CSV output).
- **Output**: `output/collection_{username}.html` and `.csv` (gitignored).
- **Caching**: `games_list.pickle` caches enriched game data; delete it or set `REFRESH_GAME_DATA=true` to re-download.
- **Template**: `collection_template.html` uses `string.Template` (`$bgg_username`, `$last_update_date`, `$html`).

## Gotchas

- **Package manager**: `uv`. Lockfile is `uv.lock`. Do not use pip/conda.
- **Python version**: 3.12 (`.python-version`).
- **Env vars**: `BGG_USERNAME` and `BGG_API_TOKEN` are required (raises `KeyError` if missing). `REFRESH_GAME_DATA` defaults to `true`. Copy `.env.example` to `.env` — `uv run` loads `.env` automatically.
- **Batching**: Per-game API calls are batched 20 per request (`BGG_BATCH_SIZE = 20`). Script sleeps 2s between batches. Setting is 20 because BGG enforces that maximum.
- **Pickle format**: `games_list.pickle` stores flat game dicts (not wrapped response objects). Old pickle files from before the batching change are incompatible — delete and re-download.
- **Notebooks**: `.ipynb` files are exploratory; the script is the authoritative pipeline.
