import os
from jinja2 import Environment, FileSystemLoader
import pandas as pd

from common import load_data, parse_numplayers_poll, recommended_players_string

pd.set_option('future.no_silent_downcasting', True)

BGG_USERNAME = os.environ["BGG_USERNAME"]
REFRESH_DATA = os.environ.get("REFRESH_DATA", "true").lower() == "true"
INCLUDE_FOR_TRADE = os.environ.get("INCLUDE_FOR_TRADE", "false").lower() == "true"

if __name__ == "__main__":
    data = load_data(BGG_USERNAME, refresh=REFRESH_DATA)
    collection_dict = data['collection']
    games_list = data['games']

    last_update_date = collection_dict['items']['@pubdate'][5:16]
    collection = pd.json_normalize(collection_dict['items']['item'])
    if not INCLUDE_FOR_TRADE:
        collection = collection[collection['status.@fortrade'] != '1']

    # Convert games to DataFrames and merge with collection data
    games      = pd.json_normalize(games_list)
    collection = collection.merge(games, how='left', on='@objectid', suffixes=('', '_g'))

    # Parse recommended number of players from poll data
    recommended_players = collection.poll.apply(parse_numplayers_poll)
    collection['Players'] = recommended_players.apply(recommended_players_string)
    for np in range(1, 7):
        collection[f'np_{np}'] = recommended_players.apply(lambda nums, n=np: n in nums)
    collection['np_7+'] = recommended_players.apply(lambda nums: any(p >= 7 for p in nums))

    # Create columns for HTML export
    collection['Name']       = collection['name.#text']
    collection['Time']       = collection['playingtime'].astype(int)
    collection['# Plays']    = collection['numplays']
    collection['Rating']     = collection['stats.rating.@value'].replace('N/A', ' ')
    collection['BGG Avg']    = collection['statistics.ratings.average'].astype(float).round(2)
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
        bgg_username=BGG_USERNAME,
        last_update_date=last_update_date,
        sections=sections,
    )
    with open(f'output/collection_{BGG_USERNAME}.html', 'w') as f:
        f.write(rendered)

    collection.to_csv('output/collection_{}.csv'.format(BGG_USERNAME))
