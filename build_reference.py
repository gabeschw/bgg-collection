"""Render a magazine-style reference guide with one card per game, four per A4 page."""
import os
import click
from jinja2 import Environment, FileSystemLoader, select_autoescape

import common

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
        games_list = [g for g in games_list if (items.get(g['@objectid'], {}).get('status') or {}).get('@fortrade') != '1']

    data_date = common.cache_date(username)

    # Optionally download + resize images to keep PDF size reasonable
    image_map = {}
    if local_images:
        image_map = common.prepare_local_images(games_list, items, username)

    overrides = common.load_overrides()
    descriptions = common.load_descriptions()
    cards = [common.build_card(g, items.get(g['@objectid'], {}), overrides, descriptions) for g in games_list]
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
