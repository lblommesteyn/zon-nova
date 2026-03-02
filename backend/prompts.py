"""
All Nova prompt templates in one place.
Keep system prompts concise — they repeat every call.
"""

from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from world import WorldState, WorldObject, Event
    from character import CharacterState


# ── System prompts ────────────────────────────────────────────────────────────

CHARACTER_DECISION_SYSTEM = (
    "You are simulating a character in a children's story. "
    "Stay completely true to your personality, goal, and fear. "
    "Only act on information your character has personally witnessed — never use knowledge they couldn't have. "
    "Respond with valid JSON only. No explanation, no extra text."
)

WORLD_INIT_SYSTEM = (
    "You are a creative world-builder for warm children's bedtime stories. "
    "Create vivid, imaginative, age-appropriate settings. "
    "Respond with valid JSON only. No explanation, no extra text."
)

NARRATIVE_COMPILER_SYSTEM = (
    "You are a gifted children's author writing a bedtime story that a parent will read aloud to their child. "
    "Write in warm, simple prose for ages 4–8 that sounds beautiful spoken aloud — "
    "short sentences, gentle rhythm, vivid sensory images, and a cozy sleepy feeling by the end. "
    "Preserve causality — events happen because characters chose to act. "
    "Respond with valid JSON only. No explanation, no extra text."
)

ILLUSTRATION_SYSTEM = (
    "You generate detailed illustration prompts for children's picture book art. "
    "Output only a single descriptive paragraph — no JSON, no labels, no extra text."
)

GOAL_CHECK_SYSTEM = (
    "You evaluate whether a story character has achieved or made meaningful progress toward their goal. "
    "In a children's bedtime story, a clear positive step toward the goal counts as success — "
    "it does not need to be 100% complete. Be generous: if the character is clearly on the right path "
    "and something good has happened, return achieved. "
    "Respond with valid JSON only. No explanation, no extra text."
)


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_world_init_prompt(theme: str, char_configs: List[dict], preset_hint: str = "") -> str:
    char_lines = "\n".join(
        f"  - {c['name']} ({c.get('personality_traits', '')}): Goal — {c.get('goal', '')}."
        for c in char_configs
    )
    hint_line = f"\nSetting style hints: {preset_hint}" if preset_hint else ""
    return f"""Create a children's story world for this theme: "{theme}"{hint_line}

Characters:
{char_lines}

Design exactly 5 named locations that connect naturally (each location should connect to 2-3 others).
Include 6-8 interesting objects spread across locations.
IMPORTANT: At least one object must be directly relevant to each character's stated goal — place it somewhere they must travel to find it.
Characters may start in the same or different locations, but spread them out so they must move to meet.

Return ONLY this JSON:
{{
  "setting_name": "evocative world name",
  "setting_description": "2-3 sentence atmospheric description appropriate for children",
  "locations": [
    {{
      "name": "Location Name",
      "description": "1-2 vivid sentences",
      "connected_to": ["Other Location", "Another Location"]
    }}
  ],
  "objects": [
    {{
      "id": "unique_snake_case_id",
      "name": "Object Name",
      "location": "Location Name",
      "description": "brief child-friendly description",
      "properties": {{}}
    }}
  ],
  "character_starting_positions": {{
    "Character Name": "Location Name"
  }},
  "character_appearances": {{
    "Character Name": "FIRST say what kind of being this character is (e.g. 'a small brown rabbit', 'a young human girl', 'a wise old owl', 'a tiny pixie'). Then describe their defining visual features for an illustrator in 1 sentence. If their name or traits suggest an animal or magical creature, describe them as that creature — do NOT default to human."
  }}
}}"""


def build_character_decision_prompt(
    char: "CharacterState",
    visible_objects: List["WorldObject"],
    nearby_chars: List["CharacterState"],
    world: "WorldState",
) -> str:
    obj_lines = "\n".join(f"  - {o.name}: {o.description}" for o in visible_objects)
    char_lines = "\n".join(
        f"  - {c.name} ({', '.join(c.personality_traits)})" for c in nearby_chars
    )
    carrying = world.carrying_objects(char.id)
    carry_lines = "\n".join(f"  - {o.name}" for o in carrying)

    recent = char.knowledge.witnessed_events[-8:]
    event_lines = "\n".join(f"  - {e.get('description', '')}" for e in recent)

    # Build reachable locations
    current_loc = world.locations.get(char.current_location)
    reachable = current_loc.connected_to if current_loc else []

    # Build interaction nudge — the most important behavioral fix
    if nearby_chars:
        nearby_names = " and ".join(c.name for c in nearby_chars)
        interaction_block = (
            f"\nCRITICAL: {nearby_names} {'is' if len(nearby_chars) == 1 else 'are'} RIGHT HERE with you. "
            f"Moving away from them is almost always the wrong choice. "
            f"Could speaking to them, giving them something, or asking for help advance your goal? "
            f"Use this opportunity — characters who never interact never make progress."
        )
    else:
        interaction_block = (
            f"\nYou are alone. Search this location for anything useful, "
            f"or move toward a place where your goal is more likely to be achieved."
        )

    # Identify the last action to avoid repetition
    last_action = ""
    if recent:
        last = recent[-1]
        if last.get("actor") == char.id:
            last_action = f"\nAVOID: You just did '{last.get('action_type', '')}' last turn. Do something different."

    return f"""You are {char.name} — {', '.join(char.personality_traits)}.

YOUR GOAL (the only thing that matters to you): {char.goal}
YOUR FEAR: {char.fear}
YOUR MOOD: {char.emotional_state}
YOUR LOCATION: {char.current_location}

OBJECTS YOU CAN SEE HERE:
{obj_lines if obj_lines else '  (nothing)'}

WHAT YOU ARE CARRYING:
{carry_lines if carry_lines else '  (nothing)'}

WHO IS HERE WITH YOU:
{char_lines if char_lines else '  (no one — you are alone)'}

WHAT YOU HAVE WITNESSED:
{event_lines if event_lines else '  (nothing yet)'}

PLACES YOU COULD MOVE TO: {', '.join(reachable) if reachable else 'nowhere new'}
{interaction_block}{last_action}

DECISION: Choose the ONE action that moves you closest to your goal.
- speak → only if you have something meaningful to say that advances your goal
- give → if you're carrying something another character needs
- take → if an object here would help you
- search → if you haven't explored this location yet
- move → ONLY if there's a specific reason to go elsewhere
- hide → only if you genuinely fear what's about to happen

Do NOT act on information {char.name} hasn't personally witnessed.

Respond ONLY with this JSON:
{{
  "action_type": "move|take|speak|give|hide|search",
  "target": "exact location name, object name, or character name",
  "dialogue": "exact words spoken (only if action_type is speak — make it reveal your goal or fear)",
  "internal_motivation": "one honest sentence: what {char.name} hopes this action will achieve"
}}"""


def build_narrative_prompt(
    world: "WorldState",
    characters: List["CharacterState"],
    event_log: List["Event"],
) -> str:
    char_summaries = "\n".join(
        f"- {c.name} ({', '.join(c.personality_traits)}): Goal — {c.goal}. Fear — {c.fear}."
        for c in characters
    )
    events_text = "\n".join(
        f"Turn {e.turn} | {e.actor} [{e.action_type}]: {e.description}"
        for e in event_log
    )
    return f"""SETTING: {world.setting_name} — {world.setting_description}

CHARACTERS:
{char_summaries}

COMPLETE EVENT LOG (everything that happened, in order):
{events_text}

Compile this into a children's bedtime story for ages 4–8 that a parent reads aloud.
Rules:
- Write in warm, simple prose that sounds beautiful spoken aloud — short sentences, gentle rhythm
- Each page captures ONE story moment — do not combine multiple beats into one page
- Preserve the causal chain — events happen because characters chose to act
- Do NOT add events that didn't occur in the simulation
- You MUST return between 8 and 10 pages — never fewer than 8
- Each page text should be 3–4 sentences
- The final page must feel like a true ending: peaceful, resolved, with a sense of the characters settling down to rest

Return ONLY a JSON array with 8–10 objects. No explanation before or after the array:
[
  {{
    "page": 1,
    "text": "3–4 warm, vivid sentences of story prose",
    "scene_description": "What is visually happening — for an illustrator",
    "characters_present": ["Character Name"]
  }},
  {{
    "page": 2,
    "text": "...",
    "scene_description": "...",
    "characters_present": ["..."]
  }}
]"""


def build_goal_check_prompt(char: "CharacterState", recent_events: list) -> str:
    events_text = "\n".join(f"- {e.get('description', '')}" for e in recent_events)
    return f"""Character: {char.name}
Goal: {char.goal}

Events {char.name} personally witnessed (most recent):
{events_text or '(none)'}

Has {char.name} achieved their goal, or made a clear meaningful step toward it?
In a children's story, getting the key item, speaking to the right person, or having a clear breakthrough counts.
Be generous — if something good happened that moves them toward their goal, return true.

Return ONLY: {{"achieved": true}} or {{"achieved": false}}"""


def build_illustration_prompt(page: dict, appearance_map: dict | None = None) -> str:
    chars_present = page.get("characters_present", [])
    appearance_map = appearance_map or {}

    if chars_present:
        char_lines = "\n".join(
            f"  - {name}: {appearance_map.get(name, 'a child-like character')}"
            for name in chars_present
        )
        char_block = f"ALL of these characters must be clearly visible in the scene:\n{char_lines}"
    else:
        char_block = "No specific characters required — focus on the setting."

    return f"""Create an illustration prompt for this children's picture book page.

Scene: {page.get('scene_description', '')}
Story text: {page.get('text', '')}

{char_block}

Write a single detailed illustration prompt for a warm, whimsical watercolor children's book illustration.
Include: art style (soft watercolor, warm palette), color mood, character expressions and poses, background details.
Every named character above must appear. Keep it magical and child-appropriate.
Output ONLY the illustration prompt paragraph."""
