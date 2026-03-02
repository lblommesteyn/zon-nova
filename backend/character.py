"""
Character agents — each has a private world-view based only on what they've witnessed.
Information asymmetry between characters is the core mechanic.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class CharacterKnowledge:
    known_locations: List[str] = field(default_factory=list)
    known_characters: List[str] = field(default_factory=list)   # character ids met
    known_objects: List[str] = field(default_factory=list)       # object ids seen/carried
    witnessed_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CharacterState:
    id: str
    name: str
    personality_traits: List[str]
    goal: str
    fear: str
    current_location: str
    appearance: str = ""           # visual description for illustration prompts
    emotional_state: str = "curious"
    knowledge: CharacterKnowledge = field(default_factory=CharacterKnowledge)
    goal_achieved: bool = False

    def __post_init__(self):
        # Characters start knowing their initial location
        if self.current_location not in self.knowledge.known_locations:
            self.knowledge.known_locations.append(self.current_location)
        # They know themselves
        if self.id not in self.knowledge.known_characters:
            self.knowledge.known_characters.append(self.id)

    def witness_event(self, event_dict: Dict[str, Any]):
        """Add an event to this character's witnessed history."""
        self.knowledge.witnessed_events.append(event_dict)

    def learn_location(self, location_name: str):
        if location_name not in self.knowledge.known_locations:
            self.knowledge.known_locations.append(location_name)

    def meet_character(self, char_id: str):
        if char_id not in self.knowledge.known_characters:
            self.knowledge.known_characters.append(char_id)

    def learn_object(self, obj_id: str):
        if obj_id not in self.knowledge.known_objects:
            self.knowledge.known_objects.append(obj_id)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "personality_traits": self.personality_traits,
            "goal": self.goal,
            "fear": self.fear,
            "current_location": self.current_location,
            "emotional_state": self.emotional_state,
            "goal_achieved": self.goal_achieved,
        }


def make_character(char_config: dict) -> "CharacterState":
    """Build a CharacterState from user-provided config dict."""
    traits = char_config.get("personality_traits", [])
    if isinstance(traits, str):
        traits = [t.strip() for t in traits.split(",")]

    return CharacterState(
        id=char_config["name"].lower().replace(" ", "_"),
        name=char_config["name"],
        personality_traits=traits,
        goal=char_config.get("goal", "Find adventure"),
        fear=char_config.get("fear", "Being left behind"),
        current_location=char_config.get("starting_location", ""),
        appearance=char_config.get("appearance", ""),
    )
