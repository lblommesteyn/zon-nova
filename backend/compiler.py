"""
Narrative Compiler — takes the raw simulation event log and asks Nova Pro
to weave it into a children's bedtime story.

This is the only step where Nova "writes". Everything before is simulation.
"""

import asyncio
from typing import List, Dict

from nova_client import NovaClient
from world import WorldState, Event
from character import CharacterState
from prompts import (
    NARRATIVE_COMPILER_SYSTEM,
    ILLUSTRATION_SYSTEM,
    build_narrative_prompt,
    build_illustration_prompt,
)


class NarrativeCompiler:
    def __init__(self, nova: NovaClient):
        self.nova = nova

    async def compile(
        self,
        world: WorldState,
        characters: List[CharacterState],
        event_log: List[Event],
    ) -> List[Dict]:
        """
        Ask Nova Pro to compile the event log into story pages.
        Returns a list of page dicts: {page, text, scene_description, characters_present}
        """
        prompt = build_narrative_prompt(world, characters, event_log)

        try:
            pages = await self.nova.invoke_json(
                self.nova.pro(),
                NARRATIVE_COMPILER_SYSTEM,
                prompt,
                max_tokens=6000,
                temperature=0.75,
            )
            # Ensure it's a list
            if isinstance(pages, dict) and "pages" in pages:
                pages = pages["pages"]
            if not isinstance(pages, list):
                raise ValueError("Nova did not return a JSON array")
        except Exception as exc:
            print(f"[Compiler] Nova compilation failed: {exc}. Building fallback story.")
            pages = self._fallback_story(event_log, characters)

        # Normalize page structure
        normalized = []
        for i, page in enumerate(pages, 1):
            normalized.append({
                "page": page.get("page", i),
                "text": page.get("text", ""),
                "scene_description": page.get("scene_description", ""),
                "characters_present": page.get("characters_present", []),
            })

        return normalized

    async def generate_page_images(
        self,
        pages: List[Dict],
        illus_prompts: List[str],
    ) -> List[str]:
        """
        Generate one Nova Canvas image per page in parallel.
        Returns a list of base64 PNG strings (empty string if a page failed).
        """
        tasks = [
            self._gen_canvas_image(prompt, seed=i)
            for i, prompt in enumerate(illus_prompts)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        images = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"[Canvas] Page {i+1} failed: {result}")
                images.append("")
            else:
                images.append(result)
        return images

    async def _gen_canvas_image(self, illus_prompt: str, seed: int) -> str:
        style = (
            "Watercolor children's book illustration, warm soft colors, "
            "whimsical, magical, storybook art style, detailed background, "
            "cozy and dreamlike atmosphere. "
        )
        negative = (
            "text, letters, words, watermark, signature, logo, "
            "ugly, blurry, low quality, realistic photograph, dark, scary, violent"
        )
        return await self.nova.generate_image(
            prompt=style + illus_prompt,
            negative_prompt=negative,
            width=512,
            height=512,
            seed=seed * 37,
        )

    async def generate_illustration_prompts(self, pages: List[Dict]) -> List[str]:
        """
        Generate one illustration prompt per page, in parallel.
        """
        tasks = [self._gen_illus_prompt(page) for page in pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        prompts = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                prompts.append(
                    f"A warm watercolor illustration of a magical children's story scene. "
                    f"Soft colors, whimsical details, child-friendly art style."
                )
            else:
                prompts.append(result)
        return prompts

    async def _gen_illus_prompt(self, page: Dict) -> str:
        prompt = build_illustration_prompt(page)
        return await self.nova.invoke(
            self.nova.lite(),
            ILLUSTRATION_SYSTEM,
            prompt,
            max_tokens=250,
            temperature=0.7,
        )

    def _fallback_story(
        self,
        event_log: List[Event],
        characters: List[CharacterState],
    ) -> List[Dict]:
        """Minimal story built directly from events if Nova Pro fails."""
        pages = []
        char_names = [c.name for c in characters]

        pages.append({
            "page": 1,
            "text": (
                f"Once upon a time, {', '.join(char_names[:-1])} and {char_names[-1]} "
                f"found themselves in a magical world full of mystery and wonder."
            ),
            "scene_description": "Characters gathered at the start of their adventure",
            "characters_present": char_names,
        })

        # Group events into beats of ~3 events per page
        chunk_size = max(1, len(event_log) // 8)
        for i in range(0, len(event_log), chunk_size):
            chunk = event_log[i:i + chunk_size]
            text = " ".join(e.description for e in chunk)
            present = list({e.actor for e in chunk})
            present_names = [
                c.name for c in characters if c.id in present
            ]
            pages.append({
                "page": len(pages) + 1,
                "text": text,
                "scene_description": text[:120],
                "characters_present": present_names,
            })

        pages.append({
            "page": len(pages) + 1,
            "text": (
                f"And so {', '.join(char_names)} learned that the greatest adventures "
                f"happen when you follow your heart. They fell asleep under the stars, "
                f"dreaming of tomorrow."
            ),
            "scene_description": "Characters resting peacefully as the stars appear",
            "characters_present": char_names,
        })

        return pages
