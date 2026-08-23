"""Render a full-bleed box-art mosaic cover from the collection to output/cover_<username>.html.

A decorative title page: every game's cover fills a tight grid across one A4 sheet,
with a frosted title panel overlaid in the middle. Used as the cover for the
reference guide. Requires the local image cache from --local-images.
"""
import os
import random
import sys

import click
from jinja2 import Environment, FileSystemLoader, select_autoescape

import common


@click.command()
@click.argument('username')
@click.option('--cols', type=int, default=None,
              help='Number of mosaic columns (the aligned rows are derived; the sorted '
                   'tail of games is dropped so every row stays full)')
@click.option('--rows', type=int, default=None,
              help='Number of mosaic rows (overrides --cols when set)')
@click.option('--title', default='Game Reference',
              help='Cover title text')
@click.option('--subtitle', type=str, default=None,
              help='Cover subtitle line (default: "<user> · N games · last updated <date>")')
@click.option('--sorting', type=click.Choice(['alpha', 'rating', 'random']), default='random',
              help='Tile ordering: alpha (default), rating, or random')
@click.option('--seed', type=int, default=None,
              help='Random seed for reproducible --sorting random')
@click.option('--include-for-trade', is_flag=True, default=False,
              help='Include games marked For Trade in BGG')
def main(username, cols, rows, title, subtitle, sorting, seed, include_for_trade):
    """Render a box-art mosaic cover page to output/cover_<username>.html."""
    data = common.load_data(username, refresh=False)
    games_list = data['games']
    items = {i['@objectid']: i for i in common.as_list(data['collection']['items']['item'])}
    if not include_for_trade:
        games_list = [g for g in games_list if (items.get(g['@objectid'], {}).get('status') or {}).get('@fortrade') != '1']
    if not games_list:
        sys.exit('No games to render.')

    overrides = common.load_overrides()
    descriptions = common.load_descriptions()
    cards = [common.build_card(g, items.get(g['@objectid'], {}), overrides, descriptions)
             for g in games_list]
    image_map = common.prepare_local_images(games_list, items, username)
    cards = [c for c in cards if c['id'] in image_map]
    if not cards:
        sys.exit('No local cover images were available.')

    if sorting == 'rating':
        cards.sort(key=lambda c: c['id'])
        cards.sort(key=lambda c: _rating(c['id'], items), reverse=True)
    elif sorting == 'random':
        rng = random.Random(seed)
        cards = sorted(cards, key=lambda c: rng.random())
    else:
        cards.sort(key=lambda c: c['name'].lower())

    for c in cards:
        c['image'] = image_map[c['id']]

    # Pick a grid that fills every row: capacity = cols*rows, then trim the
    # sorted tail so the last row never runs short.
    n = len(cards)
    if cols and rows:
        pass
    elif rows:
        rows = min(rows, n)
        cols = n // rows or 1
    elif cols:
        cols = min(cols, n)
        rows = n // cols or 1
    else:
        cols, rows = _mosaic_dims(n)
    if cols * rows > n:
        rows = min(rows, max(1, n // cols))
    tiles = cols * rows
    # Drop only when capacity exceeds tile count (the sorted tail).
    if tiles < n:
        cards = cards[:tiles]

    env = Environment(
        loader=FileSystemLoader('templates'),
        autoescape=select_autoescape(['html']),
    )
    template = env.get_template('cover.html')
    rendered = template.render(
        bgg_username=username,
        title=title,
        subtitle=subtitle,
        card_count=len(cards),
        last_update_date=common.cache_date(username),
        cols=cols,
        rows=rows,
        cards=cards,
    )

    os.makedirs('output', exist_ok=True)
    with open(f'output/cover_{username}.html', 'w') as f:
        f.write(rendered)
    dropped = n - tiles
    note = f' ({dropped} dropped)' if dropped else ''
    print(f'Wrote output/cover_{username}.html ({tiles} tiles, {cols}x{rows}{note})')


def _mosaic_dims(n, ideal=1.414):
    """Pick cols x rows (product <= n) closest to a full, square-ish grid."""
    best = None
    for cols in range(1, int(ideal * (n ** 0.5)) + 2):
        rows = n // cols or 1
        cap = cols * rows
        if cap > n:
            rows -= 1
            cap = cols * rows
        if cap == 0:
            continue
        loss = n - cap
        dev = abs(rows / cols - ideal)
        if best is None or (loss + 20 * dev) < (best[0] + 20 * best[1]):
            best = (loss, dev, cols, rows)
    return best[2], best[3]


def _rating(gid, items):
    """Personal rating for a game (-1 when unrated) to sort the mosaic by."""
    try:
        return float(items.get(gid, {}).get('stats', {}).get('rating', {}).get('@value'))
    except (TypeError, ValueError):
        return -1.0


if __name__ == "__main__":
    main()