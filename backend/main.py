"""
FastAPI application — WebSocket endpoint drives the real-time demo experience.

Flow:
  1. Client connects to ws://localhost:8000/ws/generate
  2. Client sends JSON config (theme, characters, max_turns)
  3. Server streams simulation events + story back through the WebSocket
  4. Client renders the simulation log and then the storybook
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from nova_client import NovaClient
from simulation import Simulation, initialize_world, _event_to_dict
from compiler import NarrativeCompiler

load_dotenv()

app = FastAPI(title="Emergent Story Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared Nova client (boto3 client is thread-safe)
nova = NovaClient(region=os.getenv("AWS_REGION", "us-east-1"))
compiler = NarrativeCompiler(nova)


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@app.websocket("/ws/generate")
async def generate_story(websocket: WebSocket):
    await websocket.accept()

    async def send(msg: dict):
        await websocket.send_text(json.dumps(msg))

    try:
        raw = await websocket.receive_text()
        config = json.loads(raw)
        _validate_config(config)

        # ── World initialization ───────────────────────────────────────────
        await send({"type": "status", "message": "Building your story world..."})

        world, characters = await initialize_world(nova, config)

        await send({
            "type": "world_ready",
            "world": world.to_dict(),
            "characters": [c.to_dict() for c in characters.values()],
        })

        # ── Simulation ─────────────────────────────────────────────────────
        await send({"type": "status", "message": "Characters are making decisions..."})

        async def on_progress(event_type: str, data: dict):
            await send({"type": event_type, **data})

        sim = Simulation(nova, world, characters)
        event_log = await sim.run(
            max_turns=config.get("max_turns", 8),
            progress_callback=on_progress,
        )

        # ── Narrative compilation ──────────────────────────────────────────
        await send({"type": "status", "message": "Weaving the story together..."})

        pages = await compiler.compile(world, list(characters.values()), event_log)

        await send({"type": "status", "message": "Writing illustration notes..."})

        illustration_prompts = await compiler.generate_illustration_prompts(pages)

        # ── Send story text now so the UI can start showing pages ──────────
        await send({
            "type": "story_text_ready",
            "pages": pages,
            "illustration_prompts": illustration_prompts,
            "event_log": [_event_to_dict(e) for e in event_log],
            "world_summary": {
                "setting_name": world.setting_name,
                "setting_description": world.setting_description,
                "total_turns": world.turn,
                "total_events": len(event_log),
            },
        })

        # ── Generate images, streaming each one as it finishes ────────────
        await send({"type": "status", "message": f"Painting {len(pages)} illustrations with Nova Canvas…"})

        async def gen_and_stream(idx: int, prompt: str):
            try:
                img64 = await compiler._gen_canvas_image(prompt, seed=idx)
                await send({"type": "page_image", "index": idx, "image": img64})
            except Exception as exc:
                print(f"[Canvas] Page {idx+1} failed: {exc}")
                await send({"type": "page_image", "index": idx, "image": ""})

        await asyncio.gather(*[
            gen_and_stream(i, p)
            for i, p in enumerate(illustration_prompts)
        ])

        await send({"type": "story_complete"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await send({"type": "error", "message": str(exc)})
        except Exception:
            pass
        raise


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "nova_region": os.getenv("AWS_REGION", "us-east-1")}


# ── Serve frontend ─────────────────────────────────────────────────────────────

frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="static")


# ── Dev entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_config(config: dict):
    if "characters" not in config or not config["characters"]:
        raise ValueError("Config must include at least one character.")
    for char in config["characters"]:
        if "name" not in char:
            raise ValueError("Each character must have a name.")
    if len(config["characters"]) > 5:
        raise ValueError("Maximum 5 characters supported.")
