/* ─── Fable — Frontend ──────────────────────────────────────────────────────── */

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
  charIdMap: {},         // char_id → display name (from world_ready)
  lastConfig: null,      // last generation config — for "Same World, New Story"
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

// ─── Intro typewriter sequence ──────────────────────────────────────────────────
// Runs once on page load: ornament fades in → title types → tagline types → body reveals

function runIntro() {
  const ornament = $('header-ornament');
  const titleEl  = $('header-title');
  const tagEl    = $('header-tagline');
  const bodyEl   = $('setup-body');

  const TITLE   = 'Fable';
  const TAGLINE = 'Characters with secrets. Stories that choose their own ending.';

  // Phase 1 — ornament fades in
  setTimeout(() => {
    ornament.classList.add('visible');
  }, 180);

  // Phase 2 — title types in, letter by letter (slow, deliberate)
  function typeTitle(onDone) {
    let i = 0;

    // Insert the block cursor
    const cursor = document.createElement('span');
    cursor.className = 'intro-cursor';
    titleEl.appendChild(cursor);

    function step() {
      if (i < TITLE.length) {
        cursor.insertAdjacentText('beforebegin', TITLE[i++]);
        setTimeout(step, 110 + Math.random() * 60);  // 110–170 ms per char — weighty
      } else {
        // Pause, then widen letter-spacing and remove cursor
        setTimeout(() => {
          titleEl.classList.add('done');
          setTimeout(() => {
            cursor.remove();
            if (onDone) onDone();
          }, 400);
        }, 300);
      }
    }
    setTimeout(step, 0);
  }

  // Phase 3 — tagline types in (faster, italic whisper)
  function typeTagline(onDone) {
    let i = 0;
    function step() {
      if (i < TAGLINE.length) {
        tagEl.textContent += TAGLINE[i++];
        setTimeout(step, 28 + Math.random() * 12);
      } else {
        if (onDone) onDone();
      }
    }
    setTimeout(step, 0);
  }

  // Sequence: wait → type title → pause → type tagline → reveal body
  setTimeout(() => {
    typeTitle(() => {
      setTimeout(() => {
        typeTagline(() => {
          setTimeout(() => {
            bodyEl.classList.add('visible');
          }, 200);
        });
      }, 160);
    });
  }, 320);
}

runIntro();

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

// ─── Theme background crossfade ────────────────────────────────────────────────

let _bgActive = 'a';

function setThemeBg(preset) {
  const next   = _bgActive === 'a' ? 'b' : 'a';
  const nextEl = $('tbg-' + next);
  const curEl  = $('tbg-' + _bgActive);

  // Assign new theme class to the off-screen layer, then cross-fade
  const cls = preset ? `tbg-${preset}` : 'tbg-enchanted_forest';
  nextEl.className = `theme-bg-layer ${cls}`;
  nextEl.classList.add('active');
  curEl.classList.remove('active');

  _bgActive = next;
}

// ─── Setup interactions ─────────────────────────────────────────────────────────

document.querySelectorAll('.theme-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    state.selectedPreset = card.dataset.preset;
    state.selectedTheme  = card.dataset.theme;
    $('custom-theme').value = '';
    $('custom-panel').classList.remove('active');
    fillPresetChars(state.selectedPreset);
    setThemeBg(state.selectedPreset);
  });
});

// Custom world panel interactions
const _customPanel = $('custom-panel');
const _customInput = $('custom-theme');

_customInput.addEventListener('focus', () => {
  document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
  _customPanel.classList.add('active');
  state.selectedPreset = '';
  setThemeBg('custom');
});

_customInput.addEventListener('input', () => {
  const val = _customInput.value.trim();
  state.selectedTheme = val || null;
  if (val) _customPanel.classList.add('active');
});

_customInput.addEventListener('blur', () => {
  if (!_customInput.value.trim()) {
    _customPanel.classList.remove('active');
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

  const config = {
    theme:     state.selectedTheme || $('custom-theme').value.trim() || 'magical adventure',
    preset:    state.selectedPreset || '',
    characters,
    max_turns: state.maxTurns,
  };
  state.lastConfig = config;
  startGeneration(config);
});

// ─── WebSocket ─────────────────────────────────────────────────────────────────

function startGeneration(config) {
  cleanup3D();
  showScreen('simulation-screen');
  clearSimLog();
  setProgress(0);
  Object.assign(state, {
    pages: [], eventLog: [], worldSummary: {},
    illustrationPrompts: [], pageImages: [], charIdMap: {},
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
      // Build char_id → name map for divergence viz
      (msg.characters || []).forEach(c => { state.charIdMap[c.id] = c.name; });
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

    case 'goal_achieved_event': {
      const { character_name, goal } = msg;
      addLog('goal-achieved', null, `★ ${character_name} achieved their goal: "${goal}"`);
      break;
    }

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

let _logGen = 0;  // incremented on clear — orphaned typeText callbacks self-cancel

function clearSimLog() { _logGen++; $('sim-log').innerHTML = ''; }
function setStatus(t)  { $('sim-status-text').textContent = t; }
function setProgress(p){ $('progress-bar').style.width = `${p}%`; }

// Typewriter — types `fullText` into `el`, then calls onDone.
// Uses generation guard so stale callbacks after clearSimLog are no-ops.
function typeText(el, fullText, msPerChar, onDone) {
  const gen = _logGen;
  let i = 0;

  // Blinking cursor stays at the end while typing
  const cursor = document.createElement('span');
  cursor.className = 'type-cursor';
  el.appendChild(cursor);

  const simLog = $('sim-log');

  function step() {
    if (_logGen !== gen) return;          // log was cleared — abandon
    if (i < fullText.length) {
      cursor.insertAdjacentText('beforebegin', fullText[i++]);
      simLog.scrollTop = simLog.scrollHeight;
      setTimeout(step, msPerChar + Math.random() * 10);
    } else {
      cursor.remove();
      simLog.scrollTop = simLog.scrollHeight;
      if (onDone) onDone();
    }
  }

  // First character after a small delay so the entry slide-in plays first
  setTimeout(step, 30);
}

function addLog(type, charName, text, motivation) {
  const log   = $('sim-log');
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;

  if (type === 'action' && charName) {
    // Char tag appears instantly
    const ci  = state.charColorMap[charName] ?? 0;
    const tag = document.createElement('span');
    tag.className  = 'char-tag';
    tag.dataset.ci = ci;
    tag.textContent = charName;
    entry.appendChild(tag);

    // Main action text — speed adapts to length so long lines don't drag
    const txt = document.createElement('span');
    entry.appendChild(txt);
    const mainSpeed = Math.min(20, Math.max(10, Math.round(1400 / Math.max(text.length, 1))));

    typeText(txt, text, mainSpeed, motivation ? () => {
      // Motivation types in after a brief pause
      const m = document.createElement('span');
      m.className = 'motivation-text';
      entry.appendChild(m);
      setTimeout(() => typeText(m, ` — ${motivation}`, 12), 60);
    } : null);

  } else {
    const txt = document.createElement('span');
    entry.appendChild(txt);
    const speed = type === 'goal-achieved' ? 24
                : type === 'turn-marker'   ? 22
                : 16;
    typeText(txt, text, speed);
  }
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

  // 3D book-opening splash — plays over the rendered storybook then fades away
  initBook3D(sn);
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

  const onPage = state.spreadIndex >= 0;
  $('read-aloud-btn').disabled = !onPage || !window.speechSynthesis;
  if (!onPage) stopReading();

  if (state.spreadIndex === -1) {
    $('page-indicator').textContent = `Cover  ·  ${state.pages.length} pages`;
  } else {
    $('page-indicator').textContent =
      `Page ${state.spreadIndex + 1}  of  ${state.pages.length}`;
  }
}

$('prev-btn').addEventListener('click', () => {
  if (state.spreadIndex > -1) { stopReading(); state.spreadIndex--; renderSpread(); }
});
$('next-btn').addEventListener('click', () => {
  if (state.spreadIndex < state.pages.length - 1) { stopReading(); state.spreadIndex++; renderSpread(); }
});
$('restart-btn').addEventListener('click', () => { stopReading(); cleanup3D(); showScreen('setup-screen'); });

$('rerun-btn').addEventListener('click', () => {
  stopReading();
  cleanup3D();
  if (!state.lastConfig) { showScreen('setup-screen'); return; }
  startGeneration(state.lastConfig);
});

// ─── Read Aloud (Web Speech API) ───────────────────────────────────────────────

let _reading = false;

function stopReading() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  _reading = false;
  const btn = $('read-aloud-btn');
  if (btn) { btn.textContent = '▶ Read Aloud'; btn.classList.remove('reading'); }
}

function readPageAloud(idx) {
  if (!window.speechSynthesis) return;
  const page = state.pages[idx];
  if (!page) return;

  if (_reading) { stopReading(); return; }   // toggle off

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(page.text);
  utterance.rate  = 0.88;   // gentle bedtime pace
  utterance.pitch = 1.05;
  utterance.volume = 1.0;

  // Prefer a warm English voice
  const pick = () => {
    const voices = window.speechSynthesis.getVoices();
    return (
      voices.find(v => /Samantha|Karen|Moira|Fiona/.test(v.name)) ||
      voices.find(v => v.lang === 'en-US' && !v.name.includes('Google')) ||
      voices.find(v => v.lang.startsWith('en'))
    );
  };
  const v = pick();
  if (v) utterance.voice = v;

  utterance.onend = () => stopReading();
  utterance.onerror = () => stopReading();

  _reading = true;
  const btn = $('read-aloud-btn');
  btn.textContent = '■ Stop Reading';
  btn.classList.add('reading');
  window.speechSynthesis.speak(utterance);
}

$('read-aloud-btn').addEventListener('click', () => {
  if (state.spreadIndex >= 0) readPageAloud(state.spreadIndex);
});

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

  // Build full character list from color map keys
  const allCharNames = Object.keys(state.charColorMap);

  state.eventLog.forEach(evt => {
    const isGoal = evt.action_type === 'goal_achieved';

    const entry = document.createElement('div');
    entry.className = isGoal ? 'log-entry goal-achieved' : 'log-entry action';
    entry.style.animation = 'none';

    if (isGoal) {
      entry.textContent = `★ ${evt.description}`;
    } else {
      const actorName = state.charIdMap[evt.actor] || evt.actor || '?';
      const ci  = state.charColorMap[actorName] ?? 0;
      const tag = document.createElement('span');
      tag.className   = 'char-tag';
      tag.dataset.ci  = ci;
      tag.textContent = actorName;
      entry.appendChild(tag);

      const txt = document.createElement('span');
      txt.textContent = ` T${evt.turn} · ${evt.description}`;
      entry.appendChild(txt);

      // ── Knowledge divergence: show who saw vs who missed this event ──
      if (evt.witnessed_by && allCharNames.length > 0) {
        const witnessNames = (evt.witnessed_by || [])
          .map(id => state.charIdMap[id] || id)
          .filter(Boolean);
        const missedNames = allCharNames.filter(n => !witnessNames.includes(n));

        const div = document.createElement('div');
        div.className = 'witness-row';

        if (witnessNames.length) {
          const saw = document.createElement('span');
          saw.className = 'witness-tag saw';
          saw.textContent = `saw: ${witnessNames.join(', ')}`;
          div.appendChild(saw);
        }
        if (missedNames.length) {
          const missed = document.createElement('span');
          missed.className = 'witness-tag missed';
          missed.textContent = `missed: ${missedNames.join(', ')}`;
          div.appendChild(missed);
        }
        entry.appendChild(div);
      }
    }

    container.appendChild(entry);
  });
}

// ─── 3D Book Opening Animation (Three.js) ──────────────────────────────────────

function cleanup3D() {
  if (state._book3d) {
    if (state._book3d.animId) cancelAnimationFrame(state._book3d.animId);
    if (state._book3d.renderer) state._book3d.renderer.dispose();
    state._book3d = null;
  }
  const splash = $('book-3d-splash');
  if (splash) {
    splash.style.display = 'none';
    splash.style.opacity = '';
    splash.style.transition = '';
    splash.innerHTML = '';
  }
}

function transitionTo2D() {
  const splash = $('book-3d-splash');
  // Cancel the animation loop before fading
  if (state._book3d && state._book3d.animId) {
    cancelAnimationFrame(state._book3d.animId);
    state._book3d.animId = null;
  }
  splash.style.transition = 'opacity 0.7s ease';
  splash.style.opacity = '0';
  setTimeout(cleanup3D, 750);
}

function initBook3D(settingName) {
  if (typeof THREE === 'undefined') return;   // CDN not loaded

  const splash = $('book-3d-splash');
  cleanup3D();                                // clear any stale previous run
  splash.style.opacity = '1';
  splash.style.transition = '';
  splash.style.display = 'block';

  const W = window.innerWidth;
  const H = window.innerHeight;

  // ── Scene ──────────────────────────────────────────────────────────────────
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x060c07);

  const camera = new THREE.PerspectiveCamera(46, W / H, 0.1, 50);
  camera.position.set(0, 1.1, 4.2);
  camera.lookAt(0, 0.1, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(W, H);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  splash.appendChild(renderer.domElement);

  state._book3d = { renderer, animId: null };

  // ── Lighting ───────────────────────────────────────────────────────────────
  scene.add(new THREE.AmbientLight(0xffffff, 0.38));
  const key = new THREE.DirectionalLight(0xf5dfa0, 1.0);
  key.position.set(2, 5, 3);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x304830, 0.3);
  fill.position.set(-3, -1, -2);
  scene.add(fill);

  // ── Book dimensions ────────────────────────────────────────────────────────
  const bW = 1.15;   // width (X)
  const bH = 1.55;   // depth/height of book (Z, portrait)
  const bD = 0.09;   // thickness (Y)

  // ── Book group (all geometry — rotated together in phase 2) ────────────────
  const bookGroup = new THREE.Group();
  scene.add(bookGroup);

  // Pages block (base) — parchment top, leather bottom
  const baseMats = [
    new THREE.MeshLambertMaterial({ color: 0xd8c9a8 }), // right edge
    new THREE.MeshLambertMaterial({ color: 0x182d1a }), // left edge (spine side)
    new THREE.MeshLambertMaterial({ color: 0xd8c9a8 }), // top (inside pages)
    new THREE.MeshLambertMaterial({ color: 0x182d1a }), // bottom (back cover)
    new THREE.MeshLambertMaterial({ color: 0xd8c9a8 }), // front edge
    new THREE.MeshLambertMaterial({ color: 0xd8c9a8 }), // back edge
  ];
  const baseGeo = new THREE.BoxGeometry(bW, bD, bH);
  const base    = new THREE.Mesh(baseGeo, baseMats);
  base.position.y = -bD / 2;
  bookGroup.add(base);

  // Spine strip
  const spineGeo = new THREE.BoxGeometry(0.055, bD + 0.004, bH);
  const spineMat = new THREE.MeshLambertMaterial({ color: 0x0d1f0f });
  const spineObj = new THREE.Mesh(spineGeo, spineMat);
  spineObj.position.set(-bW / 2 - 0.027, 0, 0);
  bookGroup.add(spineObj);

  // ── Cover canvas texture ───────────────────────────────────────────────────
  const cvs = document.createElement('canvas');
  cvs.width = 512; cvs.height = 682;
  const ctx = cvs.getContext('2d');

  // Leather background
  ctx.fillStyle = '#182d1a';
  ctx.fillRect(0, 0, 512, 682);

  // Outer gold border
  ctx.strokeStyle = '#9a7018';
  ctx.lineWidth = 7;
  ctx.strokeRect(16, 16, 480, 650);

  // Inner gold border
  ctx.strokeStyle = '#c09028';
  ctx.lineWidth = 2;
  ctx.strokeRect(26, 26, 460, 630);

  // Corner ornaments
  ctx.fillStyle = '#c09028';
  ctx.font = '18px serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  [[32, 32], [480, 32], [32, 650], [480, 650]].forEach(([cx, cy]) => {
    ctx.fillText('✦', cx, cy);
  });

  // Title (word-wrapped)
  ctx.fillStyle = '#d8b878';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.font = 'italic 300 44px Georgia, serif';

  const titleWords = settingName.split(' ');
  const titleLines = [];
  let cur = '';
  for (const w of titleWords) {
    const test = cur ? cur + ' ' + w : w;
    if (ctx.measureText(test).width > 390 && cur) {
      titleLines.push(cur);
      cur = w;
    } else {
      cur = test;
    }
  }
  if (cur) titleLines.push(cur);

  const lineH  = 58;
  const totalH = titleLines.length * lineH;
  let ty = 341 - totalH / 2 + lineH * 0.78;
  for (const line of titleLines) {
    ctx.fillText(line, 256, ty);
    ty += lineH;
  }

  // Ornament above title
  ctx.fillStyle = '#c09028';
  ctx.font = '30px serif';
  ctx.fillText('✦', 256, 341 - totalH / 2 - 16);

  // Thin rule under ornament
  ctx.strokeStyle = '#9a7018';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(136, 341 - totalH / 2 - 3);
  ctx.lineTo(376, 341 - totalH / 2 - 3);
  ctx.stroke();

  // Subtitle
  ctx.fillStyle = '#7a6848';
  ctx.font = '300 20px Georgia, serif';
  ctx.fillText('An Emergent Story', 256, 341 + totalH / 2 + 36);

  const coverTex = new THREE.CanvasTexture(cvs);

  // ── Cover pivot (hinge at spine) ───────────────────────────────────────────
  // Phase 1: cover swings outward around the spine (rotation.z, 0 → π)
  const coverPivot = new THREE.Group();
  coverPivot.position.set(-bW / 2, 0, 0);   // hinge at spine
  bookGroup.add(coverPivot);

  // Outside face — textured leather cover; center at (bW/2, bD/2+ε, 0) in pivot-local space
  const coverOutGeo = new THREE.PlaneGeometry(bW, bH);
  const coverOutMat = new THREE.MeshLambertMaterial({ map: coverTex, side: THREE.FrontSide });
  const coverOut    = new THREE.Mesh(coverOutGeo, coverOutMat);
  coverOut.rotation.x = -Math.PI / 2;
  coverOut.position.set(bW / 2, bD / 2 + 0.002, 0);
  coverPivot.add(coverOut);

  // Inside face — dark leather (visible once cover swings past vertical)
  const coverInGeo = new THREE.PlaneGeometry(bW, bH);
  const coverInMat = new THREE.MeshLambertMaterial({ color: 0x0e1e10, side: THREE.FrontSide });
  const coverIn    = new THREE.Mesh(coverInGeo, coverInMat);
  coverIn.rotation.x = Math.PI / 2;
  coverIn.position.set(bW / 2, bD / 2 + 0.001, 0);
  coverPivot.add(coverIn);

  // ── Animation loop ─────────────────────────────────────────────────────────
  // Two phases within a single timeline (t = 0→1):
  //   Phase 1 (t 0.00→0.55): cover swings open around spine (rotation.z)
  //   Phase 2 (t 0.50→1.00): open book tilts toward camera + camera zooms
  let startTs    = null;
  const DELAY    = 600;    // ms — pause before animation begins
  const DURATION = 3200;   // ms — total animation duration

  function easeInOut(t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }
  function easeIn(t)    { return t * t * t; }

  function animate(ts) {
    if (!startTs) startTs = ts;
    const elapsed = ts - startTs;

    if (elapsed > DELAY) {
      const t = Math.min((elapsed - DELAY) / DURATION, 1.0);

      // Phase 1 — cover opens outward around the spine
      const t1 = Math.min(t / 0.55, 1.0);
      coverPivot.rotation.z = easeInOut(t1) * Math.PI;

      // Phase 2 — open book tilts toward camera + camera zooms in
      if (t > 0.50) {
        const t2 = easeIn((t - 0.50) / 0.50);
        bookGroup.rotation.x = t2 * (Math.PI / 3);
        camera.position.z    = 4.2 - t2 * 1.5;
        camera.position.y    = 1.1 - t2 * 0.4;
      }
    }

    renderer.render(scene, camera);

    if (elapsed >= DELAY + DURATION) {
      transitionTo2D();
      return;
    }

    state._book3d.animId = requestAnimationFrame(animate);
  }

  state._book3d.animId = requestAnimationFrame(animate);
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
