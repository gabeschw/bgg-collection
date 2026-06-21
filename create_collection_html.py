import os
import requests
import xmltodict
import time
import pickle
from tqdm import tqdm
from jinja2 import Environment, FileSystemLoader
import pandas as pd

pd.set_option('future.no_silent_downcasting', True)

BGG_USERNAME = os.environ["BGG_USERNAME"]
BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]
REFRESH_GAME_DATA = os.environ.get("REFRESH_GAME_DATA", "true").lower() == "true"
INCLUDE_FOR_TRADE = os.environ.get("INCLUDE_FOR_TRADE", "false").lower() == "true"
BGG_BATCH_SIZE = 20

def bgg_api_to_dict(endpoint, params, retries=5):
    for _ in range(retries):
        r = requests.get(
            "https://boardgamegeek.com/xmlapi2/{}".format(endpoint),
            params=params,
            headers={
                "Authorization": f"Bearer {BGG_API_TOKEN}"
            }
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
            headers={
                 "Authorization": f"Bearer {BGG_API_TOKEN}"
            }
        )
        r.raise_for_status()
        if r.status_code == 202:
            time.sleep(1)
            continue
        return xmltodict.parse(r.content)
    raise RuntimeError(f"BGG API returned 202 {retries} times for boardgame {game_ids}")

def parse_numplayers_poll(poll, threshold=0.60):
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

if __name__ == "__main__":
    # Download collection XML data
    collection_dict = bgg_api_to_dict('collection', {
        'username': BGG_USERNAME,
        'version': 1,
        'excludesubtype': 'boardgameexpansion',
        'stats': 1,
        'own': 1,
    })
    last_update_date = collection_dict['items']['@pubdate'][5:16]
    collection = pd.json_normalize(collection_dict['items']['item'])
    if INCLUDE_FOR_TRADE:
        collection = collection[collection['status.@fortrade'] == '1']

    # Download individual game XML data from collection
    if REFRESH_GAME_DATA:
        games_list = []
        game_ids = collection['@objectid'].to_list()
        for i in tqdm(range(0, len(game_ids), BGG_BATCH_SIZE)):
            batch = game_ids[i:i + BGG_BATCH_SIZE]
            response = bgg_game_to_dict(batch, {'stats': '1'})
            batch_games = response['boardgames']['boardgame']
            if not isinstance(batch_games, list):
                batch_games = [batch_games]
            games_list.extend(batch_games)
            time.sleep(2)
        with open('games_list.pickle', 'wb') as f:
            pickle.dump(games_list, f)
    else:
        with open('games_list.pickle', 'rb') as f:
            games_list = pickle.load(f)

    # Convert games to DataFrames and merge with collection data
    games      = pd.json_normalize(games_list)
    collection = collection.merge(games, how='left', on='@objectid', suffixes=('', '_g'))

    # Parse recommended number of players from poll data
    recommended_players = collection.poll.apply(parse_numplayers_poll)
    collection['Players'] = recommended_players.apply(
        lambda nums: "".join(str(n) if n in nums else "_" for n in range(1, 10))
    )
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
    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("collection_template.html")
    rendered = template.render(
        bgg_username=BGG_USERNAME,
        last_update_date=last_update_date,
        sections=sections,
    )
    with open(f'output/collection_{BGG_USERNAME}.html', 'w') as f:
        f.write(rendered)

    collection.to_csv('output/collection_{}.csv'.format(BGG_USERNAME))
