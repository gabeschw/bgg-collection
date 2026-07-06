"""Generate consistent, length-capped game descriptions with an LLM and archive them.

Reads the cache written by build_collection.py, rewrites each game's description in a
consistent house voice grounded in structured facts, enforces a character ceiling, and
stores the results in cache/_descriptions.json (keyed by object id). build_reference.py reads
that file; this script is the only place that calls an LLM.

Only missing or stale entries are regenerated (see the source-hash / PROMPT_VERSION /
model check below); bump PROMPT_VERSION after editing INSTRUCTIONS to force a rebuild.
"""
import os
import json
import asyncio
import hashlib

import click
from pydantic_ai import Agent

import common

# LLM_MODEL may be a bare OpenRouter slug ("google/gemini-2.5-flash-lite") or a
# full pydantic-ai id ("openrouter:..."); normalize to the prefixed form.
_model = os.environ.get("LLM_MODEL") or os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")
MODEL = _model if _model.startswith("openrouter:") else f"openrouter:{_model}"
TEMPERATURE = 0.8
NUM_RETRIES = 5
CHAR_CEILING = 450         
PROMPT_VERSION = 3  # change when prompt or settings change, to trigger new summaries

INSTRUCTIONS = f"""
You write short, consistent descriptions for a board game collection reference guide.
Audience: someone who hasn't played the game and is deciding whether they'd enjoy it.

Given a game's original description and a set of facts, write a new description
according to the following:
- Convey the theme and how it plays, and give a sense of who it's for (e.g. light
  family game, gateway, thinky strategy game, party filler), but base this ONLY on
  the provided facts and text. Do not invent mechanics, opinions, or details.
- Use a consistent, plain, engaging voice across all games. Use present tense to describe the gameplay.
- Fit within {CHAR_CEILING} characters — a short paragraph. Use the space when the game warrants
  it, but don't pad a simple game just to fill it.
- Do NOT mention player count, playing time, publisher, designer since these will be shown 
  elsewhere in the reference guide.
- Do NOT use the name of the game in the description.
- Do NOT start sentences with words like "this is", "this game", "a", etc., even if 
  this means sentences are technially fragments, not grammatically correct.
- Do NOT use em-dashes, dashes, emojis, or other uncommon punctuation.
"""

async def summarize(game) -> str:
    """Rewrite within CHAR_CEILING, retrying with feedback.

    If the model never gets under the ceiling within NUM_RETRIES tries, keep the
    shortest attempt.
    """
    agent = Agent(
        MODEL,
        instructions=INSTRUCTIONS,
        model_settings={"temperature": TEMPERATURE},
    )
    categories = common.names(game.get('boardgamecategory'), limit=3)
    mechanics = common.names(game.get('boardgamemechanic'), limit=4)
    prompt = (
        (f"Categories: {categories}\n" if categories else '')
        + (f"Mechanics: {mechanics}\n" if mechanics else '')
        + f"Original Description:\n{common.clean_text(game.get('description'))}"
    )

    history = None
    attempts = []
    for _ in range(NUM_RETRIES + 1):
        result = await agent.run(prompt, message_history=history)
        text = result.output.strip()
        attempts.append(text)
        if len(text) <= CHAR_CEILING:
            return text
        history = result.all_messages()
        prompt = (f"That reply was {len(text)} characters. Rewrite it to at most "
                     f"{CHAR_CEILING} characters, keeping the meaning and voice.")
    return min(attempts, key=len)

async def _run(username):
    data = common.load_data(username, refresh=False)  # read cache; build_collection fetches
    store = common.load_descriptions()

    updated = 0
    skipped = 0
    empty = 0
    for game in data['games']:
        oid = game['@objectid']
        source_hash = hashlib.sha256(common.clean_text(game.get('description')).encode('utf-8')).hexdigest()[:16]
        if not common.clean_text(game.get('description')):
            empty += 1
        elif (store.get(oid, {}).get('source_hash') == source_hash
              and store.get(oid, {}).get('prompt_version') == PROMPT_VERSION
              and store.get(oid, {}).get('model') == MODEL):
            skipped += 1
        else:
            description = await summarize(game)
            store[oid] = {
                'description': description,
                'source_hash': source_hash,
                'prompt_version': PROMPT_VERSION,
                'model': MODEL,
            }
            updated += 1
            print(f"[{updated}] {common.primary_name(game.get('name'))[:42]:42} {len(description):>3} chars")

    with open(common.DESCRIPTIONS_FILE, 'w') as f:
        json.dump(store, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"\nupdated {updated}, skipped {skipped} (fresh), empty {empty}; total stored {len(store)}")


@click.command()
@click.argument('username')
def main(username):
    asyncio.run(_run(username))


if __name__ == "__main__":
    main()
