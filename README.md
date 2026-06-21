# bgg-collection

Downloads a BGG user's board game collection and generates a printable HTML report plus CSV.

```bash
uv run python create_collection_html.py
```

## Report Columns

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

![Powered by BGG](bgg.png)
