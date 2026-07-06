# bgg-collection

Fetch a BoardGameGeek user's collection and turn it into two printable documents:

- **Collection report** — a compact, sortable table of the whole collection (`build_collection.py`).
- **Reference guide** — a magazine-style card per game (`build_reference.py`).

## Setup

Copy `.env.example` to `.env` and fill in your BGG API token, then install dependencies:

```bash
uv sync
```

Both scripts pull the same data from BGG and cache it to `cache/<username>.json`. Pass `--refresh-data` to re-pull from the API; otherwise they render from the cache offline (no token or network needed).

## Collection report

`build_collection.py` downloads the collection from BGG and writes `output/collection_<username>.html` (plus a CSV), caching the raw collection + game data to `cache/<username>.json`.

```bash
uv run python build_collection.py <username>
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
uv run python build_reference.py <username>
```

It uses the same `cache/<username>.json`, so it can run before or after the collection report — whichever runs first with `--refresh-data` populates the cache. Print to PDF straight from the browser; backgrounds are forced on via CSS, so no print-dialog tweaks are needed.

### Card descriptions

Card descriptions come from `_descriptions.json`, generated separately by an LLM (see below); if a game has no entry, the cleaned/truncated BGG description is used as a fallback.

### Overrides

`overrides.toml` holds per-game display overrides keyed by BGG object id:

- `name` — used everywhere (collection report and card); for fixing a name, e.g. restoring the canonical title over a localized edition.
- `short` — used only on the reference card, where the name must fit one line; the collection table keeps the full name.
- `description` — a hand-written description that wins over the generated one.

Trailing `(...)` parentheticals in names are trimmed automatically.

```toml
[overrides."42"]      # owned edition: Euphrat & Tigris
name = "Tigris & Euphrates"

[overrides."284083"]  # The Crew: The Quest for Planet Nine
short = "The Crew"
```

## Descriptions (optional, LLM)

`build_descriptions.py` rewrites each game's BGG description into a consistent, length-capped (≤450 char) blurb and archives them to `_descriptions.json` (keyed by object id). It's the only script that calls an LLM (via OpenRouter), and it's run occasionally — the fast build just reads the file.

```bash
uv run python build_descriptions.py <username>
```

Set `OPENROUTER_API_KEY` and `LLM_MODEL` in `.env`. Entries regenerate only when the source description, prompt, or model changes.

![Powered by BGG](bgg.png)
