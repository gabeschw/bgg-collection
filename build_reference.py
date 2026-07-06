import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from common import (
    load_data, cache_path, parse_numplayers_poll, is_for_trade,
    display_name, load_overrides, load_descriptions, as_list, names, clean_text,
)

BGG_USERNAME = os.environ["BGG_USERNAME"]
REFRESH_DATA = os.environ.get("REFRESH_DATA", "true").lower() == "true"
INCLUDE_FOR_TRADE = os.environ.get("INCLUDE_FOR_TRADE", "false").lower() == "true"

# Personal-rating thresholds for the favorite medal, highest tier first.
FAVORITE_TIERS = [
    ('gold',   float(os.environ.get("FAVORITE_GOLD", 10))),
    ('silver', float(os.environ.get("FAVORITE_SILVER", 9))),
    ('bronze', float(os.environ.get("FAVORITE_BRONZE", 8))),
]

def _published(game, item):
    """Assemble the published/publisher line, grouping the owned edition's year with its
    publisher: "1876 · Publisher (2014 ed.)". Falls back to "year (ed.)" when there is no
    publisher, "year · publisher" when the edition year matches, or just "year".
    """
    year = str(game.get('yearpublished') or '')
    owned = str(item.get('yearpublished') or '')
    # Publisher of the owned edition (from the version's links), else the game's first.
    version = item.get('version', {}).get('item') or {}
    edition_pubs = [link['@value'] for link in as_list(version.get('link'))
                    if isinstance(link, dict) and link.get('@type') == 'boardgamepublisher' and link.get('@value')]
    if edition_pubs:
        publisher = edition_pubs[0] + (' +' if len(edition_pubs) > 1 else '')
    else:
        publisher = names(game.get('boardgamepublisher'), limit=1)
    ed = f'({owned} ed.)' if owned and owned != year else ''
    if publisher:
        publisher = f'{publisher} {ed}'.strip()   # edition year rides with the publisher
    elif ed:
        year = f'{year} {ed}'.strip()             # no publisher -> attach to the year
    return ' · '.join(p for p in (year, publisher) if p)

def _description(desc, max_len=900):
    """Fallback: cleaned BGG text, truncated at a word boundary."""
    text = clean_text(desc)
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0].rstrip(',.;:') + '…'
    return text

def _resolve_description(game, overrides, descriptions):
    """Precedence: manual override -> archived LLM description -> cleaned BGG text."""
    manual = overrides.get(game['@objectid'], {}).get('description')
    if manual:
        return clean_text(manual)
    generated = descriptions.get(game['@objectid'], {}).get('description')
    if generated:
        return generated
    return _description(game.get('description'))

def _players(game):
    lo, hi = game.get('minplayers'), game.get('maxplayers')
    if not lo or lo == '0':
        return hi or ''
    return lo if lo == hi else f'{lo}–{hi}'

def _round1(value):
    try:
        return f'{float(value):.1f}'
    except (TypeError, ValueError):
        return ''

def _recommended_players(game):
    # Comma-separated counts, e.g. "2, 3, 4"; blank when the poll recommends nothing.
    return ', '.join(str(n) for n in parse_numplayers_poll(game.get('poll')))

def _medal(item):
    """Favorite tier ('gold'/'silver'/'bronze') from the personal rating, else ''."""
    try:
        rating = float(item.get('stats', {}).get('rating', {}).get('@value'))
    except (TypeError, ValueError):
        return ''  # unrated ('N/A' or missing)
    for tier, threshold in FAVORITE_TIERS:
        if rating >= threshold:
            return tier
    return ''

def build_card(game, item, overrides, descriptions):
    # Identity fields (name, image, year, publisher) reflect the owned edition
    # via the collection item; the rest comes from the game's canonical data.
    ratings = game.get('statistics', {}).get('ratings', {})
    return {
        'id':          game['@objectid'],
        'name':        display_name(game, item, overrides, short=True),
        'url':         f"https://boardgamegeek.com/boardgame/{game['@objectid']}",
        'medal':       _medal(item),
        'image':       item.get('image') or game.get('image') or game.get('thumbnail') or '',
        'players':     _players(game),
        'rec_players': _recommended_players(game),
        'time':        game.get('playingtime') or '',
        'description': _resolve_description(game, overrides, descriptions),
        'published':   _published(game, item),
        'designer':    names(game.get('boardgamedesigner'), limit=2),
        'theme':       names(game.get('boardgamecategory'), limit=3),
        'mechanics':   names(game.get('boardgamemechanic'), limit=3),
        'weight':      _round1(ratings.get('averageweight')),
    }

if __name__ == "__main__":
    data = load_data(BGG_USERNAME, refresh=REFRESH_DATA)
    games_list = data['games']
    items = {i['@objectid']: i for i in as_list(data['collection']['items']['item'])}
    if not INCLUDE_FOR_TRADE:
        games_list = [g for g in games_list if not is_for_trade(items.get(g['@objectid'], {}))]

    data_date = datetime.fromtimestamp(os.path.getmtime(cache_path(BGG_USERNAME))).strftime('%b %d %Y')

    overrides = load_overrides()
    descriptions = load_descriptions()
    cards = [build_card(g, items.get(g['@objectid'], {}), overrides, descriptions) for g in games_list]
    cards.sort(key=lambda c: c['name'].lower())

    env = Environment(
        loader=FileSystemLoader('templates'),
        autoescape=select_autoescape(['html']),
    )
    template = env.get_template('reference.html')
    rendered = template.render(
        bgg_username=BGG_USERNAME,
        last_update_date=data_date,
        card_count=len(cards),
        cards=cards,
    )

    os.makedirs('output', exist_ok=True)
    with open(f'output/reference_{BGG_USERNAME}.html', 'w') as f:
        f.write(rendered)
    print(f'Wrote output/reference_{BGG_USERNAME}.html ({len(cards)} games)')
