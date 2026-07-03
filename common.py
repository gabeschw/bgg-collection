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
