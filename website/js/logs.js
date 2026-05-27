/* ============================================
   AI Coup Arena — Game Logs Page Logic
   Loads logs_index.json, renders filterable list,
   fetches + renders individual game logs & reviews
   ============================================ */

const MODEL_COLORS = {
  'Claude': '#e94560',
  'ChatGPT': '#10a37f',
  'Grok': '#64b4ff',
  'Gemini': '#4285f4',
  'Mistral': '#ff7832',
  'Perplexity': '#b482ff',
};

function getModelBadgeClass(name) {
  return name.toLowerCase();
}

let allLogs = [];
let filteredLogs = [];
let currentPage = 1;
const PAGE_SIZE = 50;

// Base paths for fetching log/review files
// Uses relative paths: works when served from repo root (GitHub Pages)
// or when opened locally with the website/ folder as context
const LOGS_BASE = '../AI_game/logs/';
const REVIEWS_BASE = '../AI_game/review/';

// Fallback: if running from GitHub Pages root, try without ../
async function fetchWithFallback(primaryUrl) {
  let resp = await fetch(primaryUrl);
  if (resp.ok) return resp;
  // Try without leading ../  (in case site is served from repo root subfolder)
  const altUrl = primaryUrl.replace('../', '');
  resp = await fetch(altUrl);
  return resp;
}

// --- State ---
let viewerOpen = false;

// --- Init ---
async function init() {
  try {
    const resp = await fetch('data/logs_index.json');
    allLogs = await resp.json();
    populateFilters();
    applyFilters();
  } catch (err) {
    document.getElementById('log-list').innerHTML =
      '<div class="card" style="text-align:center;color:#e94560;">Failed to load game log index.</div>';
    console.error(err);
  }
}

// --- Filters ---
function populateFilters() {
  // Winner models
  const winners = [...new Set(allLogs.map(l => l.winner).filter(Boolean))].sort();
  const winnerSelect = document.getElementById('filter-winner');
  for (const w of winners) {
    const opt = document.createElement('option');
    opt.value = w;
    opt.textContent = w;
    winnerSelect.appendChild(opt);
  }

  // Player count
  const playerCounts = [...new Set(allLogs.map(l => l.players.length))].sort();
  const countSelect = document.getElementById('filter-players');
  for (const c of playerCounts) {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c + ' players';
    countSelect.appendChild(opt);
  }

  // Update total count
  document.getElementById('total-count').textContent = allLogs.length;
}

function applyFilters() {
  const search = document.getElementById('search-input').value.toLowerCase().trim();
  const winner = document.getElementById('filter-winner').value;
  const playerCount = document.getElementById('filter-players').value;
  const reviewOnly = document.getElementById('filter-review').checked;

  filteredLogs = allLogs.filter(log => {
    if (winner && log.winner !== winner) return false;
    if (playerCount && log.players.length !== parseInt(playerCount)) return false;
    if (reviewOnly && !log.has_review) return false;
    if (search) {
      const searchStr = [
        log.date,
        log.winner,
        ...log.players.map(p => p.name),
        ...log.players.map(p => p.model),
      ].join(' ').toLowerCase();
      if (!searchStr.includes(search)) return false;
    }
    return true;
  });

  currentPage = 1;
  document.getElementById('filtered-count').textContent = filteredLogs.length;
  renderLogList();
}

// --- Render log list ---
function renderLogList() {
  const listEl = document.getElementById('log-list');
  const totalPages = Math.ceil(filteredLogs.length / PAGE_SIZE);
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageItems = filteredLogs.slice(start, start + PAGE_SIZE);

  if (pageItems.length === 0) {
    listEl.innerHTML = '<div class="card" style="text-align:center;color:var(--text-muted);">No games match your filters.</div>';
    document.getElementById('pagination').innerHTML = '';
    return;
  }

  listEl.innerHTML = pageItems.map(log => `
    <div class="log-entry" onclick="openLog('${log.filename}', ${log.has_review})">
      <span class="log-date">${log.date || 'Unknown'}</span>
      <span class="log-players">
        ${log.players.map(p => `<span class="model-badge ${getModelBadgeClass(p.name)}">${p.name}</span>`).join(' ')}
      </span>
      <span class="log-winner">&#x1F3C6; ${log.winner || '?'}</span>
      <span class="log-turns">${log.turns} turns</span>
      ${log.has_review ? '<span class="log-review-badge">Review</span>' : ''}
    </div>
  `).join('');

  renderPagination(totalPages);
}

function renderPagination(totalPages) {
  const pag = document.getElementById('pagination');
  if (totalPages <= 1) {
    pag.innerHTML = '';
    return;
  }

  let html = '';
  html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">&#x25C0; Prev</button>`;

  // Show up to 7 page buttons
  const maxButtons = 7;
  let startPage = Math.max(1, currentPage - 3);
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);
  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  if (startPage > 1) {
    html += `<button onclick="goToPage(1)">1</button>`;
    if (startPage > 2) html += '<span class="page-info">...</span>';
  }

  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
  }

  if (endPage < totalPages) {
    if (endPage < totalPages - 1) html += '<span class="page-info">...</span>';
    html += `<button onclick="goToPage(${totalPages})">${totalPages}</button>`;
  }

  html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">Next &#x25B6;</button>`;

  pag.innerHTML = html;
}

function goToPage(page) {
  currentPage = page;
  renderLogList();
  document.getElementById('log-list').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// --- Log Viewer ---
async function openLog(filename, hasReview) {
  const viewerSection = document.getElementById('viewer-section');
  const indexSection = document.getElementById('index-section');
  const viewerContent = document.getElementById('viewer-content');
  const reviewTab = document.getElementById('tab-review');

  indexSection.style.display = 'none';
  viewerSection.style.display = 'block';
  viewerContent.innerHTML = '<div class="loading">Loading game log...</div>';

  // Show/hide review tab
  reviewTab.style.display = hasReview ? 'inline-block' : 'none';

  // Store current filename for tab switching
  viewerSection.dataset.filename = filename;
  viewerSection.dataset.hasReview = hasReview;

  // Activate log tab
  document.getElementById('tab-log').classList.add('active');
  reviewTab.classList.remove('active');

  try {
    const resp = await fetchWithFallback(LOGS_BASE + filename);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const md = await resp.text();
    viewerContent.innerHTML = renderMarkdown(md);
  } catch (err) {
    viewerContent.innerHTML = `<div style="color:#e94560;">Failed to load log: ${err.message}</div>`;
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function showReview() {
  const viewerSection = document.getElementById('viewer-section');
  const viewerContent = document.getElementById('viewer-content');
  const filename = viewerSection.dataset.filename;

  // Derive review filename from game filename
  const reviewFilename = filename.replace('game_', 'review_');

  document.getElementById('tab-log').classList.remove('active');
  document.getElementById('tab-review').classList.add('active');
  viewerContent.innerHTML = '<div class="loading">Loading review...</div>';

  try {
    const resp = await fetchWithFallback(REVIEWS_BASE + reviewFilename);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const md = await resp.text();
    viewerContent.innerHTML = renderMarkdown(md);
  } catch (err) {
    viewerContent.innerHTML = `<div style="color:#e94560;">Failed to load review: ${err.message}</div>`;
  }
}

async function showLog() {
  const viewerSection = document.getElementById('viewer-section');
  const filename = viewerSection.dataset.filename;
  const hasReview = viewerSection.dataset.hasReview === 'true';

  document.getElementById('tab-log').classList.add('active');
  document.getElementById('tab-review').classList.remove('active');

  await openLog(filename, hasReview);
}

function closeViewer() {
  document.getElementById('viewer-section').style.display = 'none';
  document.getElementById('index-section').style.display = 'block';
}

// --- Markdown Rendering ---
// Uses marked.js if available, otherwise a simple fallback
function renderMarkdown(md) {
  if (typeof marked !== 'undefined') {
    return marked.parse(md);
  }
  // Simple fallback
  return '<pre style="white-space:pre-wrap;font-size:0.9rem;">' + escapeHtml(md) + '</pre>';
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// --- Event Listeners ---
document.addEventListener('DOMContentLoaded', () => {
  init();

  document.getElementById('search-input').addEventListener('input', debounce(applyFilters, 300));
  document.getElementById('filter-winner').addEventListener('change', applyFilters);
  document.getElementById('filter-players').addEventListener('change', applyFilters);
  document.getElementById('filter-review').addEventListener('change', applyFilters);
});

// Debounce helper
function debounce(fn, ms) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}
