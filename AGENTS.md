# AGENTS.md

## Project

Downloads a BGG user's board game collection via the BoardGameGeek XML API, enriches each game with stats, and generates two printable documents: a **collection report** (sortable HTML table + CSV) and a **reference guide** (magazine-style card per game).

## Commands

```bash
uv run python build_collection.py    # download + collection report (run this first)
uv run python build_reference.py     # reference guide (reads games_list.pickle)
uv sync                              # install dependencies (add --extra notebook for the notebook)
```

No tests, lint, or CI.

## Architecture

- **`build_collection.py`**: full pipeline (download → merge → HTML/CSV output). Caches raw game data to `games_list.pickle`.
- **`build_reference.py`**: reads `games_list.pickle` (so `build_collection.py` must run first) and renders one card per game. `overrides.toml` supplies per-game display-name overrides keyed by BGG object id.
- **`common.py`**: shared BGG parsing (recommended-players poll logic) used by both scripts.
- **Templates**: `templates/collection.html` and `templates/reference.html`, both Jinja2 (`build_reference.py` renders with `autoescape`; `build_collection.py` passes pre-rendered tables via `{{ ... | safe }}`).
- **Output**: `output/collection_{username}.html`/`.csv` and `output/reference_{username}.html` (all gitignored).
- **Caching**: `games_list.pickle` caches enriched game data; delete it or set `REFRESH_GAME_DATA=true` to re-download.

## Gotchas

- **Package manager**: `uv`. Lockfile is `uv.lock`. Do not use pip/conda.
- **Python version**: 3.12 (`.python-version`).
- **Env vars**: `BGG_USERNAME` and `BGG_API_TOKEN` are required (raises `KeyError` if missing). `REFRESH_GAME_DATA` defaults to `true`. Copy `.env.example` to `.env` — `uv run` loads `.env` automatically.
- **Batching**: Per-game API calls are batched 20 per request (`BGG_BATCH_SIZE = 20`). Script sleeps 2s between batches. Setting is 20 because BGG enforces that maximum.
- **Pickle format**: `games_list.pickle` stores flat game dicts (not wrapped response objects). Old pickle files from before the batching change are incompatible — delete and re-download.
- **Notebooks**: `.ipynb` files are exploratory; the script is the authoritative pipeline.
