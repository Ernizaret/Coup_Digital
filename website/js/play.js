/* ============================================
   AI Coup Arena -- Play Page Logic
   Setup forms, WebSocket client, game renderer
   ============================================ */

// --- Constants ---
const MODEL_BADGE_CLASSES = {
  'Claude': 'claude',
  'ChatGPT': 'chatgpt',
  'Gemini': 'gemini',
  'Grok': 'grok',
  'Mistral': 'mistral',
  'Perplexity': 'perplexity',
};

const CARD_SHORT = {
  'Duke': 'D',
  'Assassin': 'A',
  'Captain': 'C',
  'Ambassador': 'Am',
  'Contessa': 'Co',
};

// --- State ---
let currentMode = 'bot';
let availableAgents = [];
let botPlayers = [];       // [{name, model, provider}]
let humanOpponents = [];   // [{name, model, provider}]
let ws = null;
let gameId = null;
let gameMode = null;
let humanPlayerName = null;
let isAwaitingHumanInput = false;

// Per-player configs (keyed by index in the player list)
let botPlayerConfigs = {};    // { index: {history_depth, rules_summary, strategy_guide} }
let humanPlayerConfigs = {};

// Determine API base URL (same origin when served by FastAPI)
const API_BASE = '';
function getWsBase() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}`;
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
  loadAvailableAgents();
});

async function loadAvailableAgents() {
  try {
    const resp = await fetch(`${API_BASE}/api/config`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    availableAgents = data.agents || [];
    renderAgentButtons();
  } catch (err) {
    console.error('Failed to load config:', err);
    document.getElementById('bot-agent-buttons').innerHTML =
      '<span class="text-red">Failed to connect to server. Make sure the FastAPI server is running.</span>';
    document.getElementById('human-agent-buttons').innerHTML =
      '<span class="text-red">Failed to connect to server. Make sure the FastAPI server is running.</span>';
  }
}

function renderAgentButtons() {
  const botContainer = document.getElementById('bot-agent-buttons');
  const humanContainer = document.getElementById('human-agent-buttons');

  const html = availableAgents.map(agent => {
    const badgeClass = MODEL_BADGE_CLASSES[agent.name] || '';
    return `<button class="agent-btn ${badgeClass}" onclick="addPlayer('${agent.name}', '${agent.model}')">${agent.name}</button>`;
  }).join('');

  botContainer.innerHTML = html || '<span class="text-muted">No models configured in ai_config.json</span>';
  humanContainer.innerHTML = html.replace(/addPlayer\(/g, 'addOpponent(') ||
    '<span class="text-muted">No models configured in ai_config.json</span>';
}

// --- Mode Switching ---
function switchMode(mode) {
  currentMode = mode;

  document.getElementById('tab-bot-match').classList.toggle('active', mode === 'bot');
  document.getElementById('tab-human-match').classList.toggle('active', mode === 'human');
  document.getElementById('bot-setup').style.display = mode === 'bot' ? 'block' : 'none';
  document.getElementById('human-setup').style.display = mode === 'human' ? 'block' : 'none';
}

// --- Bot vs Bot: Player Management ---
function addPlayer(providerName, model) {
  if (botPlayers.length >= 6) return;

  // Build display name with numbering
  const count = botPlayers.filter(p => p.provider === providerName).length;
  const displayName = count > 0 ? `${providerName} ${count + 1}` : providerName;

  // If this is the second of this provider, rename the first
  if (count === 1) {
    // Don't rename -- convention keeps first as bare name
  }

  botPlayers.push({ name: displayName, model, provider: providerName });
  renderBotPlayerList();
  updateBotStartBtn();
}

function removePlayer(index) {
  botPlayers.splice(index, 1);
  // Rebuild names to handle numbering
  rebuildBotPlayerNames();
  renderBotPlayerList();
  updateBotStartBtn();
}

function movePlayer(index, direction) {
  const newIndex = index + direction;
  if (newIndex < 0 || newIndex >= botPlayers.length) return;
  [botPlayers[index], botPlayers[newIndex]] = [botPlayers[newIndex], botPlayers[index]];
  renderBotPlayerList();
}

function rebuildBotPlayerNames() {
  const counts = {};
  botPlayers.forEach(p => {
    counts[p.provider] = (counts[p.provider] || 0) + 1;
    const n = counts[p.provider];
    p.name = n > 1 ? `${p.provider} ${n}` : p.provider;
  });
}

function renderBotPlayerList() {
  const container = document.getElementById('bot-player-list');
  if (botPlayers.length === 0) {
    container.innerHTML = '<div class="text-muted" style="padding:0.5rem;">No players added yet. Click a model above to add.</div>';
    renderBotPerPlayerConfig();
    return;
  }

  container.innerHTML = botPlayers.map((p, i) => {
    const badgeClass = MODEL_BADGE_CLASSES[p.provider] || '';
    return `
      <div class="player-list-item">
        <span class="player-order">${i + 1}</span>
        <span class="player-name"><span class="model-badge ${badgeClass}">${p.name}</span></span>
        <span class="player-model">${p.model}</span>
        <div class="player-controls">
          <button onclick="movePlayer(${i}, -1)" title="Move up" ${i === 0 ? 'disabled' : ''}>&#x25B2;</button>
          <button onclick="movePlayer(${i}, 1)" title="Move down" ${i === botPlayers.length - 1 ? 'disabled' : ''}>&#x25BC;</button>
          <button onclick="removePlayer(${i})" title="Remove">&#x2715;</button>
        </div>
      </div>
    `;
  }).join('');

  renderBotPerPlayerConfig();
}

function renderBotPerPlayerConfig() {
  const container = document.getElementById('bot-per-player-config');
  if (botPlayers.length === 0) {
    container.innerHTML = '<p class="text-muted">Add players first, then configure them individually.</p>';
    return;
  }

  container.innerHTML = botPlayers.map((p, i) => {
    const cfg = botPlayerConfigs[i] || { history_depth: 2, rules_summary: false, strategy_guide: false };
    const badgeClass = MODEL_BADGE_CLASSES[p.provider] || '';
    return `
      <div class="per-player-card">
        <h4><span class="model-badge ${badgeClass}">${p.name}</span></h4>
        <div class="config-row">
          <div class="config-field">
            <label>History Depth</label>
            <input type="number" value="${cfg.history_depth}" min="0" max="20"
              onchange="botPlayerConfigs[${i}] = botPlayerConfigs[${i}] || {history_depth:2,rules_summary:false,strategy_guide:false}; botPlayerConfigs[${i}].history_depth = parseInt(this.value)">
          </div>
          <div class="config-field">
            <label>Rules Summary</label>
            <input type="checkbox" ${cfg.rules_summary ? 'checked' : ''}
              onchange="botPlayerConfigs[${i}] = botPlayerConfigs[${i}] || {history_depth:2,rules_summary:false,strategy_guide:false}; botPlayerConfigs[${i}].rules_summary = this.checked">
          </div>
          <div class="config-field">
            <label>Strategy Guide</label>
            <input type="checkbox" ${cfg.strategy_guide ? 'checked' : ''}
              onchange="botPlayerConfigs[${i}] = botPlayerConfigs[${i}] || {history_depth:2,rules_summary:false,strategy_guide:false}; botPlayerConfigs[${i}].strategy_guide = this.checked">
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function updateBotStartBtn() {
  const btn = document.getElementById('bot-start-btn');
  btn.disabled = botPlayers.length < 2;
}

// --- Human vs Bot: Opponent Management ---
function addOpponent(providerName, model) {
  if (humanOpponents.length >= 5) return;

  const count = humanOpponents.filter(p => p.provider === providerName).length;
  const displayName = count > 0 ? `${providerName} ${count + 1}` : providerName;

  humanOpponents.push({ name: displayName, model, provider: providerName });
  renderHumanOpponentList();
  updateHumanStartBtn();
  updatePositionOptions();
}

function removeOpponent(index) {
  humanOpponents.splice(index, 1);
  rebuildHumanOpponentNames();
  renderHumanOpponentList();
  updateHumanStartBtn();
  updatePositionOptions();
}

function moveOpponent(index, direction) {
  const newIndex = index + direction;
  if (newIndex < 0 || newIndex >= humanOpponents.length) return;
  [humanOpponents[index], humanOpponents[newIndex]] = [humanOpponents[newIndex], humanOpponents[index]];
  renderHumanOpponentList();
}

function rebuildHumanOpponentNames() {
  const counts = {};
  humanOpponents.forEach(p => {
    counts[p.provider] = (counts[p.provider] || 0) + 1;
    const n = counts[p.provider];
    p.name = n > 1 ? `${p.provider} ${n}` : p.provider;
  });
}

function renderHumanOpponentList() {
  const container = document.getElementById('human-opponent-list');
  if (humanOpponents.length === 0) {
    container.innerHTML = '<div class="text-muted" style="padding:0.5rem;">No opponents added yet. Click a model above to add.</div>';
    renderHumanPerPlayerConfig();
    return;
  }

  container.innerHTML = humanOpponents.map((p, i) => {
    const badgeClass = MODEL_BADGE_CLASSES[p.provider] || '';
    return `
      <div class="player-list-item">
        <span class="player-order">${i + 1}</span>
        <span class="player-name"><span class="model-badge ${badgeClass}">${p.name}</span></span>
        <span class="player-model">${p.model}</span>
        <div class="player-controls">
          <button onclick="moveOpponent(${i}, -1)" title="Move up" ${i === 0 ? 'disabled' : ''}>&#x25B2;</button>
          <button onclick="moveOpponent(${i}, 1)" title="Move down" ${i === humanOpponents.length - 1 ? 'disabled' : ''}>&#x25BC;</button>
          <button onclick="removeOpponent(${i})" title="Remove">&#x2715;</button>
        </div>
      </div>
    `;
  }).join('');

  renderHumanPerPlayerConfig();
}

function renderHumanPerPlayerConfig() {
  const container = document.getElementById('human-per-player-config');
  if (humanOpponents.length === 0) {
    container.innerHTML = '<p class="text-muted">Add opponents first, then configure them individually.</p>';
    return;
  }

  container.innerHTML = humanOpponents.map((p, i) => {
    const cfg = humanPlayerConfigs[i] || { history_depth: 2, rules_summary: false, strategy_guide: false };
    const badgeClass = MODEL_BADGE_CLASSES[p.provider] || '';
    return `
      <div class="per-player-card">
        <h4><span class="model-badge ${badgeClass}">${p.name}</span></h4>
        <div class="config-row">
          <div class="config-field">
            <label>History Depth</label>
            <input type="number" value="${cfg.history_depth}" min="0" max="20"
              onchange="humanPlayerConfigs[${i}] = humanPlayerConfigs[${i}] || {history_depth:2,rules_summary:false,strategy_guide:false}; humanPlayerConfigs[${i}].history_depth = parseInt(this.value)">
          </div>
          <div class="config-field">
            <label>Rules Summary</label>
            <input type="checkbox" ${cfg.rules_summary ? 'checked' : ''}
              onchange="humanPlayerConfigs[${i}] = humanPlayerConfigs[${i}] || {history_depth:2,rules_summary:false,strategy_guide:false}; humanPlayerConfigs[${i}].rules_summary = this.checked">
          </div>
          <div class="config-field">
            <label>Strategy Guide</label>
            <input type="checkbox" ${cfg.strategy_guide ? 'checked' : ''}
              onchange="humanPlayerConfigs[${i}] = humanPlayerConfigs[${i}] || {history_depth:2,rules_summary:false,strategy_guide:false}; humanPlayerConfigs[${i}].strategy_guide = this.checked">
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function updateHumanStartBtn() {
  const btn = document.getElementById('human-start-btn');
  btn.disabled = humanOpponents.length < 1;
}

function updatePositionOptions() {
  const select = document.getElementById('human-position');
  const total = humanOpponents.length + 1;
  // Preserve current value
  const currentVal = select.value;

  select.innerHTML = '';
  for (let i = 0; i < total; i++) {
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = `Seat ${i + 1}`;
    select.appendChild(opt);
  }
  const randOpt = document.createElement('option');
  randOpt.value = 'random';
  randOpt.textContent = 'Random';
  select.appendChild(randOpt);

  // Restore if still valid
  if ([...select.options].some(o => o.value === currentVal)) {
    select.value = currentVal;
  }
}

// --- Start Bot Match ---
async function startBotMatch() {
  const btn = document.getElementById('bot-start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  const seedInput = document.getElementById('bot-seed').value;
  const surveyInterval = parseInt(document.getElementById('bot-survey-interval').value) || 0;

  // Build config arrays
  const historyDepths = botPlayers.map((_, i) => {
    const cfg = botPlayerConfigs[i];
    return cfg ? cfg.history_depth : 2;
  });
  const rulesSummaries = botPlayers.map((_, i) => {
    const cfg = botPlayerConfigs[i];
    return cfg ? cfg.rules_summary : false;
  });
  const strategyGuides = botPlayers.map((_, i) => {
    const cfg = botPlayerConfigs[i];
    return cfg ? cfg.strategy_guide : false;
  });

  const body = {
    agents: botPlayers.map(p => p.provider),
    seed: seedInput ? parseInt(seedInput) : null,
    survey_interval: surveyInterval,
    history_depths: historyDepths,
    rules_summaries: rulesSummaries,
    strategy_guides: strategyGuides,
  };

  try {
    const resp = await fetch(`${API_BASE}/api/game/bot-match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    gameId = data.game_id;
    gameMode = 'bot';
    humanPlayerName = null;

    // Show game viewer
    showGameViewer(data.players);

    // Connect WebSocket
    connectWebSocket(gameId);

  } catch (err) {
    alert(`Failed to start match: ${err.message}`);
    btn.disabled = false;
    btn.textContent = 'Start Match';
  }
}

// --- Start Human Match ---
async function startHumanMatch() {
  const btn = document.getElementById('human-start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  const seedInput = document.getElementById('human-seed').value;
  const positionVal = document.getElementById('human-position').value;
  const position = positionVal === 'random'
    ? Math.floor(Math.random() * (humanOpponents.length + 1))
    : parseInt(positionVal);

  const historyDepths = humanOpponents.map((_, i) => {
    const cfg = humanPlayerConfigs[i];
    return cfg ? cfg.history_depth : 2;
  });
  const rulesSummaries = humanOpponents.map((_, i) => {
    const cfg = humanPlayerConfigs[i];
    return cfg ? cfg.rules_summary : false;
  });
  const strategyGuides = humanOpponents.map((_, i) => {
    const cfg = humanPlayerConfigs[i];
    return cfg ? cfg.strategy_guide : false;
  });

  const body = {
    opponents: humanOpponents.map(p => p.provider),
    player_position: position,
    seed: seedInput ? parseInt(seedInput) : null,
    history_depths: historyDepths,
    rules_summaries: rulesSummaries,
    strategy_guides: strategyGuides,
  };

  try {
    const resp = await fetch(`${API_BASE}/api/game/human-match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    gameId = data.game_id;
    gameMode = 'human';
    humanPlayerName = data.human_player;

    showGameViewer(data.players);
    connectWebSocket(gameId);

  } catch (err) {
    alert(`Failed to start game: ${err.message}`);
    btn.disabled = false;
    btn.textContent = 'Start Game';
  }
}

// --- Game Viewer ---
function showGameViewer(players) {
  document.getElementById('mode-section').style.display = 'none';
  document.getElementById('game-section').style.display = 'block';
  document.getElementById('game-over-panel').style.display = 'none';
  document.getElementById('game-log').innerHTML = '<div class="text-muted" style="padding:0.5rem;">Connecting to game...</div>';

  // Show human panel only in human mode
  document.getElementById('human-action-panel').style.display =
    gameMode === 'human' ? 'block' : 'none';

  // Initialize player status cards
  const statusBar = document.getElementById('player-status-bar');
  statusBar.innerHTML = players.map(p => {
    const badgeClass = MODEL_BADGE_CLASSES[p.name] || (p.model === 'human' ? '' : '');
    const isHuman = p.model === 'human';
    return `
      <div class="player-status-card" id="ps-${sanitize(p.name)}">
        <div class="ps-name">${p.name}${isHuman ? ' (You)' : ''}</div>
        <div class="ps-model"><span class="model-badge ${badgeClass}">${isHuman ? 'Human' : p.name}</span></div>
        <div class="ps-stats">
          <div class="ps-stat">
            <span class="ps-stat-value" id="ps-coins-${sanitize(p.name)}">2</span>
            <span class="ps-stat-label">Coins</span>
          </div>
          <div class="ps-stat">
            <span class="ps-stat-value" id="ps-influence-${sanitize(p.name)}">2</span>
            <span class="ps-stat-label">Cards</span>
          </div>
        </div>
        <div class="ps-cards" id="ps-cards-${sanitize(p.name)}">
          <div class="card-icon hidden">?</div>
          <div class="card-icon hidden">?</div>
        </div>
      </div>
    `;
  }).join('');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function sanitize(name) {
  return name.replace(/[^a-zA-Z0-9]/g, '_');
}

// --- WebSocket ---
function connectWebSocket(gameId) {
  const wsUrl = `${getWsBase()}/ws/game/${gameId}`;
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('WebSocket connected');
    appendToLog('Connected to game server.', 'event');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWsMessage(msg);
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
    }
  };

  ws.onclose = (event) => {
    console.log('WebSocket closed:', event.code, event.reason);
    if (event.code !== 1000) {
      appendToLog('Connection lost. Refresh to reconnect.', 'event');
    }
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
  };
}

function handleWsMessage(msg) {
  switch (msg.type) {
    case 'connected':
      document.getElementById('game-seed-display').textContent =
        msg.seed ? `Seed: ${msg.seed}` : '';
      document.getElementById('game-log').innerHTML = '';
      appendToLog('Game started!', 'event');
      break;

    case 'game_started':
      document.getElementById('game-log').innerHTML = '';
      appendToLog('Game started!', 'event');
      break;

    case 'turn_start':
      appendToLog(`Turn ${msg.turn_number} -- ${msg.player}'s turn`, 'turn');
      highlightActivePlayer(msg.player);
      break;

    case 'agent_response':
      const speechPart = msg.speech && msg.speech !== '(silent)'
        ? msg.speech : null;
      if (speechPart) {
        appendToLog(`${msg.player}: "${speechPart}"`, 'speech');
      }
      appendToLog(`${msg.player} chose: ${msg.action}`, 'action', msg.player, msg.action);
      break;

    case 'event':
      if (msg.text) {
        appendToLog(msg.text, 'event');
      }
      break;

    case 'game_state':
      updateGameState(msg);
      break;

    case 'awaiting_human_input':
      showHumanInput(msg);
      break;

    case 'game_over':
      handleGameOver(msg);
      break;

    case 'error':
      appendToLog(`Error: ${msg.message}`, 'event');
      break;

    case 'pong':
      break;

    default:
      console.log('Unknown message type:', msg.type);
  }
}

// --- Game State Updates ---
function updateGameState(state) {
  if (state.seed) {
    document.getElementById('game-seed-display').textContent = `Seed: ${state.seed}`;
  }

  if (!state.players) return;

  for (const p of state.players) {
    const nameId = sanitize(p.name);

    // Update coins and influence
    const coinsEl = document.getElementById(`ps-coins-${nameId}`);
    const influenceEl = document.getElementById(`ps-influence-${nameId}`);
    if (coinsEl) coinsEl.textContent = p.coins;
    if (influenceEl) influenceEl.textContent = p.influence_count;

    // Update card display
    const cardsEl = document.getElementById(`ps-cards-${nameId}`);
    if (cardsEl) {
      let cardsHtml = '';

      // Show hand for human player
      if (p.hand) {
        for (const card of p.hand) {
          cardsHtml += `<div class="card-icon hand">${card}</div>`;
        }
      } else {
        // Hidden cards
        for (let i = 0; i < p.influence_count; i++) {
          cardsHtml += '<div class="card-icon hidden">?</div>';
        }
      }

      // Revealed cards
      if (p.revealed) {
        for (const card of p.revealed) {
          const short = CARD_SHORT[card] || card[0];
          cardsHtml += `<div class="card-icon revealed" title="${card}">${short}</div>`;
        }
      }

      cardsEl.innerHTML = cardsHtml;
    }

    // Update alive/eliminated status
    const cardEl = document.getElementById(`ps-${nameId}`);
    if (cardEl) {
      cardEl.classList.toggle('eliminated', !p.alive);
    }

    // Update human hand display
    if (gameMode === 'human' && p.name === humanPlayerName && p.hand) {
      updateHumanHand(p.hand);
    }
  }
}

function highlightActivePlayer(playerName) {
  // Remove active from all
  document.querySelectorAll('.player-status-card').forEach(el => {
    el.classList.remove('active-turn');
  });
  const nameId = sanitize(playerName);
  const el = document.getElementById(`ps-${nameId}`);
  if (el) el.classList.add('active-turn');
}

function updateHumanHand(hand) {
  const handEl = document.getElementById('human-hand');
  handEl.innerHTML = '<span class="hand-label">Your Hand:</span>' +
    hand.map(card => `<div class="card-icon hand">${card}</div>`).join('');
}

// --- Human Input ---
function showHumanInput(msg) {
  isAwaitingHumanInput = true;
  const panel = document.getElementById('human-action-panel');
  const promptEl = document.getElementById('human-prompt');
  const optionsEl = document.getElementById('human-options');

  panel.style.display = 'block';
  promptEl.textContent = msg.message;

  // Determine which options are "primary" actions
  const primaryActions = ['Income', 'Foreign Aid', 'Tax', 'Steal', 'Exchange', 'Assassinate', 'Coup', 'Yes'];

  optionsEl.innerHTML = msg.options.map(option => {
    const isPrimary = primaryActions.includes(option);
    return `<button class="human-option-btn ${isPrimary ? 'primary-action' : ''}"
              onclick="sendHumanAction('${escapeQuotes(option)}')">${option}</button>`;
  }).join('');

  // Scroll to the action panel
  panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function sendHumanAction(action) {
  if (!ws || !isAwaitingHumanInput) return;

  ws.send(JSON.stringify({
    type: 'human_action',
    action: action,
    speech: '',
  }));

  isAwaitingHumanInput = false;

  // Clear the options
  document.getElementById('human-options').innerHTML =
    '<span class="text-muted">Waiting for other players...</span>';
  document.getElementById('human-prompt').textContent = 'Action sent. Waiting...';
}

function escapeQuotes(str) {
  return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// --- Game Log ---
function appendToLog(text, type, playerName, actionChoice) {
  const logEl = document.getElementById('game-log');

  const entry = document.createElement('div');

  switch (type) {
    case 'turn':
      entry.className = 'log-entry-turn';
      entry.textContent = text;
      break;
    case 'speech':
      entry.className = 'log-entry-speech';
      entry.textContent = text;
      break;
    case 'action':
      entry.className = 'log-entry-action';
      if (playerName && actionChoice) {
        entry.innerHTML = `<span class="action-player">${escapeHtml(playerName)}</span> chose: <span class="action-choice">${escapeHtml(actionChoice)}</span>`;
      } else {
        entry.textContent = text;
      }
      break;
    case 'event':
    default:
      entry.className = 'log-entry-event';
      entry.textContent = text;
      break;
  }

  logEl.appendChild(entry);

  // Auto-scroll to bottom
  logEl.scrollTop = logEl.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// --- Game Over ---
function handleGameOver(msg) {
  const panel = document.getElementById('game-over-panel');
  const title = document.getElementById('game-over-title');
  const message = document.getElementById('game-over-message');

  panel.style.display = 'block';

  if (gameMode === 'human' && msg.winner_name === humanPlayerName) {
    title.textContent = 'You Win!';
    message.textContent = 'Congratulations! You defeated the AI opponents.';
  } else {
    title.textContent = 'Game Over';
    message.textContent = `${msg.winner_name} (${msg.winner_model}) wins!`;
  }

  // Hide human input panel
  document.getElementById('human-action-panel').style.display = 'none';

  appendToLog(`Game Over! ${msg.winner_name} wins!`, 'turn');

  // Close WebSocket
  if (ws) {
    ws.close(1000, 'Game over');
    ws = null;
  }
}

// --- Play Again ---
function playAgain() {
  // Reset state
  gameId = null;
  gameMode = null;
  humanPlayerName = null;
  isAwaitingHumanInput = false;

  // Show setup, hide game
  document.getElementById('mode-section').style.display = 'block';
  document.getElementById('game-section').style.display = 'none';

  // Reset buttons
  document.getElementById('bot-start-btn').textContent = 'Start Match';
  document.getElementById('bot-start-btn').disabled = botPlayers.length < 2;
  document.getElementById('human-start-btn').textContent = 'Start Game';
  document.getElementById('human-start-btn').disabled = humanOpponents.length < 1;

  window.scrollTo({ top: 0, behavior: 'smooth' });
}
