# AGENTS.md

## Project

Downloads a BGG user's board game collection via the BoardGameGeek XML API, enriches each game with stats, and generates a printable HTML report plus CSV.

## Commands

```bash
uv run python create_collection_html.py    # main script
uv sync                                    # install dependencies
```

There are no tests, lint, or CI.

## Architecture

- **Main script**: `create_collection_html.py` — runs the full pipeline (download → merge → HTML/CSV output). `main.py` is a placeholder stub.
- **Output**: `output/collection_{username}.html` and `.csv` (gitignored).
- **Caching**: `games_list.pickle` caches downloaded game data; toggle with `REFRESH_GAME_DATA` flag.
- **Template**: `collection_template.html` uses `string.Template` (`$bgg_username`, `$last_update_date`, `$html`).

## Gotchas

- **Package manager**: `uv`. The lockfile is `uv.lock`. Do not use pip/conda.
- **Python version**: 3.12 (`.python-version`).
- **Env vars**: `BGG_USERNAME` and `BGG_API_TOKEN` are required (raises `KeyError` if missing). `REFRESH_GAME_DATA` defaults to `true`. Copy `.env.example` to `.env` and fill in your values — `uv run` loads `.env` automatically.
- **Notebooks**: `.ipynb` files are exploratory; the script is the authoritative pipeline.
- **Rate limiting**: The script sleeps 2s between per-game API calls; handles HTTP 202 retries.