"""Shared BoardGameGeek layer: fetch + cache the data, and parse it.

Both build scripts call load_data(), so either can populate the shared per-user
cache under cache/. When the cache is present and REFRESH_DATA is off, rendering
runs entirely from it — no API token or network needed.

The cache holds the raw API responses:
    {"collection": <collection response>, "games": [<boardgame dicts>]}
"""
import os
import re
import html
import json
import time
import tomllib
import requests
import xmltodict
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
    for _ in range(retries):
        r = requests.get(
            "https://boardgamegeek.com/xmlapi2/{}".format(endpoint),
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
    if isinstance(game_ids, list):
        game_ids = ",".join(str(i) for i in game_ids)
    params = params or {}
    for _ in range(retries):
        r = requests.get(
            "https://boardgamegeek.com/xmlapi/boardgame/{}".format(game_ids),
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
    return os.path.join(CACHE_DIR, f"{username}.json")

DESCRIPTIONS_FILE = os.path.join(CACHE_DIR, "_descriptions.json")

def load_descriptions(path=DESCRIPTIONS_FILE):
    """Load archived LLM summaries keyed by object id (empty if none yet)."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def fetch_user_data(username):
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


