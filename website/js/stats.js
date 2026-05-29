/* ============================================
   AI Coup Arena — Stats Page Logic
   Loads winrates.json, renders tables + charts
   ============================================ */

// Model display names and colors
const MODEL_META = {
  'anthropic/claude-opus-4.6-fast': { name: 'Claude', color: '#e94560', short: 'Claude' },
  'google/gemini-2.0-flash-001':   { name: 'Gemini', color: '#4285f4', short: 'Gemini' },
  'openai/gpt-4o':                 { name: 'ChatGPT', color: '#10a37f', short: 'ChatGPT' },
  'x-ai/grok-4.3':                 { name: 'Grok', color: '#64b4ff', short: 'Grok' },
  'mistralai/mistral-nemo':        { name: 'Mistral', color: '#ff7832', short: 'Mistral' },
  'perplexity/sonar':              { name: 'Perplexity', color: '#b482ff', short: 'Perplexity' },
};

function getModelName(model) {
  return MODEL_META[model]?.name || model.split('/').pop();
}

function getModelColor(model) {
  return MODEL_META[model]?.color || '#888';
}

let allData = [];
let sortCol = 'elo';
let sortDir = 'desc';

// --- Load data ---
async function init() {
  try {
    const resp = await fetch('data/winrates.json');
    allData = await resp.json();
    renderAll();
  } catch (err) {
    document.getElementById('leaderboard-body').innerHTML =
      '<tr><td colspan="7" style="text-align:center;color:#e94560;">Failed to load data</td></tr>';
    console.error(err);
  }
}

function renderAll() {
  renderSummaryStats();
  renderLeaderboard();
  renderDetailedTable();
  renderCharts();
}

// --- Summary Stats ---
function renderSummaryStats() {
  const totalGames = allData.reduce((s, r) => s + r.games_played, 0) / 4; // 4 players per game
  const totalQueries = allData.reduce((s, r) => s + r.total_queries, 0);
  const totalTokens = allData.reduce((s, r) => s + r.total_tokens, 0);
  const topElo = Math.max(...allData.map(r => r.elo));

  document.getElementById('stat-games').textContent = Math.round(totalGames).toLocaleString();
  document.getElementById('stat-queries').textContent = totalQueries.toLocaleString();
  document.getElementById('stat-tokens').textContent = (totalTokens / 1e6).toFixed(1) + 'M';
  document.getElementById('stat-top-elo').textContent = topElo.toFixed(1);
}

// --- Leaderboard (best config per model) ---
function renderLeaderboard() {
  // Group by model, find best config by ELO (with minimum 50 games)
  const byModel = {};
  for (const row of allData) {
    if (row.games_played < 50) continue;
    const model = row.model;
    if (!byModel[model] || row.elo > byModel[model].elo) {
      byModel[model] = row;
    }
  }

  const ranked = Object.values(byModel).sort((a, b) => b.elo - a.elo);
  const tbody = document.getElementById('leaderboard-body');
  tbody.innerHTML = '';

  ranked.forEach((row, i) => {
    const rank = i + 1;
    const rankClass = rank <= 3 ? `rank-${rank}` : '';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="${rankClass}">${rank}</td>
      <td><span class="model-badge ${getModelName(row.model).toLowerCase()}">${getModelName(row.model)}</span></td>
      <td>${row.elo.toFixed(1)}</td>
      <td>${(row.win_rate * 100).toFixed(1)}%</td>
      <td>${row.games_played}</td>
      <td>${formatConfig(row)}</td>
      <td>${(row.bluff_success_rate * 100).toFixed(0)}%</td>
    `;
    tbody.appendChild(tr);
  });
}

function formatConfig(row) {
  return `d=${row.history_depth}, r=${row.rules === 'Yes' || row.rules === 1 ? 'Y' : 'N'}, s=${row.strategy === 'Yes' || row.strategy === 1 ? 'Y' : 'N'}`;
}

// --- Detailed Filtered Table ---
function renderDetailedTable() {
  const modelFilter = document.getElementById('filter-model').value;
  const rulesFilter = document.getElementById('filter-rules').value;
  const strategyFilter = document.getElementById('filter-strategy').value;
  const minGames = parseInt(document.getElementById('filter-min-games').value) || 0;

  let filtered = allData.filter(row => {
    if (modelFilter && row.model !== modelFilter) return false;
    if (rulesFilter !== '' && String(row.rules) !== rulesFilter) return false;
    if (strategyFilter !== '' && String(row.strategy) !== strategyFilter) return false;
    if (row.games_played < minGames) return false;
    return true;
  });

  // Sort
  filtered.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return sortDir === 'asc' ? -1 : 1;
    if (va > vb) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  const tbody = document.getElementById('detailed-body');
  tbody.innerHTML = '';

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted);">No data matches filters</td></tr>';
    return;
  }

  for (const row of filtered) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="model-badge ${getModelName(row.model).toLowerCase()}">${getModelName(row.model)}</span></td>
      <td>${row.history_depth}</td>
      <td>${row.rules}</td>
      <td>${row.strategy}</td>
      <td>${row.games_played}</td>
      <td>${(row.win_rate * 100).toFixed(1)}%</td>
      <td>${row.elo.toFixed(1)}</td>
      <td>${(row.bluff_success_rate * 100).toFixed(0)}%</td>
      <td>${(row.challenge_success_rate * 100).toFixed(0)}%</td>
      <td>${row.avg_tokens_per_query.toFixed(0)}</td>
    `;
    tbody.appendChild(tr);
  }

  // Update sort indicators
  document.querySelectorAll('#detailed-table th.sortable').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.col === sortCol) {
      th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });
}

function handleSort(col) {
  if (sortCol === col) {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    sortCol = col;
    sortDir = 'desc';
  }
  renderDetailedTable();
}

// --- Charts ---
let charts = {};

function renderCharts() {
  renderWinRateChart();
  renderRadarChart();
  renderTokenChart();
}

function renderWinRateChart() {
  // Best config per model (min 50 games)
  const byModel = {};
  for (const row of allData) {
    if (row.games_played < 50) continue;
    if (!byModel[row.model] || row.elo > byModel[row.model].elo) {
      byModel[row.model] = row;
    }
  }

  const entries = Object.values(byModel).sort((a, b) => b.win_rate - a.win_rate);
  const labels = entries.map(r => getModelName(r.model));
  const values = entries.map(r => (r.win_rate * 100));
  const colors = entries.map(r => getModelColor(r.model));

  if (charts.winRate) charts.winRate.destroy();
  charts.winRate = new Chart(document.getElementById('chart-winrate'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Win Rate (%)',
        data: values,
        backgroundColor: colors.map(c => c + '99'),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 60,
          ticks: { color: '#b0b0c0', callback: v => v + '%' },
          grid: { color: 'rgba(245,197,24,0.08)' },
        },
        x: {
          ticks: { color: '#b0b0c0' },
          grid: { display: false },
        }
      }
    }
  });
}

function renderRadarChart() {
  // Behavioral profiles for best config per model (min 50 games)
  const byModel = {};
  for (const row of allData) {
    if (row.games_played < 50) continue;
    if (!byModel[row.model] || row.elo > byModel[row.model].elo) {
      byModel[row.model] = row;
    }
  }

  const models = Object.values(byModel).sort((a, b) => b.elo - a.elo);
  const datasets = models.map(row => ({
    label: getModelName(row.model),
    data: [
      row.win_rate * 100,
      row.bluff_success_rate * 100,
      row.challenge_success_rate * 100,
      row.card_guess_accuracy * 100,
      // Normalize tokens: lower is better, invert for radar
      Math.max(0, 100 - (row.avg_tokens_per_query / 25)),
    ],
    borderColor: getModelColor(row.model),
    backgroundColor: getModelColor(row.model) + '20',
    borderWidth: 2,
    pointBackgroundColor: getModelColor(row.model),
  }));

  if (charts.radar) charts.radar.destroy();
  charts.radar = new Chart(document.getElementById('chart-radar'), {
    type: 'radar',
    data: {
      labels: ['Win Rate', 'Bluff Success', 'Challenge Accuracy', 'Card Guess Accuracy', 'Token Efficiency'],
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#b0b0c0', padding: 15 },
        },
      },
      scales: {
        r: {
          beginAtZero: true,
          max: 100,
          ticks: {
            color: '#777799',
            backdropColor: 'transparent',
          },
          grid: { color: 'rgba(245,197,24,0.1)' },
          pointLabels: { color: '#b0b0c0', font: { size: 11 } },
          angleLines: { color: 'rgba(245,197,24,0.1)' },
        }
      }
    }
  });
}

function renderTokenChart() {
  // Token efficiency: avg tokens per query vs win rate (scatter-like via bar)
  const byModel = {};
  for (const row of allData) {
    if (row.games_played < 50) continue;
    if (!byModel[row.model] || row.elo > byModel[row.model].elo) {
      byModel[row.model] = row;
    }
  }

  const entries = Object.values(byModel).sort((a, b) => a.avg_tokens_per_query - b.avg_tokens_per_query);
  const labels = entries.map(r => getModelName(r.model));
  const tokenValues = entries.map(r => r.avg_tokens_per_query);
  const winValues = entries.map(r => (r.win_rate * 100));
  const colors = entries.map(r => getModelColor(r.model));

  if (charts.tokens) charts.tokens.destroy();
  charts.tokens = new Chart(document.getElementById('chart-tokens'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Avg Tokens/Query',
          data: tokenValues,
          backgroundColor: colors.map(c => c + '66'),
          borderColor: colors,
          borderWidth: 2,
          borderRadius: 6,
          yAxisID: 'y',
        },
        {
          label: 'Win Rate (%)',
          data: winValues,
          type: 'line',
          borderColor: '#f5c518',
          backgroundColor: '#f5c51833',
          borderWidth: 3,
          pointRadius: 5,
          pointBackgroundColor: '#f5c518',
          fill: false,
          yAxisID: 'y1',
          tension: 0.3,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#b0b0c0' },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          position: 'left',
          ticks: { color: '#b0b0c0' },
          grid: { color: 'rgba(245,197,24,0.08)' },
          title: { display: true, text: 'Tokens/Query', color: '#b0b0c0' },
        },
        y1: {
          beginAtZero: true,
          position: 'right',
          ticks: { color: '#f5c518', callback: v => v + '%' },
          grid: { display: false },
          title: { display: true, text: 'Win Rate', color: '#f5c518' },
        },
        x: {
          ticks: { color: '#b0b0c0' },
          grid: { display: false },
        }
      }
    }
  });
}

// --- Populate filter dropdowns ---
function populateFilters() {
  const modelSelect = document.getElementById('filter-model');
  const models = [...new Set(allData.map(r => r.model))].sort();
  for (const m of models) {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = getModelName(m);
    modelSelect.appendChild(opt);
  }
}

// --- Event listeners ---
document.addEventListener('DOMContentLoaded', () => {
  init().then(() => {
    populateFilters();
  });

  // Filter changes
  ['filter-model', 'filter-rules', 'filter-strategy', 'filter-min-games'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderDetailedTable);
  });

  // Sort clicks
  document.querySelectorAll('#detailed-table th.sortable').forEach(th => {
    th.addEventListener('click', () => handleSort(th.dataset.col));
  });
});
