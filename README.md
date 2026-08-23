# bgg-collection

Fetch a BoardGameGeek user's collection and turn it into printable documents:

- **Cover page** — full-bleed box-art mosaic title page (`build_cover.py`).
- **Reference guide** — magazine-style card per game with art, stats, and blurbs (`build_reference.py`).
- **Collection report** — compact tables grouped by player counts, designer, and title (`build_collection.py`).
- **Combined PDF** — merge cover, reference, and collection into one PDF (`print_pdf.sh`).

## Setup

Copy `.env.example` to `.env` and fill in your BGG API token, then install dependencies:

```bash
uv sync
```

Scripts pull data from BGG and cache it to `cache/<username>.json`. Pass `--refresh-data` to re-fetch from the API; otherwise builds run offline from the cache (no token or network needed).

## Quick Start

```bash
# 1. Fetch collection & build HTML documents
uv run python build_collection.py <username> --refresh-data
uv run python build_reference.py <username> --local-images
uv run python build_cover.py <username>

# 2. Export combined PDF (cover -> reference -> collection)
./print_pdf.sh <username>
```

## Collection report

`build_collection.py` downloads the collection from BGG and writes `output/collection_<username>.html` (plus a CSV), with tables grouped by recommended player counts (1 to 7+), designer, and an alphabetical list.

```bash
uv run python build_collection.py <username> [--refresh-data] [--include-for-trade]
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

`build_reference.py` renders a magazine-style color reference — one card per game with box art, publisher, designer, theme, mechanics, recommended player counts, complexity, QR code to BGG, and summary blurb — laid out four per portrait A4 page. Output goes to `output/reference_<username>.html`.

```bash
uv run python build_reference.py <username> [--local-images] [--refresh-data] [--include-for-trade]
```

Pass `--local-images` to download and shrink images to 600px JPEGs in `output/<username>_images/`, keeping the output PDF size manageable.

### Cover page

`build_cover.py` renders a full-bleed box-art mosaic — one tile per game, keeping every row full — with a frosted title panel as a decorative cover for the reference guide. It reuses the local image cache from `--local-images`.

```bash
uv run python build_cover.py <username> [--cols N] [--rows N] [--title "..."] [--sorting alpha|rating|random] [--seed N] [--include-for-trade]
```

Grid dimensions auto-size to A4's portrait aspect with square-ish cells (e.g. 320 games → 16×20); pass `--cols` or `--rows` to pin one axis. Output goes to `output/cover_<username>.html`.

### PDF export

`print_pdf.sh` renders the HTML files via headless Chrome and merges them with `pdfunite` into a single combined PDF (`output/<username>.pdf`), ordered as cover → reference cards → collection report:

```bash
./print_pdf.sh <username>
```

You can also specify individual sections: `./print_pdf.sh <username> cover reference`.

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
