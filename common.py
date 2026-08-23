"""Shared data layer for BGG collection scripts: API fetch, caching, name resolution,
poll parsing, file I/O for overrides and LLM descriptions, and reference-card assembly."""
import html
import json
import os
import re
import time
import tomllib
from io import BytesIO

import qrcode as _qrcode_lib
import qrcode.image.svg
import requests
import xmltodict
from PIL import Image
from tqdm import tqdm

# Anchor paths to this file's directory so they resolve the same from the
# scripts (run at the repo root) and from a notebook (a different cwd).
_ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_ROOT, "cache")
BGG_BATCH_SIZE = 20  # BGG's maximum per boardgame request

def _headers():
    # Read the token lazily so cache-only reads need no credentials.
    return {"Authorization": f"Bearer {os.environ['BGG_API_TOKEN']}"}

def bgg_api_to_dict(endpoint, params, retries=5):
    """Fetch from the BGG XML API 2, retrying on 202 (accepted, not yet ready)."""
    for _ in range(retries):
        r = requests.get(
            f"https://boardgamegeek.com/xmlapi2/{endpoint}",
            params=params,
            headers=_headers(),
        )
        r.raise_for_status()
        if r.status_code == 202:
            time.sleep(5)
            continue
        return xmltodict.parse(r.content)
    raise RuntimeError(f"BGG API returned 202 {retries} times for {endpoint}")

def bgg_game_to_dict(game_ids, params=None, retries=5):
    """Fetch per-game data from BGG's older xmlapi (supports batch via comma-separated IDs)."""
    if isinstance(game_ids, list):
        game_ids = ",".join(str(i) for i in game_ids)
    params = params or {}
    for _ in range(retries):
        r = requests.get(
            f"https://boardgamegeek.com/xmlapi/boardgame/{game_ids}",
            params=params,
            headers=_headers(),
        )
        r.raise_for_status()
        if r.status_code == 202:
            time.sleep(1)
            continue
        return xmltodict.parse(r.content)
    raise RuntimeError(f"BGG API returned 202 {retries} times for boardgame {game_ids}")

def cache_path(username):
    """Path to the per-user BGG cache file."""
    return os.path.join(CACHE_DIR, f"{username}.json")

def cache_date(username, fmt='%d %b %Y'):
    """Formatted mtime of a user's cache file (build date for headers/covers)."""
    from datetime import datetime
    return datetime.fromtimestamp(os.path.getmtime(cache_path(username))).strftime(fmt)

DESCRIPTIONS_FILE = os.path.join(CACHE_DIR, "_descriptions.json")

def load_descriptions(path=DESCRIPTIONS_FILE):
    """Load archived LLM summaries keyed by object id (empty if none yet)."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def fetch_user_data(username):
    """Fetch the full collection and per-game data from BGG, returning {"collection": ..., "games": [...]}."""
    collection = bgg_api_to_dict('collection', {
        'username': username,
        'version': 1,
        'excludesubtype': 'boardgameexpansion',
        'stats': 1,
        'own': 1,
    })
    items = collection['items']['item']
    if not isinstance(items, list):
        items = [items]
    game_ids = [i['@objectid'] for i in items]

    games = []
    for i in tqdm(range(0, len(game_ids), BGG_BATCH_SIZE)):
        batch = game_ids[i:i + BGG_BATCH_SIZE]
        response = bgg_game_to_dict(batch, {'stats': '1'})
        batch_games = response['boardgames']['boardgame']
        if not isinstance(batch_games, list):
            batch_games = [batch_games]
        games.extend(batch_games)
        time.sleep(2)

    return {'collection': collection, 'games': games}

def load_data(username, refresh):
    """Return the full owned collection + games data, fetching from BGG when needed.

    Caches everything (for-trade filtering is a render-time concern), so it
    fetches (and rewrites the cache) when `refresh` is set or no cache exists;
    otherwise reads the cache. Fetching requires BGG_API_TOKEN.
    """
    path = cache_path(username)
    if refresh or not os.path.exists(path):
        data = fetch_user_data(username)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f)
        return data
    with open(path) as f:
        return json.load(f)

def as_list(field):
    """Wrap a BGG field that may be a single dict, a list, or missing into a list."""
    if field is None or isinstance(field, float):
        return []
    return field if isinstance(field, list) else [field]

def primary_name(field):
    """The game's primary (@primary='true') name, or the first name if none is flagged."""
    items = as_list(field)
    for i in items:
        if isinstance(i, dict) and i.get('@primary') == 'true':
            return i.get('#text', '')
    return items[0].get('#text', '') if items and isinstance(items[0], dict) else ''

def names(field, limit=None, sep=', ', more='+'):
    """Join the '#text' values of a possibly-nested BGG field (list/dict/None)."""
    texts = [i['#text'] for i in as_list(field) if isinstance(i, dict) and i.get('#text')]
    if not texts:
        return ''
    if limit and len(texts) > limit:
        return sep.join(texts[:limit]) + ' ' + more
    return sep.join(texts)

def clean_text(text):
    """Unescape HTML entities and collapse whitespace to a single line."""
    return re.sub(r'\s+', ' ', html.unescape(text or '').replace('\n', ' ')).strip()

OVERRIDES_FILE = os.environ.get("OVERRIDES_FILE", os.path.join(_ROOT, "overrides.toml"))

def load_overrides(path=OVERRIDES_FILE):
    """Load per-game overrides keyed by object id, e.g. {'42': {'name': ...}}."""
    try:
        with open(path, 'rb') as f:
            return tomllib.load(f).get('overrides', {})
    except FileNotFoundError:
        return {}

def display_name(game, item, overrides, short=False):
    """Resolve a game's display name.

    `name` overrides apply everywhere; a `short` override applies only where
    `short=True` (the reference card, which has one line). Otherwise use the
    owned edition's name (collection item), falling back to the canonical name.
    """
    ov = overrides.get(game.get('@objectid'), {})
    if short and ov.get('short'):
        return ov['short']
    if ov.get('name'):
        return ov['name']
    name_field = item.get('name')
    raw_name = name_field.get('#text') if isinstance(name_field, dict) else (name_field or '')
    raw_name = raw_name or primary_name(game.get('name'))
    m = re.match(r'^(.*?)\s*\(([^()]*)\)\s*$', raw_name)
    if m:
        head, paren = m.group(1).strip(), m.group(2).strip()
        raw_name = head if re.search(r'[A-Za-z]', head) else paren
    return raw_name

def parse_numplayers_poll(poll, threshold=0.60):
    """Return the player counts the BGG community rates Best/Recommended.

    `poll` is the raw `poll` element list from the BGG API (the first entry is
    the suggested_numplayers poll). A count qualifies when the share of
    Best+Recommended votes meets `threshold`.
    """
    try:
        np_poll = poll[0]
    except TypeError:
        return []

    if int(np_poll['@totalvotes']) < 1 or np_poll['@name'] != 'suggested_numplayers':
        return []

    recommended = []
    for np_dict in np_poll['results']:
        num_players = int(np_dict['@numplayers'].replace('+', ''))
        good_votes  = 0
        total_votes = 0
        for row in np_dict['result']:
            votes = int(row['@numvotes'])
            total_votes += votes
            if row['@value'] in ('Best', 'Recommended'):
                good_votes += votes
        if total_votes > 0 and good_votes / total_votes >= threshold:
            recommended.append(num_players)
    return recommended

IMAGE_MAX_DIM = 600

def resize_image(url, output_path):
    """Download an image, resize to IMAGE_MAX_DIM, and save as JPEG."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        if max(img.size) > IMAGE_MAX_DIM:
            ratio = IMAGE_MAX_DIM / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        if img.mode in ('RGBA', 'P', 'PA'):
            if img.mode == 'P':
                img = img.convert('RGBA')
            img = img.convert('RGB')
        img.save(output_path, 'JPEG', quality=85)
        return True
    except Exception:
        return False


def qrcode(game):
    return _qrcode_lib.make(
        data=f"https://boardgamegeek.com/boardgame/{game['@objectid']}",
        image_factory=_qrcode_lib.image.svg.SvgPathImage
    ).to_string().decode().replace('fill="#000000"', 'fill="currentColor"')

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

def _resolve_descriptions(game, overrides, descriptions):
    """Precedence: manual override -> archived LLM description -> cleaned BGG text."""
    manual = overrides.get(game['@objectid'], {}).get('description')
    if manual:
        return clean_text(manual)
    generated = descriptions.get(game['@objectid'], {}).get('description')
    if generated:
        return generated
    text = clean_text(game.get('description'))
    if len(text) > 900:
        text = text[:900].rsplit(' ', 1)[0].rstrip(',.;:') + '…'
    return text

def _players(game):
    """Format the player range as 'lo–hi', 'lo', or 'hi'."""
    lo, hi = game.get('minplayers'), game.get('maxplayers')
    if not lo or lo == '0':
        return hi or ''
    return lo if lo == hi else f'{lo}–{hi}'

def _round1(value):
    try:
        return f'{float(value):.1f}'
    except (TypeError, ValueError):
        return ''

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
    """Build the card dict for a single game from the collection item and BGG data."""
    # Identity fields (name, image, year, publisher) reflect the owned edition
    # via the collection item; the rest comes from the game's canonical data.
    ratings = game.get('statistics', {}).get('ratings', {})
    return {
        'id':          game['@objectid'],
        'name':        display_name(game, item, overrides, short=True),
        'url':         f"https://boardgamegeek.com/boardgame/{game['@objectid']}",
        'qrcode':      qrcode(game),
        'medal':       _medal(item),
        'image':       item.get('image') or game.get('image') or game.get('thumbnail') or '',
        'players':     _players(game),
        'rec_players': ', '.join(str(n) for n in parse_numplayers_poll(game.get('poll'))),
        'time':        game.get('playingtime') or '',
        'description': _resolve_descriptions(game, overrides, descriptions),
        'published':   _published(game, item),
        'designer':    names(game.get('boardgamedesigner'), limit=2),
        'theme':       names(game.get('boardgamecategory'), limit=3),
        'mechanics':   names(game.get('boardgamemechanic'), limit=3),
        'weight':      _round1(ratings.get('averageweight')),
    }

def prepare_local_images(games, items, username):
    """Download + resize each game's cover into output/<username>_images/ (skipping ones
    already on disk) and return {objectid: relative_path} for cards to use."""
    image_map = {}
    image_dir = os.path.join(_ROOT, 'output', f'{username}_images')
    os.makedirs(image_dir, exist_ok=True)
    for g in tqdm(games, desc='Images'):
        gid = g['@objectid']
        item = items.get(gid, {})
        image_url = item.get('image') or g.get('image') or g.get('thumbnail') or ''
        if image_url:
            local_path = os.path.join(image_dir, f'{gid}.jpg')
            if not os.path.exists(local_path):
                resize_image(image_url, local_path)
            if os.path.exists(local_path):
                image_map[gid] = f'{username}_images/{gid}.jpg'
    return image_map


