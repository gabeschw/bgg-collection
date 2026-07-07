"""Render a magazine-style reference guide with one card per game, four per A4 page."""
import os
from datetime import datetime
from io import BytesIO
import click
import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
import qrcode
import qrcode.image.svg
from tqdm import tqdm

import common

IMAGE_MAX_DIM = 600

def _resize_image(url, output_path):
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
    
def _qrcode(game):
    return qrcode.make(
        data=f"https://boardgamegeek.com/boardgame/{game['@objectid']}",
        image_factory=qrcode.image.svg.SvgPathImage
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
    edition_pubs = [link['@value'] for link in common.as_list(version.get('link'))
                    if isinstance(link, dict) and link.get('@type') == 'boardgamepublisher' and link.get('@value')]
    if edition_pubs:
        publisher = edition_pubs[0] + (' +' if len(edition_pubs) > 1 else '')
    else:
        publisher = common.names(game.get('boardgamepublisher'), limit=1)
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
        return common.clean_text(manual)
    generated = descriptions.get(game['@objectid'], {}).get('description')
    if generated:
        return generated
    text = common.clean_text(game.get('description'))
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
        'name':        common.display_name(game, item, overrides, short=True),
        'url':         f"https://boardgamegeek.com/boardgame/{game['@objectid']}",
        'qrcode':      _qrcode(game),
        'medal':       _medal(item),
        'image':       item.get('image') or game.get('image') or game.get('thumbnail') or '',
        'players':     _players(game),
        'rec_players': ', '.join(str(n) for n in common.parse_numplayers_poll(game.get('poll'))),
        'time':        game.get('playingtime') or '',
        'description': _resolve_descriptions(game, overrides, descriptions),
        'published':   _published(game, item),
        'designer':    common.names(game.get('boardgamedesigner'), limit=2),
        'theme':       common.names(game.get('boardgamecategory'), limit=3),
        'mechanics':   common.names(game.get('boardgamemechanic'), limit=3),
        'weight':      _round1(ratings.get('averageweight')),
    }

@click.command()
@click.argument('username')
@click.option('--refresh-data', is_flag=True, default=False,
              help='Fetch fresh data from BGG API')
@click.option('--include-for-trade', is_flag=True, default=False,
              help='Include games marked For Trade in BGG')
@click.option('--local-images', is_flag=True, default=False,
              help='Download and resize images locally to reduce PDF size')
def main(username, refresh_data, include_for_trade, local_images):
    """Download the collection from BGG and render the reference guide to output/."""
    data = common.load_data(username, refresh=refresh_data)
    games_list = data['games']
    items = {i['@objectid']: i for i in common.as_list(data['collection']['items']['item'])}
    if not include_for_trade:
        games_list = [g for g in games_list if not ((items.get(g['@objectid'], {}).get('status') or {}).get('@fortrade') == '1')]

    data_date = datetime.fromtimestamp(os.path.getmtime(common.cache_path(username))).strftime('%b %d %Y')

    # Optionally download + resize images to keep PDF size reasonable
    image_map = {}
    if local_images:
        image_dir = os.path.join('output', f'{username}_images')
        os.makedirs(image_dir, exist_ok=True)
        for g in tqdm(games_list, desc='Images'):
            gid = g['@objectid']
            item = items.get(gid, {})
            image_url = item.get('image') or g.get('image') or g.get('thumbnail') or ''
            if image_url:
                local_path = os.path.join(image_dir, f'{gid}.jpg')
                if not os.path.exists(local_path):
                    _resize_image(image_url, local_path)
                if os.path.exists(local_path):
                    image_map[gid] = f'{username}_images/{gid}.jpg'

    overrides = common.load_overrides()
    descriptions = common.load_descriptions()
    cards = [build_card(g, items.get(g['@objectid'], {}), overrides, descriptions) for g in games_list]
    for c in cards:
        if c['id'] in image_map:
            c['image'] = image_map[c['id']]
    cards.sort(key=lambda c: c['name'].lower())

    env = Environment(
        loader=FileSystemLoader('templates'),
        autoescape=select_autoescape(['html']),
    )
    template = env.get_template('reference.html')
    rendered = template.render(
        bgg_username=username,
        last_update_date=data_date,
        card_count=len(cards),
        cards=cards,
    )

    os.makedirs('output', exist_ok=True)
    with open(f'output/reference_{username}.html', 'w') as f:
        f.write(rendered)
    print(f'Wrote output/reference_{username}.html ({len(cards)} games)')


if __name__ == "__main__":
    main()
