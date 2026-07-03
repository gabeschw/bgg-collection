# bgg-collection

Fetch a BoardGameGeek user's collection and turn it into two printable documents:

- **Collection report** — a compact, sortable table of the whole collection (`build_collection.py`).
- **Reference guide** — a magazine-style card per game (`build_reference.py`).

## Setup

Copy `.env.example` to `.env` and fill in your BGG username and API token, then install dependencies:

```bash
uv sync
```

Both scripts pull the same data from BGG and cache it to `cache/<username>.json`. Set `REFRESH_DATA=false` to render from that cache without hitting the API (no token or network needed); leave it `true` to re-pull.

## Collection report

`build_collection.py` downloads the collection from BGG and writes `output/collection_<username>.html` (plus a CSV), caching the raw collection + game data to `cache/<username>.json`.

```bash
uv run python build_collection.py
```

| Column | Description |
|--------|-------------|
| Name | Game title |
| Time | Playing time in minutes |
| Players | Player counts where the game is recommended. For example, `_234_____` = good at 2–4 players. |
| Weight | Complexity from BGG, 1 (light) to 5 (heavy) |
| Year | Publication year |
| Designer | Game designer |
| BGG Rank | Overall rank on BGG |
| BGG Avg | Community rating on BGG (1–10) |
| Rating | Your personal rating (1–10) |
| # Plays | Number of times played |

## Reference guide

`build_reference.py` renders a print-ready, magazine-style color reference — one card per game with box art, publisher/designer/theme/mechanics, recommended player counts, and complexity — laid out four to a portrait Letter page. Output goes to `output/reference_<username>.html`.

```bash
uv run python build_reference.py
```

It uses the same `cache/<username>.json`, so it can run before or after the collection report — whichever runs first with `REFRESH_DATA=true` populates the cache. When printing to PDF, enable "Background graphics" so the colored elements render.

### Name overrides

Game names too long to fit on a card line can be shortened in `overrides.toml`, keyed by BGG object id. Trailing `(...)` parentheticals are trimmed automatically; colon subtitles need a manual choice. Each run prints the ids of names that may not fit, ready to paste in:

```toml
[overrides."130176"]  # Tales & Games: The Hare & the Tortoise
name = "The Hare & the Tortoise"
```

![Powered by BGG](bgg.png)
