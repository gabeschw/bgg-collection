import os
import re
import html
import tomllib
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from common import load_data, cache_path, parse_numplayers_poll

BGG_USERNAME = os.environ["BGG_USERNAME"]
REFRESH_DATA = os.environ.get("REFRESH_DATA", "true").lower() == "true"
INCLUDE_FOR_TRADE = os.environ.get("INCLUDE_FOR_TRADE", "false").lower() == "true"
OVERRIDES_FILE = os.environ.get("OVERRIDES_FILE", "overrides.toml")

def _as_list(field):
    if field is None or isinstance(field, float):
        return []
    return field if isinstance(field, list) else [field]

def _names(field, limit=None, sep=', ', more='+'):
    texts = [i['#text'] for i in _as_list(field) if isinstance(i, dict) and i.get('#text')]
    if not texts:
        return ''
    if limit and len(texts) > limit:
        return sep.join(texts[:limit]) + ' ' + more
    return sep.join(texts)

def _primary_name(field):
    items = _as_list(field)
    for i in items:
        if isinstance(i, dict) and i.get('@primary') == 'true':
            return i.get('#text', '')
    return items[0].get('#text', '') if items and isinstance(items[0], dict) else ''

def load_overrides(path=OVERRIDES_FILE):
    """Load per-game overrides keyed by object id, e.g. {'130176': {'name': ...}}."""
    try:
        with open(path, 'rb') as f:
            return tomllib.load(f).get('overrides', {})
    except FileNotFoundError:
        return {}

def _clean_name(name):
    """Trim a trailing "(...)" parenthetical from a name.

    Keeps the part before the parens when it has Latin letters (drops edition/
    disambiguation notes); otherwise uses the parenthetical, which is how a
    non-Latin primary name shows its English title,
    e.g. "白と黒でトリテ (Trick-Taking in Black and White)".
    """
    m = re.match(r'^(.*?)\s*\(([^()]*)\)\s*$', name)
    if not m:
        return name
    head, paren = m.group(1).strip(), m.group(2).strip()
    return head if re.search(r'[A-Za-z]', head) else paren

def _collection_name(item):
    name = item.get('name')
    return name.get('#text') if isinstance(name, dict) else (name or '')

def display_name(game, item, overrides):
    """Prefer an explicit override, then the owned edition's name (what BGG shows
    for the collection item), then the game's canonical name."""
    override = overrides.get(game['@objectid'], {}).get('name')
    if override:
        return override
    return _clean_name(_collection_name(item) or _primary_name(game.get('name')))

def _owned_publisher(item):
    """First publisher of the owned edition, from the version's links (blank if none)."""
    version = item.get('version', {}).get('item') or {}
    pubs = [l['@value'] for l in _as_list(version.get('link'))
            if isinstance(l, dict) and l.get('@type') == 'boardgamepublisher' and l.get('@value')]
    if not pubs:
        return ''
    return pubs[0] + ' +' if len(pubs) > 1 else pubs[0]

def _published(game, item):
    """Original release year, adding the owned edition's year when it differs,
    e.g. "1994 (2011 ed.)"."""
    original = str(game.get('yearpublished') or '')
    owned = str(item.get('yearpublished') or '')
    if owned and owned != original:
        return f'{original} ({owned} ed.)' if original else owned
    return original

def _clean(text):
    return re.sub(r'\s+', ' ', html.unescape(text or '').replace('\n', ' ')).strip()

def _description(desc, max_len=900):
    text = _clean(desc)
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0].rstrip(',.;:') + '…'
    return text

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

def build_card(game, item, overrides):
    # Identity fields (name, image, year, publisher) reflect the owned edition
    # via the collection item; the rest comes from the game's canonical data.
    ratings = game.get('statistics', {}).get('ratings', {})
    return {
        'id':          game['@objectid'],
        'name':        display_name(game, item, overrides),
        'url':         f"https://boardgamegeek.com/boardgame/{game['@objectid']}",
        'image':       item.get('image') or game.get('image') or game.get('thumbnail') or '',
        'players':     _players(game),
        'rec_players': _recommended_players(game),
        'time':        game.get('playingtime') or '',
        'description': _description(game.get('description')),
        'published':   _published(game, item),
        'publisher':   _owned_publisher(item) or _names(game.get('boardgamepublisher'), limit=1),
        'designer':    _names(game.get('boardgamedesigner'), limit=2),
        'theme':       _names(game.get('boardgamecategory'), limit=3),
        'mechanics':   _names(game.get('boardgamemechanic'), limit=3),
        'weight':      _round1(ratings.get('averageweight')),
    }

if __name__ == "__main__":
    data = load_data(BGG_USERNAME, refresh=REFRESH_DATA, include_for_trade=INCLUDE_FOR_TRADE)
    games_list = data['games']
    items = {i['@objectid']: i for i in _as_list(data['collection']['items']['item'])}

    data_date = datetime.fromtimestamp(os.path.getmtime(cache_path(BGG_USERNAME))).strftime('%b %d %Y')

    overrides = load_overrides()
    cards = [build_card(g, items.get(g['@objectid'], {}), overrides) for g in games_list]
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
