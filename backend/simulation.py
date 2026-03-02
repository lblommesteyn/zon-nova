"""
Simulation loop — the heart of the Emergent Story Engine.

Each turn:
  1. Perception  — filter world to each character's knowledge view
  2. Decision    — all characters act in parallel (asyncio.gather)
  3. Resolution  — world state updates
  4. Propagation — witnesses learn what happened
  5. Check       — did the story reach a natural end?
"""

import asyncio
from typing import List, Dict, Callable, Awaitable, Optional, Any

from nova_client import NovaClient
from world import WorldState, Event, CharacterPosition, build_world_from_nova
from character import CharacterState, make_character
from resolver import ActionResolver
from prompts import (
    CHARACTER_DECISION_SYSTEM,
    GOAL_CHECK_SYSTEM,
    WORLD_INIT_SYSTEM,
    build_character_decision_prompt,
    build_goal_check_prompt,
    build_world_init_prompt,
)


# Preset theme hints sent to Nova to guide world generation
PRESET_HINTS: Dict[str, str] = {
    "enchanted_forest": (
        "Ancient magical forest with talking animals, glowing mushrooms, a wise old tree, "
        "hidden fairy circles, and a crystal-clear stream. Warm, mysterious, and full of wonder."
    ),
    "pirate_ship": (
        "Wooden sailing ship on sparkling seas, with a crow's nest, creaky hold, captain's cabin, "
        "a mysterious treasure map, and a nearby island just visible on the horizon."
    ),
    "space_station": (
        "Gleaming space station orbiting a colorful planet, with a command bridge, zero-gravity lab, "
        "docking bay, engine room humming with power, and a viewport showing the stars."
    ),
    "underwater_kingdom": (
        "Magical underwater realm with coral palaces, pearl gardens, a sunken treasure ship, "
        "bioluminescent creatures, and a deep trench hiding ancient secrets."
    ),
}


class Simulation:
    def __init__(
        self,
        nova: NovaClient,
        world: WorldState,
        characters: Dict[str, CharacterState],
    ):
        self.nova = nova
        self.world = world
        self.characters = characters   # char_id → CharacterState
        self.resolver = ActionResolver()
        self.event_log: List[Event] = []
        self._goals_announced: set = set()   # char_ids whose achievement was already emitted

    async def run(
        self,
        max_turns: int = 8,
        progress_callback: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> List[Event]:
        """Run the simulation for up to max_turns turns."""

        for turn in range(1, max_turns + 1):
            self.world.turn = turn

            # ── 1 + 2: Perception + Decision (parallel) ─────────────────
            active = [c for c in self.characters.values()
                      if self.world.characters[c.id].alive]

            decision_tasks = [self._get_action(char) for char in active]
            results = await asyncio.gather(*decision_tasks, return_exceptions=True)

            actions = []
            for char, result in zip(active, results):
                if isinstance(result, Exception):
                    # Fallback: character idles this turn
                    action = {"action_type": "idle", "target": "", "internal_motivation":
                              f"{char.name} hesitated, unsure what to do."}
                else:
                    action = result

                actions.append((char.id, action))

                if progress_callback:
                    await progress_callback("character_action", {
                        "turn": turn,
                        "character_id": char.id,
                        "character_name": char.name,
                        "action": action,
                    })

            # ── 3: Resolution ────────────────────────────────────────────
            new_events = self.resolver.resolve_all(self.world, self.characters, actions)

            # ── 4: Propagation — update character knowledge ───────────────
            for event in new_events:
                self.world.events.append(event)
                self.event_log.append(event)
                self._propagate(event)

            if progress_callback:
                await progress_callback("turn_complete", {
                    "turn": turn,
                    "events": [_event_to_dict(e) for e in new_events],
                })

            # ── 4.5: Goal achievement check (Nova Micro, after turn 2) ────
            if turn >= 3:
                goal_checks = [
                    self._check_goal_achieved(char)
                    for char in active
                    if not char.goal_achieved
                ]
                await asyncio.gather(*goal_checks, return_exceptions=True)

                # Emit one event per newly-achieved goal
                for char in active:
                    if char.goal_achieved and char.id not in self._goals_announced:
                        self._goals_announced.add(char.id)
                        goal_event = Event(
                            turn=turn,
                            actor=char.id,
                            action_type="goal_achieved",
                            description=f"{char.name} achieved their goal: {char.goal}",
                        )
                        goal_event.witnessed_by = list(self.characters.keys())
                        self.world.events.append(goal_event)
                        self.event_log.append(goal_event)
                        self._propagate(goal_event)

                        if progress_callback:
                            await progress_callback("goal_achieved_event", {
                                "turn": turn,
                                "character_name": char.name,
                                "goal": char.goal,
                            })

            # ── 5: Check ending conditions ────────────────────────────────
            if self._story_concluded(turn, max_turns):
                break

        return self.event_log

    async def _get_action(self, char: CharacterState) -> dict:
        """Ask Nova what this character does next."""
        pos = self.world.characters[char.id]
        visible_objects = self.world.objects_at(pos.location)
        nearby_char_ids = self.world.characters_at(pos.location)
        nearby_chars = [
            self.characters[cid] for cid in nearby_char_ids if cid != char.id
        ]

        prompt = build_character_decision_prompt(char, visible_objects, nearby_chars, self.world)

        action = await self.nova.invoke_json(
            self.nova.micro(),
            CHARACTER_DECISION_SYSTEM,
            prompt,
            max_tokens=300,
            temperature=0.85,
        )
        # Validate minimal structure
        if not isinstance(action, dict) or "action_type" not in action:
            action = {"action_type": "idle", "target": "", "internal_motivation":
                      f"{char.name} paused and looked around."}
        return action

    def _propagate(self, event: Event):
        """
        Characters in the same location as the event actor witness it.
        Also update emotional states and inter-character awareness.
        """
        actor_pos = self.world.characters.get(event.actor)
        if not actor_pos:
            return

        event_dict = _event_to_dict(event)

        for char_id in event.witnessed_by:
            char = self.characters.get(char_id)
            if not char:
                continue
            char.witness_event(event_dict)

            # Characters in the same location learn each other exists
            for other_id in event.witnessed_by:
                if other_id != char_id:
                    char.meet_character(other_id)

            # Adjust emotional state based on action type
            if event.action_type == "speak" and char_id != event.actor:
                char.emotional_state = "attentive"
            elif event.action_type == "take":
                char.emotional_state = "watchful"
            elif event.action_type == "hide":
                if char_id == event.actor:
                    char.emotional_state = "nervous"
            elif event.action_type == "search" and "discovered" in event.description:
                char.emotional_state = "surprised"

    async def _check_goal_achieved(self, char: CharacterState) -> None:
        """Ask Nova Micro if this character has achieved their goal."""
        if char.goal_achieved:
            return
        recent = char.knowledge.witnessed_events[-6:]
        if len(recent) < 2:
            return  # not enough context to evaluate

        prompt = build_goal_check_prompt(char, recent)
        try:
            result = await self.nova.invoke_json(
                self.nova.micro(),
                GOAL_CHECK_SYSTEM,
                prompt,
                max_tokens=60,
                temperature=0.2,
            )
            if isinstance(result, dict) and result.get("achieved") is True:
                char.goal_achieved = True
        except Exception as exc:
            print(f"[Goal check] {char.name}: {exc}")

    def _story_concluded(self, turn: int, max_turns: int) -> bool:
        """Return True when the story has reached a natural ending point."""
        if turn >= max_turns:
            return True
        # End early once any character achieves their goal (after a minimum arc)
        if turn >= 3 and any(c.goal_achieved for c in self.characters.values()):
            return True
        return False


def _event_to_dict(event: Event) -> dict:
    return {
        "turn": event.turn,
        "actor": event.actor,
        "action_type": event.action_type,
        "description": event.description,
        "witnessed_by": event.witnessed_by,
    }


# ── World initialization ──────────────────────────────────────────────────────

async def initialize_world(
    nova: NovaClient,
    config: dict,
) -> tuple[WorldState, Dict[str, CharacterState]]:
    """
    Use Nova to generate the initial world from user config.
    Falls back to a minimal world if Nova fails.
    """
    char_configs = config["characters"]
    char_names = [c["name"] for c in char_configs]
    theme = config.get("theme", "magical adventure")
    preset_key = config.get("preset", "")
    preset_hint = PRESET_HINTS.get(preset_key, "")

    # Pass full char_configs so Nova can generate goal-relevant objects and correct appearances
    prompt = build_world_init_prompt(theme, char_configs, preset_hint)

    try:
        nova_data = await nova.invoke_json(
            nova.lite(),
            WORLD_INIT_SYSTEM,
            prompt,
            max_tokens=2000,
            temperature=0.7,
        )
    except Exception as exc:
        print(f"[World init] Nova call failed: {exc}. Using fallback world.")
        nova_data = _fallback_world(theme, char_names)

    world = build_world_from_nova(nova_data, char_names)

    # Assign starting positions and appearances from Nova's suggestion
    starting_positions: Dict[str, str] = nova_data.get("character_starting_positions", {})
    appearance_map: Dict[str, str] = nova_data.get("character_appearances", {})
    location_names = list(world.locations.keys())

    characters: Dict[str, CharacterState] = {}
    for i, char_cfg in enumerate(char_configs):
        # Find starting location: Nova suggestion → fallback to cycling through locations
        start_loc = starting_positions.get(char_cfg["name"], "")
        if start_loc not in world.locations:
            start_loc = location_names[i % len(location_names)] if location_names else "Unknown"

        char_cfg["starting_location"] = start_loc
        char_cfg["appearance"] = appearance_map.get(char_cfg["name"], "")
        char = make_character(char_cfg)
        characters[char.id] = char
        world.characters[char.id] = CharacterPosition(location=start_loc)

    return world, characters


def _fallback_world(theme: str, char_names: list) -> dict:
    """Minimal world used if Nova fails during initialization."""
    return {
        "setting_name": f"The World of {theme.title()}",
        "setting_description": f"A magical place where {theme} adventures unfold.",
        "locations": [
            {"name": "The Meadow", "description": "A sunny meadow with tall grass.", "connected_to": ["The Forest", "The Cave"]},
            {"name": "The Forest", "description": "A quiet forest of whispering trees.", "connected_to": ["The Meadow", "The Stream"]},
            {"name": "The Cave", "description": "A cozy cave with glittering walls.", "connected_to": ["The Meadow", "The Stream"]},
            {"name": "The Stream", "description": "A babbling brook with smooth pebbles.", "connected_to": ["The Forest", "The Cave", "The Hill"]},
            {"name": "The Hill", "description": "A gentle hill with a view of everything.", "connected_to": ["The Stream"]},
        ],
        "objects": [
            {"id": "golden_key", "name": "Golden Key", "location": "The Cave", "description": "A shiny key that might open something important."},
            {"id": "magic_map", "name": "Magic Map", "location": "The Meadow", "description": "A map that seems to redraw itself."},
            {"id": "crystal_gem", "name": "Crystal Gem", "location": "The Stream", "description": "A glowing gem with mysterious power."},
            {"id": "old_lantern", "name": "Old Lantern", "location": "The Forest", "description": "A lantern that never runs out of light."},
        ],
        "character_starting_positions": {name: ["The Meadow", "The Forest", "The Cave"][i % 3] for i, name in enumerate(char_names)},
    }
