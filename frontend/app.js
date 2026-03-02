/* ─── Emergent Story Engine — Frontend ─────────────────────────────────────── */

const WS_URL = `ws://${location.host}/ws/generate`;

// ─── State ─────────────────────────────────────────────────────────────────────

const state = {
  selectedPreset: null,
  selectedTheme: null,
  pages: [],
  illustrationPrompts: [],
  pageImages: [],        // base64 PNG per page index, filled progressively
  eventLog: [],
  worldSummary: {},
  spreadIndex: -1,      // -1 = cover, 0..N-1 = story pages (one page per spread)
  maxTurns: 8,
  ws: null,
  charColorMap: {},
};

// ─── Presets ───────────────────────────────────────────────────────────────────

const PRESET_DEFAULTS = {
  enchanted_forest: [
    { name: "Lily",    traits: "curious, brave, warm-hearted",       goal: "Find the healing blossom that will cure her grandmother", fear: "Being lost alone in the dark forest" },
    { name: "Bramble", traits: "grumpy, wise, secretly gentle",      goal: "Protect the ancient forest from any who would harm it",   fear: "Being forgotten when the old trees are gone" },
    { name: "Pip",     traits: "mischievous, quick, fiercely loyal", goal: "Collect enough golden acorns to fill his treasure chest", fear: "Bramble discovering his secret acorn stash" },
  ],
  pirate_ship: [
    { name: "Captain Rora", traits: "bold, fair, secretly homesick",  goal: "Find the treasure map that leads to her home island",   fear: "The crew losing trust in her" },
    { name: "Finn",         traits: "clumsy, enthusiastic, honest",   goal: "Prove himself brave enough to join the crew properly",  fear: "The deep water below the ship" },
    { name: "Silver",       traits: "cunning, quiet, misunderstood",  goal: "Trade the hidden compass for safe passage home",        fear: "Anyone finding out she's not really a pirate" },
  ],
  space_station: [
    { name: "Nova",   traits: "brilliant, impatient, kind",       goal: "Fix the broken star-map before the crew gets lost forever", fear: "Making a mistake that hurts someone" },
    { name: "Zephyr", traits: "calm, observant, mysterious",      goal: "Send a secret message to her home planet",                  fear: "Being sent back before her mission is done" },
    { name: "Bolt",   traits: "cheerful, loyal, accident-prone",  goal: "Find the missing power crystal in the engine room",         fear: "The lights going out completely" },
  ],
  underwater_kingdom: [
    { name: "Pearl", traits: "gentle, determined, imaginative",    goal: "Return the stolen trident to its rightful place",                    fear: "The dark depths of the deep trench" },
    { name: "Cora",  traits: "sharp-tongued, brave, caring",       goal: "Find out who is making the ocean currents go wrong",                 fear: "Losing her best friend" },
    { name: "Tide",  traits: "dreamy, magical, easily distracted", goal: "Discover whether the sunken ship holds his family's lost treasure",   fear: "Remembering too much of the past" },
  ],
};

// ─── DOM helpers ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  $(id).classList.add('active');
  window.scrollTo(0, 0);
}

function getCharConfigs() {
  return Array.from(document.querySelectorAll('.char-card')).map(card => ({
    name:               card.querySelector('.char-name').value.trim(),
    personality_traits: card.querySelector('.char-traits').value.trim(),
    goal:               card.querySelector('.char-goal').value.trim(),
    fear:               card.querySelector('.char-fear').value.trim(),
  })).filter(c => c.name);
}

function fillPresetChars(preset) {
  const defaults = PRESET_DEFAULTS[preset] || [];
  document.querySelectorAll('.char-card').forEach((card, i) => {
    if (!defaults[i]) return;
    const d = defaults[i];
    card.querySelector('.char-name').value   = d.name;
    card.querySelector('.char-traits').value = d.traits;
    card.querySelector('.char-goal').value   = d.goal;
    card.querySelector('.char-fear').value   = d.fear;
  });
}

// ─── Setup interactions ─────────────────────────────────────────────────────────

document.querySelectorAll('.theme-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    state.selectedPreset = card.dataset.preset;
    state.selectedTheme  = card.dataset.theme;
    $('custom-theme').value = '';
    fillPresetChars(state.selectedPreset);
  });
});

$('custom-theme').addEventListener('input', () => {
  if ($('custom-theme').value.trim()) {
    document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
    state.selectedPreset = '';
    state.selectedTheme  = $('custom-theme').value.trim();
  }
});

const maxTurnsInput = $('max-turns');
maxTurnsInput.addEventListener('input', () => {
  state.maxTurns = parseInt(maxTurnsInput.value, 10);
  $('turns-display').textContent = `${state.maxTurns} turns`;
});

document.querySelector('.theme-card[data-preset="enchanted_forest"]').click();

// ─── Generate ──────────────────────────────────────────────────────────────────

$('generate-btn').addEventListener('click', () => {
  const characters = getCharConfigs();
  if (!characters.length) { alert('Please name at least one character.'); return; }

  state.charColorMap = {};
  characters.forEach((c, i) => { state.charColorMap[c.name] = i % 5; });

  startGeneration({
    theme:     state.selectedTheme || $('custom-theme').value.trim() || 'magical adventure',
    preset:    state.selectedPreset || '',
    characters,
    max_turns: state.maxTurns,
  });
});

// ─── WebSocket ─────────────────────────────────────────────────────────────────

function startGeneration(config) {
  showScreen('simulation-screen');
  clearSimLog();
  setProgress(0);
  Object.assign(state, {
    pages: [], eventLog: [], worldSummary: {},
    illustrationPrompts: [], pageImages: [],
  });

  const ws = new WebSocket(WS_URL);
  state.ws = ws;
  ws.onopen    = () => ws.send(JSON.stringify(config));
  ws.onmessage = e  => handleMessage(JSON.parse(e.data), config);
  ws.onerror   = ()  => showError('Could not connect. Is the backend running on port 8000?');
}

function handleMessage(msg, config) {
  switch (msg.type) {

    case 'status':
      setStatus(msg.message);
      addLog('status', null, msg.message);
      break;

    case 'world_ready': {
      const locs = Object.keys(msg.world?.locations || {});
      addLog('status', null, `World: ${msg.world?.setting_name || '…'}`);
      if (locs.length) addLog('status', null, locs.join('  ·  '));
      setProgress(8);
      break;
    }

    case 'character_action': {
      const { turn, character_name, action } = msg;
      const verb   = action.action_type || 'act';
      const detail = action.dialogue ? `"${action.dialogue}"` : (action.target || '');
      addLog('action', character_name,
        `Turn ${turn}  ·  ${verb}${detail ? ': ' + detail : ''}`,
        action.internal_motivation);
      setProgress(Math.min(8 + (turn / config.max_turns) * 70, 78));
      break;
    }

    case 'turn_complete':
      addLog('turn-marker', null, `turn ${msg.turn} resolved`);
      break;

    case 'story_text_ready':
      // Story text arrived — switch to storybook, images will stream in
      setProgress(85);
      state.pages               = msg.pages || [];
      state.illustrationPrompts = msg.illustration_prompts || [];
      state.eventLog            = msg.event_log || [];
      state.worldSummary        = msg.world_summary || {};
      // Pre-fill pageImages with empty placeholders
      state.pageImages = new Array(state.pages.length).fill('');
      renderStorybook();
      break;

    case 'page_image':
      // A single image arrived — update that page's slot and re-render if visible
      state.pageImages[msg.index] = msg.image || '';
      updatePageImageIfVisible(msg.index);
      break;

    case 'story_complete':
      setProgress(100);
      break;

    case 'error':
      showError(msg.message);
      break;
  }
}

// ─── Sim log ───────────────────────────────────────────────────────────────────

function clearSimLog() { $('sim-log').innerHTML = ''; }
function setStatus(t)  { $('sim-status-text').textContent = t; }
function setProgress(p){ $('progress-bar').style.width = `${p}%`; }

function addLog(type, charName, text, motivation) {
  const log   = $('sim-log');
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;

  if (type === 'action' && charName) {
    const ci  = state.charColorMap[charName] ?? 0;
    const tag = document.createElement('span');
    tag.className  = 'char-tag';
    tag.dataset.ci = ci;
    tag.textContent = charName;
    entry.appendChild(tag);

    const txt = document.createElement('span');
    txt.textContent = text;
    entry.appendChild(txt);

    if (motivation) {
      const m = document.createElement('span');
      m.className   = 'motivation-text';
      m.textContent = ` — ${motivation}`;
      entry.appendChild(m);
    }
  } else {
    entry.textContent = text;
  }

  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function showError(msg) {
  showScreen('simulation-screen');
  const box = document.createElement('div');
  box.className = 'error-box';
  box.innerHTML = `<strong>Something went wrong</strong><br>${msg}`;
  $('sim-log').appendChild(box);
}

// ─── Storybook ─────────────────────────────────────────────────────────────────

function renderStorybook() {
  // Show the screen first so elements are in the layout
  showScreen('storybook-screen');

  populateReplayLog();

  const sn = state.worldSummary.setting_name || 'A Magical World';
  $('story-title').textContent    = sn;
  $('story-subtitle').textContent =
    `${state.worldSummary.total_events || 0} events · ${state.worldSummary.total_turns || 0} turns · ${state.pages.length} pages`;

  state.spreadIndex = -1;
  renderSpread();
}

function renderSpread() {
  const L = $('page-left');
  const R = $('page-right');

  // Fade out
  L.style.opacity = '0';
  R.style.opacity = '0';

  // Render then fade in
  requestAnimationFrame(() => {
    try {
      if (state.spreadIndex === -1) {
        renderCover(L, R);
      } else {
        const idx = state.spreadIndex;
        renderTextPage(L, idx);
        renderImagePage(R, idx);
      }
      updateNav();
    } catch (err) {
      console.error('renderSpread error:', err);
    }

    // Use setTimeout to ensure the opacity:0 frame is committed before fading in
    setTimeout(() => {
      L.style.opacity = '';
      R.style.opacity = '';
    }, 20);
  });
}

function renderCover(L, R) {
  const worldName = state.worldSummary.setting_name || 'A Magical World';

  L.className = 'book-page left cover';
  L.innerHTML = `
    <span class="cover-ornament">✦</span>
    <div class="cover-title">${escHtml(worldName)}</div>
    <div class="cover-rule"></div>
    <div class="cover-tagline">A story shaped by choices</div>
    <div class="cover-chars">${getCharNames().join('  ·  ')}</div>
  `;

  R.className = 'book-page right';
  R.innerHTML = `
    <div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;
                gap:1rem;text-align:center;padding:2rem;">
      <div style="font-family:var(--display);font-size:0.68rem;letter-spacing:0.18em;
                  text-transform:uppercase;color:var(--page-edge);">An emergent tale</div>
      <div style="font-family:var(--display);font-style:italic;font-size:1.5rem;
                  color:var(--ink-2);line-height:1.3;">${escHtml(worldName)}</div>
      <div style="width:40%;height:1px;background:linear-gradient(to right,
                  transparent,var(--page-edge),transparent);"></div>
      <div style="font-family:var(--serif);font-size:0.85rem;color:var(--ink-3);
                  font-style:italic;line-height:1.7;">
        In which ${getCharNames().join(', ')}<br>
        each pursued their own secret aim,<br>
        and a story emerged from their choices.
      </div>
    </div>
    <div class="page-num">❧</div>
  `;
}

function renderTextPage(el, idx) {
  const page = state.pages[idx];
  if (!page) {
    el.className = 'book-page left';
    el.innerHTML = `<div class="end-page"><span>❧</span><span>The End</span></div>`;
    return;
  }

  el.className = 'book-page left';
  el.innerHTML = `
    <p class="page-text${idx === 0 ? ' drop-cap' : ''}">${escHtml(page.text)}</p>
    ${page.scene_description
      ? `<p class="scene-desc">${escHtml(page.scene_description)}</p>`
      : ''}
    <div class="page-num">${page.page}</div>
  `;
}

function renderImagePage(el, idx) {
  const img64  = state.pageImages[idx] || '';
  const prompt = state.illustrationPrompts[idx] || '';

  el.className = 'book-page right image-page';
  el.dataset.pageIdx = idx;   // for live updates

  if (img64) {
    el.innerHTML = `<img class="page-illustration" src="data:image/png;base64,${img64}" alt="Story illustration" />`;
  } else {
    // Placeholder — shows while image is still generating
    el.innerHTML = `
      <div class="illus-placeholder">
        <div class="illus-spinner"></div>
        ${prompt
          ? `<div class="vision-card" style="margin-top:1rem;">
               <span class="vision-card-label">Illustrator's Vision</span>
               <p class="vision-text">${escHtml(prompt)}</p>
             </div>`
          : '<p style="font-family:var(--serif);font-style:italic;color:var(--ink-3);font-size:0.85rem;">Painting…</p>'}
      </div>
    `;
  }
}

// Called when a new image arrives — updates the page if it's currently visible
function updatePageImageIfVisible(idx) {
  const el = document.querySelector(`.image-page[data-page-idx="${idx}"]`);
  if (el && state.pageImages[idx]) {
    el.innerHTML = `<img class="page-illustration" src="data:image/png;base64,${state.pageImages[idx]}" alt="Story illustration" />`;
  }
}

function updateNav() {
  const maxSpread = state.pages.length - 1;
  $('prev-btn').disabled = state.spreadIndex <= -1;
  $('next-btn').disabled = state.spreadIndex >= maxSpread;

  if (state.spreadIndex === -1) {
    $('page-indicator').textContent = `Cover  ·  ${state.pages.length} pages`;
  } else {
    $('page-indicator').textContent =
      `Page ${state.spreadIndex + 1}  of  ${state.pages.length}`;
  }
}

$('prev-btn').addEventListener('click', () => {
  if (state.spreadIndex > -1) { state.spreadIndex--; renderSpread(); }
});
$('next-btn').addEventListener('click', () => {
  if (state.spreadIndex < state.pages.length - 1) { state.spreadIndex++; renderSpread(); }
});
$('restart-btn').addEventListener('click', () => showScreen('setup-screen'));

// ─── Replay log ─────────────────────────────────────────────────────────────────

let replayOpen = false;
$('log-toggle-btn').addEventListener('click', () => {
  replayOpen = !replayOpen;
  $('replay-log').classList.toggle('open', replayOpen);
  $('log-toggle-btn').textContent = replayOpen ? 'Hide Simulation Log' : 'Show Simulation Log';
});

function populateReplayLog() {
  const container = $('replay-log');
  container.innerHTML = '';
  state.eventLog.forEach(evt => {
    const entry = document.createElement('div');
    entry.className = 'log-entry action';
    entry.style.animation = 'none';

    const ci  = state.charColorMap[evt.actor] ?? 0;
    const tag = document.createElement('span');
    tag.className   = 'char-tag';
    tag.dataset.ci  = ci;
    tag.textContent = evt.actor || '?';
    entry.appendChild(tag);

    const txt = document.createElement('span');
    txt.textContent = ` T${evt.turn} · ${evt.description}`;
    entry.appendChild(txt);

    container.appendChild(entry);
  });
}

// ─── Keyboard ───────────────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (!$('storybook-screen').classList.contains('active')) return;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') $('next-btn').click();
  if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   $('prev-btn').click();
});

// ─── Utils ──────────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getCharNames() {
  return getCharConfigs().map(c => c.name).filter(Boolean);
}
