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
    "You are a gifted children's author who weaves simulation event logs into beautiful bedtime stories. "
    "Write in warm, simple prose for ages 4–8. "
    "Preserve causality — events happen because characters chose to act. "
    "Respond with valid JSON only. No explanation, no extra text."
)

ILLUSTRATION_SYSTEM = (
    "You generate detailed illustration prompts for children's picture book art. "
    "Output only a single descriptive paragraph — no JSON, no labels, no extra text."
)


# ── Prompt builders ───────────────────────────────────────────────────────────

def build_world_init_prompt(theme: str, character_names: List[str], preset_hint: str = "") -> str:
    names_str = ", ".join(character_names)
    hint_line = f"\nSetting style hints: {preset_hint}" if preset_hint else ""
    return f"""Create a children's story world for this theme: "{theme}"{hint_line}
Characters: {names_str}

Design exactly 5 named locations that connect naturally (each location should connect to 2-3 others).
Include 6-8 interesting objects spread across locations.
Characters may start in the same or different locations.

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

    return f"""You are {char.name}, a character with these traits: {', '.join(char.personality_traits)}.

YOUR SECRET GOAL: {char.goal}
YOUR DEEPEST FEAR: {char.fear}
HOW YOU FEEL RIGHT NOW: {char.emotional_state}
YOUR CURRENT LOCATION: {char.current_location}

WHAT YOU CAN REACH FROM HERE: {', '.join(reachable) if reachable else 'nowhere new'}

WHAT YOU CAN SEE NEARBY:
{obj_lines if obj_lines else '  (nothing of note)'}

WHAT YOU ARE CARRYING:
{carry_lines if carry_lines else '  (nothing)'}

WHO IS NEARBY:
{char_lines if char_lines else '  (you are alone)'}

WHAT YOU HAVE WITNESSED:
{event_lines if event_lines else '  (nothing has happened yet)'}

It is {char.name}'s turn to act. Choose ONE action driven by personality and what you know.
Do NOT act on information {char.name} hasn't personally witnessed.

Respond ONLY with this JSON:
{{
  "action_type": "move|take|speak|give|hide|search",
  "target": "exact location name, object name, or character name",
  "dialogue": "exact words spoken (only fill this if action_type is speak)",
  "internal_motivation": "why {char.name} is doing this — 1 honest sentence"
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

Compile this into a children's bedtime story for ages 4–8.
Rules:
- Write in warm, simple, beautiful prose
- Each page captures ONE story moment — do not combine multiple beats into one page
- Preserve the causal chain — events happen because characters chose to act
- Do NOT add events that didn't occur in the simulation
- You MUST return between 8 and 10 pages — never fewer than 8
- Each page text should be 3–4 sentences
- End at a natural resolution

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


def build_illustration_prompt(page: dict) -> str:
    chars = ", ".join(page.get("characters_present", []))
    return f"""Create an illustration prompt for this children's picture book page.

Scene: {page.get('scene_description', '')}
Story text: {page.get('text', '')}
Characters shown: {chars}

Write a single detailed illustration prompt for a warm, whimsical watercolor children's book illustration.
Include: art style (soft watercolor, warm palette), color mood, character expressions and poses, background details.
Keep it magical and child-appropriate. Output ONLY the illustration prompt paragraph."""
