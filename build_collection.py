import click
from jinja2 import Environment, FileSystemLoader
import pandas as pd

from common import (
    load_data, collection_df, parse_numplayers_poll,
    recommended_players_string, display_name, load_overrides, as_list,
)

pd.set_option('future.no_silent_downcasting', True)


@click.command()
@click.argument('username')
@click.option('--refresh-data', is_flag=True, default=False,
              help='Fetch fresh data from BGG API')
@click.option('--include-for-trade', is_flag=True, default=False,
              help='Include games marked For Trade in BGG')
def main(username, refresh_data, include_for_trade):
    data = load_data(username, refresh=refresh_data)
    collection_dict = data['collection']
    games_list = data['games']

    overrides = load_overrides()
    items_by_id = {i['@objectid']: i for i in as_list(collection_dict['items']['item'])}
    games_by_id = {g['@objectid']: g for g in games_list}

    last_update_date = collection_dict['items']['@pubdate'][5:16]
    collection = collection_df(data=data)
    if not include_for_trade:
        collection = collection[collection['status.@fortrade'] != '1']

    # Parse recommended number of players from poll data
    recommended_players = collection.poll.apply(parse_numplayers_poll)
    collection['Players'] = recommended_players.apply(recommended_players_string)
    for np in range(1, 7):
        collection[f'np_{np}'] = recommended_players.apply(lambda nums, n=np: n in nums)
    collection['np_7+'] = recommended_players.apply(lambda nums: any(p >= 7 for p in nums))

    # Create columns for HTML export
    collection['Name']       = collection['@objectid'].map(
        lambda oid: display_name(games_by_id.get(oid, {}), items_by_id.get(oid, {}), overrides))
    collection['Time']       = collection['playingtime'].astype(int)
    collection['# Plays']    = collection['numplays']
    # Fixed decimals so the right-aligned columns line up on the decimal point.
    collection['Rating']     = collection['stats.rating.@value'].apply(
        lambda v: f'{float(v):.1f}' if str(v).replace('.', '', 1).isdigit() else ' ')
    collection['BGG Avg']    = collection['statistics.ratings.average'].astype(float).map('{:.2f}'.format)
    collection['BGG Rank']   = collection['statistics.ratings.ranks.rank.@value'].fillna(
        collection['statistics.ratings.ranks.rank'][collection['statistics.ratings.ranks.rank'].notnull()].apply(lambda x: x[0]['@value'])
    ).replace('Not Ranked', ' ')
    collection['Weight']     = collection['statistics.ratings.averageweight'].astype(float).round(1)
    collection['Year']       = collection['yearpublished']
    collection['Designer']   = collection['boardgamedesigner.#text'].fillna(
        collection.boardgamedesigner[collection['boardgamedesigner'].notnull()].apply(lambda d: d[0]['#text'] + ' +')).fillna(' ')
    collection[' ']          = collection['status.@fortrade'].apply(lambda x: '*' if x=='1' else ' ')

    # Create main body for HTML export
    cols = [
            'Name',
            'Time',
            'Players',
            'Weight',
            'Year',
            'Designer',
            'BGG Rank',
            'BGG Avg',
            'Rating',
            '# Plays',
            ' ',
    ]

    # Build sections for HTML export
    sections = []
    for np in ['1', '2', '3', '4', '5', '6', '7+']:
        df = collection[collection[f'np_{np}']][cols].fillna(0).sort_values(
            by=['Time', 'BGG Avg'], ascending=[True, False]
        )
        sections.append({
            'title': f'{np} Player{"s" if np != "1" else ""}',
            'table': df.to_html(index=False),
        })

    sections.append({
        'title': 'Alphabetic List',
        'page_break': True,
        'table': collection[cols].fillna(0).sort_values('Name').to_html(index=False),
    })

    sections.append({
        'title': 'By Designer',
        'page_break': True,
        'table': collection[cols].fillna(0).sort_values(['Designer', 'Year', 'Name']).to_html(index=False),
    })

    # Render and export HTML
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("collection.html")
    rendered = template.render(
        bgg_username=username,
        last_update_date=last_update_date,
        game_count=len(collection),
        sections=sections,
    )
    with open(f'output/collection_{username}.html', 'w') as f:
        f.write(rendered)

    collection.to_csv('output/collection_{}.csv'.format(username))


if __name__ == "__main__":
    main()
