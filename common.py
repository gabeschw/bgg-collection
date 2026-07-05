"""Shared BoardGameGeek layer: fetch + cache the data, and parse it.

Both build scripts call load_data(), so either can populate the shared per-user
cache under cache/. When the cache is present and REFRESH_DATA is off, rendering
runs entirely from it — no API token or network needed.

The cache holds the raw API responses:
    {"collection": <collection response>, "games": [<boardgame dicts>]}
"""
import os
import re
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

def _fetch(username):
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
        data = _fetch(username)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f)
        return data
    with open(path) as f:
        return json.load(f)

def collection_df(username=None, refresh=False, data=None):
    """Owned collection merged with per-game data, as a DataFrame for analysis.

    Pass `data` from load_data() to reuse it, otherwise give a `username` to load
    from the cache. Nested fields (publisher/mechanic/version lists) are kept as
    objects rather than the stringified form the exported CSV has.
    """
    import pandas as pd
    if data is None:
        data = load_data(username, refresh)
    collection = pd.json_normalize(data['collection']['items']['item'])
    games = pd.json_normalize(data['games'])
    return collection.merge(games, how='left', on='@objectid', suffixes=('', '_g'))

def is_for_trade(item):
    """True if the collection item is flagged for trade."""
    return (item.get('status') or {}).get('@fortrade') == '1'

def _as_list(field):
    if field is None or isinstance(field, float):
        return []
    return field if isinstance(field, list) else [field]

def _primary_name(field):
    items = _as_list(field)
    for i in items:
        if isinstance(i, dict) and i.get('@primary') == 'true':
            return i.get('#text', '')
    return items[0].get('#text', '') if items and isinstance(items[0], dict) else ''

def _collection_name(item):
    name = item.get('name')
    return name.get('#text') if isinstance(name, dict) else (name or '')

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
    return _clean_name(_collection_name(item) or _primary_name(game.get('name')))

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

def recommended_players_string(nums):
    """Render recommended counts as a fixed 9-slot reference string.

    Each slot 1-9 shows its digit when recommended, otherwise an underscore,
    e.g. [2, 3, 6] -> "_23__6___".
    """
    return "".join(str(n) if n in nums else "_" for n in range(1, 10))
