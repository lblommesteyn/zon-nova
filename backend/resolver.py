"""
Action resolution — converts character decisions into World Events.

Resolution is intentionally deterministic so the demo is reliable.
Phase ordering: moves happen first, then all other actions,
so characters who run away don't witness the scene they fled.
"""

from typing import List, Tuple, Dict, Set
from world import WorldState, Event
from character import CharacterState


class ActionResolver:

    def resolve_all(
        self,
        world: WorldState,
        characters: Dict[str, CharacterState],
        actions: List[Tuple[str, dict]],
    ) -> List[Event]:
        """
        Turn a list of (char_id, action_dict) tuples into a list of Events.
        Mutates world state and character states in place.
        """
        events: List[Event] = []
        taken_objects: Set[str] = set()   # prevent two chars grabbing the same thing

        # ── Phase 1: Moves ─────────────────────────────────────────────────
        for char_id, action in actions:
            if action.get("action_type") == "move":
                event = self._resolve_move(world, characters, char_id, action)
                if event:
                    events.append(event)

        # ── Phase 2: Everything else ───────────────────────────────────────
        for char_id, action in actions:
            atype = action.get("action_type", "")
            if atype == "move":
                continue

            event = None
            if atype == "speak":
                event = self._resolve_speak(world, characters, char_id, action)
            elif atype == "take":
                event = self._resolve_take(world, characters, char_id, action, taken_objects)
            elif atype == "give":
                event = self._resolve_give(world, characters, char_id, action)
            elif atype == "hide":
                event = self._resolve_hide(world, characters, char_id, action)
            elif atype == "search":
                event = self._resolve_search(world, characters, char_id, action)
            else:
                # Unknown / malformed action — log a neutral beat
                event = self._idle_event(world, characters, char_id, action)

            if event:
                events.append(event)

        # ── Phase 3: Set witnesses (based on final positions) ─────────────
        for event in events:
            actor_pos = world.characters.get(event.actor)
            if actor_pos:
                event.witnessed_by = world.characters_at(actor_pos.location)

        return events

    # ── Individual resolvers ───────────────────────────────────────────────

    def _resolve_move(self, world, chars, char_id, action) -> Event | None:
        pos = world.characters[char_id]
        target = action.get("target", "").strip()
        current_loc = world.locations.get(pos.location)
        char = chars[char_id]

        if current_loc and target in current_loc.connected_to and target in world.locations:
            old = pos.location
            pos.location = target
            char.current_location = target
            char.learn_location(target)
            motivation = action.get("internal_motivation", "")
            suffix = f" {motivation}" if motivation else ""
            return Event(
                turn=world.turn,
                actor=char_id,
                action_type="move",
                description=f"{char.name} left {old} and made their way to {target}.{suffix}",
            )
        else:
            # Invalid move — character stays but something happens
            return Event(
                turn=world.turn,
                actor=char_id,
                action_type="wait",
                description=f"{char.name} paused and looked around {pos.location} thoughtfully.",
            )

    def _resolve_speak(self, world, chars, char_id, action) -> Event | None:
        char = chars[char_id]
        dialogue = action.get("dialogue", "").strip()
        target = action.get("target", "").strip()
        motivation = action.get("internal_motivation", "")

        if not dialogue:
            dialogue = "Something important..."

        if target:
            description = f'{char.name} turned to {target} and said: "{dialogue}"'
        else:
            description = f'{char.name} said aloud: "{dialogue}"'

        return Event(
            turn=world.turn,
            actor=char_id,
            action_type="speak",
            description=description,
        )

    def _resolve_take(self, world, chars, char_id, action, taken: Set[str]) -> Event | None:
        pos = world.characters[char_id]
        char = chars[char_id]
        target = action.get("target", "").strip().lower()

        # Find the object at the character's location
        obj = None
        for o in world.objects.values():
            if (o.name.lower() == target or o.id == target or target in o.name.lower()):
                if o.location == pos.location and not o.hidden and o.id not in taken:
                    obj = o
                    break

        if obj:
            taken.add(obj.id)
            obj.location = f"carried_by_{char_id}"
            pos.carrying.append(obj.id)
            char.learn_object(obj.id)
            return Event(
                turn=world.turn,
                actor=char_id,
                action_type="take",
                description=f"{char.name} picked up the {obj.name}.",
            )
        else:
            return Event(
                turn=world.turn,
                actor=char_id,
                action_type="search",
                description=f"{char.name} looked for {target} but couldn't find it here.",
            )

    def _resolve_give(self, world, chars, char_id, action) -> Event | None:
        pos = world.characters[char_id]
        char = chars[char_id]
        target_name = action.get("target", "").strip()

        # Find target character in same location
        target_char = None
        for cid, cstate in chars.items():
            if cid != char_id and cstate.name.lower() == target_name.lower():
                if world.characters[cid].location == pos.location:
                    target_char = cstate
                    target_pos = world.characters[cid]
                    break

        if not target_char or not pos.carrying:
            return Event(
                turn=world.turn,
                actor=char_id,
                action_type="gesture",
                description=f"{char.name} reached out toward {target_name} with an empty hand.",
            )

        # Give the first carried item
        obj_id = pos.carrying[0]
        obj = world.objects.get(obj_id)
        pos.carrying.remove(obj_id)
        target_pos.carrying.append(obj_id)
        if obj:
            obj.location = f"carried_by_{target_char.id}"
            target_char.learn_object(obj_id)
        obj_name = obj.name if obj else "something"
        return Event(
            turn=world.turn,
            actor=char_id,
            action_type="give",
            description=f"{char.name} gave the {obj_name} to {target_char.name}.",
        )

    def _resolve_hide(self, world, chars, char_id, action) -> Event | None:
        char = chars[char_id]
        pos = world.characters[char_id]
        pos.hidden = True
        motivation = action.get("internal_motivation", "")
        reason = f" {motivation}" if motivation else ""
        return Event(
            turn=world.turn,
            actor=char_id,
            action_type="hide",
            description=f"{char.name} slipped into the shadows of {pos.location} and hid.{reason}",
        )

    def _resolve_search(self, world, chars, char_id, action) -> Event | None:
        char = chars[char_id]
        pos = world.characters[char_id]

        # Reveal one hidden object or character in the location
        revealed = None
        for obj in world.objects.values():
            if obj.location == pos.location and obj.hidden:
                obj.hidden = False
                char.learn_object(obj.id)
                revealed = f"the {obj.name}"
                break

        if not revealed:
            for cid, cpos in world.characters.items():
                if cid != char_id and cpos.location == pos.location and cpos.hidden:
                    cpos.hidden = False
                    revealed = chars[cid].name
                    break

        if revealed:
            return Event(
                turn=world.turn,
                actor=char_id,
                action_type="search",
                description=f"{char.name} searched carefully and discovered {revealed}!",
            )
        else:
            return Event(
                turn=world.turn,
                actor=char_id,
                action_type="search",
                description=f"{char.name} searched the {pos.location} but found nothing hidden.",
            )

    def _idle_event(self, world, chars, char_id, action) -> Event:
        char = chars[char_id]
        motivation = action.get("internal_motivation", "")
        return Event(
            turn=world.turn,
            actor=char_id,
            action_type="idle",
            description=f"{char.name} paused, lost in thought. {motivation}".strip(),
        )
