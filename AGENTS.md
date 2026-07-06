# AGENTS.md

## Project

Downloads a BGG user's board game collection via the BoardGameGeek XML API, enriches each game with stats, and generates two printable documents: a **collection report** (sortable HTML table + CSV) and a **reference guide** (magazine-style card per game). An optional step rewrites each game's description with an LLM.

## Commands

```bash
uv run python build_collection.py <username>     # collection report
uv run python build_reference.py <username>      # reference guide
uv run python build_descriptions.py <username>   # (re)generate LLM card descriptions
uv sync                                           # install dependencies
```

Both `build_collection.py` and `build_reference.py` accept `--refresh-data` and `--include-for-trade` flags:
```bash
uv run python build_collection.py gabeschw --refresh-data --include-for-trade
```

No tests, lint, or CI.

## Architecture

- **`common.py`**: shared data + parsing layer. `load_data(username, refresh)` fetches the collection + games from BGG and caches them, or reads the cache; also holds recommended-players poll parsing, name resolution (`display_name`, `names`, `clean_text`, …), and the `_descriptions.json` reader/writer. The API token is read lazily, so cache-only reads need no credentials.
- **`build_collection.py`**: calls `load_data`, then merges/derives columns with pandas and renders the collection HTML + CSV.
- **`build_reference.py`**: calls `load_data`, then renders one card per game. A card's description resolves as `overrides.toml` `description` → archived `_descriptions.json` → cleaned/truncated BGG text. `overrides.toml` also supplies name overrides (`name` = everywhere, `short` = card-only) keyed by object id.
- **`build_descriptions.py`**: the only script that calls an LLM (`pydantic-ai` via OpenRouter). Reads the cache, rewrites each game's description within a character ceiling using a retry loop, and archives them to `_descriptions.json` (keyed by object id; regenerated only when the source text, `PROMPT_VERSION`, or model changes).
- **Data cache**: `cache/<username>.json` holds the raw API responses `{"collection": ..., "games": [...]}`. `build_collection`/`build_reference` populate it; pass `--refresh-data` (or a missing cache) triggers a fetch, otherwise they render from the cache offline. `_descriptions.json` is a separate generated artifact.
- **Templates**: `templates/collection.html` and `templates/reference.html`, both Jinja2 (`build_reference.py` renders with `autoescape`; `build_collection.py` passes pre-rendered tables via `{{ ... | safe }}`).
- **Output**: `output/collection_{username}.html`/`.csv` and `output/reference_{username}.html` (all gitignored).

## Gotchas

- **Package manager**: `uv`. Lockfile is `uv.lock`. Do not use pip/conda.
- **Python version**: 3.12 (`.python-version`).
- **CLI options**: `username` is a required positional argument. `--refresh-data` (fetch fresh data from BGG) and `--include-for-trade` (include for-trade games) are optional flags, both defaulting to `false`.
- **Env vars**: `BGG_API_TOKEN` is required only when fetching (cache reads don't need it). `LLM_API_KEY` (+ optional `LLM_MODEL`) is needed only by `build_descriptions.py`. Copy `.env.example` to `.env` — `uv run` loads `.env` automatically (a notebook must load it itself).
- **Batching**: Per-game API calls are batched 20 per request (`BGG_BATCH_SIZE = 20` in `common.py`), sleeping 2s between batches. 20 is BGG's enforced maximum.
- **Notebooks**: `.ipynb` files are exploratory; the scripts are the authoritative pipeline.
