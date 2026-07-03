# AGENTS.md

## Project

Downloads a BGG user's board game collection via the BoardGameGeek XML API, enriches each game with stats, and generates two printable documents: a **collection report** (sortable HTML table + CSV) and a **reference guide** (magazine-style card per game).

## Commands

```bash
uv run python build_collection.py    # collection report (fetches if needed)
uv run python build_reference.py     # reference guide (fetches if needed)
uv sync                              # install dependencies (add --extra notebook for the notebook)
```

No tests, lint, or CI.

## Architecture

- **`common.py`**: shared data + parsing layer. `load_data(username, refresh, include_for_trade)` fetches the collection + games from BGG and caches them, or reads the cache; also holds the recommended-players poll parsing. The API token is read lazily, so cache-only reads need no credentials.
- **`build_collection.py`**: calls `load_data`, then merges/derives columns with pandas and renders the collection HTML + CSV.
- **`build_reference.py`**: calls `load_data`, then renders one card per game. `overrides.toml` supplies per-game display-name overrides keyed by BGG object id.
- **Data cache**: `cache/<username>.json` holds the raw API responses `{"collection": ..., "games": [...]}`. Either script populates it; `REFRESH_DATA=true` (or a missing cache) triggers a fetch, otherwise both render from the cache offline.
- **Templates**: `templates/collection.html` and `templates/reference.html`, both Jinja2 (`build_reference.py` renders with `autoescape`; `build_collection.py` passes pre-rendered tables via `{{ ... | safe }}`).
- **Output**: `output/collection_{username}.html`/`.csv` and `output/reference_{username}.html` (all gitignored).

## Gotchas

- **Package manager**: `uv`. Lockfile is `uv.lock`. Do not use pip/conda.
- **Python version**: 3.12 (`.python-version`).
- **Env vars**: `BGG_USERNAME` is required; `BGG_API_TOKEN` is required only when fetching (cache reads don't need it). `REFRESH_DATA` defaults to `true`. Copy `.env.example` to `.env` — `uv run` loads `.env` automatically.
- **Batching**: Per-game API calls are batched 20 per request (`BGG_BATCH_SIZE = 20` in `common.py`), sleeping 2s between batches. 20 is BGG's enforced maximum.
- **Notebooks**: `.ipynb` files are exploratory; the scripts are the authoritative pipeline.
