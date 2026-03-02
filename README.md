# Emergent Story Engine
### Amazon Nova Hackathon — Agentic AI Category

A children's bedtime story generator where **characters drive the story, not the narrator**.
Each character has their own private world-view. Events happen because characters *acted*.
Every run produces a completely different story from the same starting setup.

---

## How It Works

```
User Input (theme + characters)
        ↓
Nova 2 Lite — World Generation (locations, objects, setting)
        ↓
┌─── Simulation Loop (N turns) ─────────────────────────────┐
│  For each character IN PARALLEL:                           │
│    Filter WorldState → character's personal knowledge view │
│    Nova 2 Lite: [personality + goal + knowledge] → Action  │
│                                                            │
│  Resolve actions → update WorldState                       │
│  Propagate: characters witness what happened near them     │
└────────────────────────────────────────────────────────────┘
        ↓
Nova Pro — Narrative Compilation (full event log → story pages)
        ↓
Nova 2 Lite — Illustration Prompt per page
        ↓
Storybook UI with page-flip rendering
```

**The key insight:** characters only know what they've personally witnessed.
Information asymmetry between them creates natural conflict and surprise — not scripted drama.

---

## Setup

### Prerequisites

- Python 3.11+
- AWS account with access to Amazon Bedrock
- AWS credentials configured (`~/.aws/credentials` or environment variables)
- Nova 2 Lite enabled in your Bedrock region (us-east-1 recommended)

### Install

```bash
cd backend
pip install -r requirements.txt
```

### Configure AWS

```bash
# Option A — AWS CLI
aws configure

# Option B — Environment variables
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
```

### Run

```bash
cd backend
python main.py
```

Then open **http://localhost:8000** in your browser.

---

## Model Usage

| Component              | Model         | Why                                      |
|------------------------|---------------|------------------------------------------|
| World generation       | Nova 2 Lite   | Fast structured JSON output              |
| Character decisions    | Nova 2 Lite   | Runs N×turns calls, needs speed + cost   |
| Action resolution      | Deterministic | No LLM needed — pure logic               |
| Narrative compilation  | Nova Pro      | One call, needs highest prose quality    |
| Illustration prompts   | Nova 2 Lite   | Simple descriptive generation            |

**Model IDs** (update in `backend/nova_client.py` if needed):
- `us.amazon.nova-2-lite-v1:0`
- `us.amazon.nova-pro-v1:0`

---

## File Structure

```
/
├── backend/
│   ├── main.py          # FastAPI app + WebSocket endpoint
│   ├── nova_client.py   # Bedrock Converse API wrapper
│   ├── world.py         # WorldState data structures
│   ├── character.py     # CharacterState + knowledge model
│   ├── prompts.py       # All Nova prompt templates
│   ├── simulation.py    # Multi-agent simulation loop
│   ├── resolver.py      # Deterministic action resolution
│   ├── compiler.py      # Narrative compilation + illustration prompts
│   └── requirements.txt
├── frontend/
│   ├── index.html       # Three-screen UI (setup / simulation / storybook)
│   ├── app.js           # WebSocket client + storybook rendering
│   └── styles.css       # Parchment storybook aesthetic
└── README.md
```

---

## Demo Script (3 min)

1. **(0:00–0:30)** — Pick "Enchanted Forest", show the 3 pre-filled characters with different secret goals
2. **(0:30–1:30)** — Click Generate. Watch the simulation log: character decisions firing in real time, events resolving, knowledge states diverging
3. **(1:30–2:30)** — Story compiles, storybook renders. Flip through pages — point out that events in the story trace back to character choices
4. **(2:30–3:00)** — Hit "Tell Another Story", same settings, generate again. **Show the judges a completely different story emerged from identical inputs.**

The second run is the money moment.

---

## Architecture Notes

### Information Asymmetry
Each character agent receives only what their character has personally witnessed. This is enforced at the prompt level — characters' `witnessed_events` are filtered from the global event log before the Nova call is made. A character who was in the Cave cannot act on something that happened in the Forest.

### Parallel Decisions
All character decisions within a turn run concurrently via `asyncio.gather()`. This keeps the simulation fast even with 3–5 characters.

### Narrative is Compiled, Not Authored
The Nova Pro compilation call receives the raw event log — a timestamped record of what actually happened. It doesn't invent events; it gives prose form to simulation output. The causality in the story is real.

### Deterministic Resolution
Action resolution (move, take, speak, give, hide, search) is handled by deterministic Python logic rather than LLM calls. This keeps the simulation stable and fast, and ensures world state integrity.
