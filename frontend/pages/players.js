// pages/players.js
// Renders into #page-players and calls /api/players/search + /api/players/project

(function () {

    const container = document.getElementById('page-players');
  
    container.innerHTML = `
      <div class="page-header">
        <h1>PLAYER <span>PROJECTIONS</span></h1>
        <p>Project a player's stat line against a specific opponent, with season and H2H context.</p>
      </div>
  
      <div class="grid-2">
  
        <!-- Left: search form -->
        <div>
          <div class="card">
            <div class="card-title">Look Up a Player</div>
  
            <div class="form-group">
              <label class="form-label">Player Name</label>
              <input class="form-input" id="player-search-input"
                     type="text" placeholder="Start typing a name..." autocomplete="off" />
            </div>
  
            <!-- Search results dropdown -->
            <div id="player-search-results" style="display:none; margin-bottom:16px;">
              <div class="card-title">Search Results</div>
              <div id="player-results-list"></div>
            </div>
  
            <!-- Selected player display -->
            <div id="player-selected-display" style="display:none; margin-bottom:16px;">
              <div class="stat-row">
                <span class="stat-label">Selected Player</span>
                <span id="player-selected-name" class="badge badge-orange"></span>
              </div>
              <div class="stat-row">
                <span class="stat-label">Team</span>
                <span id="player-selected-team" class="badge badge-muted"></span>
              </div>
            </div>
  
            <div class="form-group">
              <label class="form-label">Opponent Team</label>
              <input class="form-input" id="player-opponent"
                     type="text" placeholder="e.g. MIA" maxlength="3"
                     style="text-transform:uppercase;" />
            </div>
  
            <div class="form-group">
              <label class="form-label">Home or Away?</label>
              <select class="form-select" id="player-is-home">
                <option value="1">Home</option>
                <option value="0">Away</option>
              </select>
            </div>
  
            <button class="btn btn-primary" id="player-project-btn"
                    style="width:100%;margin-top:4px;">
              Project Stats
            </button>
          </div>
        </div>
  
        <!-- Right: projection result -->
        <div id="player-result-pane">
          <div class="card">
            <div class="state-empty">
              <span class="icon">📊</span>
              Search for a player and select an opponent to see their projection.
            </div>
          </div>
        </div>
  
      </div>
    `;
  
    let selectedPlayer = null;
    let searchTimeout  = null;
  
    // ── Player search with debounce ───────────────────────────────
    document.getElementById('player-search-input').addEventListener('input', function () {
      clearTimeout(searchTimeout);
      const q = this.value.trim();
      if (q.length < 2) {
        document.getElementById('player-search-results').style.display = 'none';
        return;
      }
      searchTimeout = setTimeout(() => searchPlayers(q), 300);
    });
  
    async function searchPlayers(query) {
      const resultsWrap = document.getElementById('player-search-results');
      const resultsList = document.getElementById('player-results-list');
  
      resultsList.innerHTML = `<div style="font-size:13px;color:var(--muted);padding:8px 0;">Searching...</div>`;
      resultsWrap.style.display = 'block';
  
      try {
        const res  = await fetch(`${window.API}/players/search?name=${encodeURIComponent(query)}`);
        const data = await res.json();
  
        if (!data.success || !data.players.length) {
          resultsList.innerHTML = `<div style="font-size:13px;color:var(--muted);padding:8px 0;">No players found.</div>`;
          return;
        }
  
        resultsList.innerHTML = data.players.slice(0, 8).map(p => `
          <div class="stat-row" style="cursor:pointer;"
               onclick="window._selectPlayer(${p.player_id}, '${p.player_name}', '${p.team_abbreviation}')">
            <span class="stat-label">${p.player_name}</span>
            <span class="badge badge-muted">${p.team_abbreviation}</span>
          </div>
        `).join('');
  
      } catch {
        resultsList.innerHTML = `<div style="font-size:13px;color:var(--red);padding:8px 0;">Search failed.</div>`;
      }
    }
  
    // ── Select a player from results ─────────────────────────────
    window._selectPlayer = function (id, name, team) {
      selectedPlayer = { id, name, team };
  
      document.getElementById('player-search-input').value    = name;
      document.getElementById('player-search-results').style.display = 'none';
      document.getElementById('player-selected-display').style.display = 'block';
      document.getElementById('player-selected-name').textContent = name;
      document.getElementById('player-selected-team').textContent = team;
    };
  
    // ── Project stats ─────────────────────────────────────────────
    document.getElementById('player-project-btn').addEventListener('click', async () => {
      const opponent = document.getElementById('player-opponent').value.trim().toUpperCase();
      const isHome   = document.getElementById('player-is-home').value;
      const pane     = document.getElementById('player-result-pane');
  
      if (!selectedPlayer) {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">⚠️</span>Search and select a player first.</div>
        </div>`;
        return;
      }
  
      if (!opponent) {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">⚠️</span>Enter an opponent team abbreviation.</div>
        </div>`;
        return;
      }
  
      pane.innerHTML = `<div class="card"><div class="loading-bar"></div>
        <div style="color:var(--muted);font-size:13px;">Running projection...</div>
      </div>`;
  
      try {
        const res  = await fetch(`${window.API}/players/project`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            player_id: selectedPlayer.id,
            opponent,
            is_home: parseInt(isHome),
          }),
        });
        const data = await res.json();
  
        if (!data.success) {
          pane.innerHTML = `<div class="card">
            <div class="state-empty"><span class="icon">❌</span>${data.error}</div>
          </div>`;
          return;
        }
  
        renderProjection(data.data, pane);
  
      } catch {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">❌</span>Could not reach API.</div>
        </div>`;
      }
    });
  
    // ── Render projection ─────────────────────────────────────────
    function renderProjection(d, pane) {
      const stats  = ['pts', 'reb', 'ast', 'stl', 'blk'];
      const labels = { pts: 'Points', reb: 'Rebounds', ast: 'Assists',
                       stl: 'Steals',  blk: 'Blocks' };
  
      const h2hNote = d.h2h_game_count > 0
        ? `Based on ${d.h2h_game_count} prior matchup${d.h2h_game_count > 1 ? 's' : ''} vs ${d.opponent}`
        : `No prior matchup data vs ${d.opponent} — using season averages`;
  
      pane.innerHTML = `
        <div class="card">
          <div class="card-title">${d.player_name} vs ${d.opponent}</div>
  
          <div style="margin-bottom:16px;">
            <span class="badge badge-muted">${h2hNote}</span>
          </div>
  
          <!-- Stat comparison header -->
          <div style="display:grid;grid-template-columns:1fr repeat(3,80px);gap:8px;
                      font-size:11px;font-weight:600;letter-spacing:.07em;
                      text-transform:uppercase;color:var(--muted);
                      padding-bottom:8px;border-bottom:1px solid var(--border);">
            <span>Stat</span>
            <span style="text-align:center">Projected</span>
            <span style="text-align:center">Season avg</span>
            <span style="text-align:center">H2H avg</span>
          </div>
  
          ${stats.map(s => {
            const proj    = d[`projected_${s}`] ?? '—';
            const season  = d.rolling_avg_pts !== undefined && s === 'pts'
                            ? d.rolling_avg_pts : '—';
            const h2h     = s === 'pts' ? (d.h2h_avg_pts ?? '—') : '—';
  
            // Highlight if projection meaningfully exceeds season avg
            const isUp = typeof proj === 'number' && typeof season === 'number'
                         && proj > season * 1.1;
  
            return `
              <div style="display:grid;grid-template-columns:1fr repeat(3,80px);
                          gap:8px;padding:12px 0;border-bottom:1px solid var(--border);
                          align-items:center;">
                <span style="font-size:13px;color:var(--text)">${labels[s]}</span>
                <span style="text-align:center;">
                  <span class="stat-value ${isUp ? 'accent' : ''}"
                        style="font-size:24px;">${proj}</span>
                </span>
                <span style="text-align:center;font-size:15px;color:var(--muted);">${season}</span>
                <span style="text-align:center;font-size:15px;color:var(--gold);">${h2h}</span>
              </div>
            `;
          }).join('')}
  
          <div style="margin-top:12px;display:flex;gap:16px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);">
              <span style="font-family:var(--font-display);font-size:18px;color:var(--orange)">—</span>
              Projected
            </div>
            <div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);">
              <span style="font-size:14px;color:var(--muted)">—</span> Season avg (last 5)
            </div>
            <div style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);">
              <span style="font-size:14px;color:var(--gold)">—</span> H2H avg
            </div>
          </div>
        </div>
      `;
    }
  
    // ── Init ──────────────────────────────────────────────────────
    window.init_players = function () {};
  
  }());