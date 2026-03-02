"""
World state — the ground truth the simulation maintains.
Characters never see this directly; they only get filtered views.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Location:
    name: str
    description: str
    connected_to: List[str] = field(default_factory=list)


@dataclass
class WorldObject:
    id: str
    name: str
    location: str          # location name, or "carried_by_{char_id}"
    description: str
    properties: Dict[str, Any] = field(default_factory=dict)
    hidden: bool = False


@dataclass
class CharacterPosition:
    location: str
    alive: bool = True
    carrying: List[str] = field(default_factory=list)   # object ids
    hidden: bool = False


@dataclass
class Event:
    turn: int
    actor: str             # character id
    action_type: str
    description: str
    witnessed_by: List[str] = field(default_factory=list)  # character ids


@dataclass
class WorldState:
    setting_name: str
    setting_description: str
    locations: Dict[str, Location] = field(default_factory=dict)   # name → Location
    objects: Dict[str, WorldObject] = field(default_factory=dict)  # id → WorldObject
    characters: Dict[str, CharacterPosition] = field(default_factory=dict)  # id → position
    events: List[Event] = field(default_factory=list)
    turn: int = 0

    # ── Helpers ──────────────────────────────────────────────────────────────

    def objects_at(self, location: str) -> List[WorldObject]:
        return [
            obj for obj in self.objects.values()
            if obj.location == location and not obj.hidden
        ]

    def characters_at(self, location: str) -> List[str]:
        return [
            char_id for char_id, pos in self.characters.items()
            if pos.location == location and pos.alive and not pos.hidden
        ]

    def events_witnessed_by(self, character_id: str) -> List[Event]:
        return [e for e in self.events if character_id in e.witnessed_by]

    def carrying_objects(self, char_id: str) -> List[WorldObject]:
        pos = self.characters.get(char_id)
        if not pos:
            return []
        return [self.objects[oid] for oid in pos.carrying if oid in self.objects]

    def to_dict(self) -> dict:
        return {
            "setting_name": self.setting_name,
            "setting_description": self.setting_description,
            "locations": {
                name: {"name": loc.name, "description": loc.description, "connected_to": loc.connected_to}
                for name, loc in self.locations.items()
            },
            "objects": {
                oid: {"id": obj.id, "name": obj.name, "location": obj.location,
                      "description": obj.description, "hidden": obj.hidden}
                for oid, obj in self.objects.items()
            },
            "characters": {
                cid: {"location": pos.location, "alive": pos.alive,
                      "carrying": pos.carrying, "hidden": pos.hidden}
                for cid, pos in self.characters.items()
            },
        }


def build_world_from_nova(nova_data: dict, character_names: List[str]) -> "WorldState":
    """
    Construct a WorldState from the JSON Nova returns for world initialization.
    """
    world = WorldState(
        setting_name=nova_data.get("setting_name", "A Magical World"),
        setting_description=nova_data.get("setting_description", ""),
    )

    for loc_data in nova_data.get("locations", []):
        loc = Location(
            name=loc_data["name"],
            description=loc_data["description"],
            connected_to=loc_data.get("connected_to", []),
        )
        world.locations[loc.name] = loc

    for obj_data in nova_data.get("objects", []):
        obj = WorldObject(
            id=obj_data["id"],
            name=obj_data["name"],
            location=obj_data.get("location", list(world.locations.keys())[0] if world.locations else ""),
            description=obj_data.get("description", ""),
            properties=obj_data.get("properties", {}),
        )
        world.objects[obj.id] = obj

    # Character starting positions are set after CharacterState objects exist
    return world
