// pages/games.js
// Renders into #page-games and calls /api/games/upcoming + /api/games/predict

(function () {

    const container = document.getElementById('page-games');
  
    container.innerHTML = `
      <div class="page-header">
        <h1>GAME <span>PREDICTIONS</span></h1>
        <p>Select a matchup to see win probability and key contributing factors.</p>
      </div>
  
      <div class="grid-2">
  
        <!-- Left: matchup selector -->
        <div>
          <div class="card">
            <div class="card-title">Select Matchup</div>
  
            <div class="form-group">
              <label class="form-label">Upcoming Games</label>
              <select class="form-select" id="games-upcoming-select">
                <option value="">Loading games...</option>
              </select>
            </div>
  
            <div style="display:flex;gap:10px;align-items:center;margin:16px 0 8px;">
              <div style="flex:1;height:1px;background:var(--border);"></div>
              <span style="font-size:11px;color:var(--muted);">OR ENTER MANUALLY</span>
              <div style="flex:1;height:1px;background:var(--border);"></div>
            </div>
  
            <div class="form-group">
              <label class="form-label">Home Team</label>
              <input class="form-input" id="games-home" type="text"
                     placeholder="e.g. BOS" maxlength="3" style="text-transform:uppercase;" />
            </div>
  
            <div class="form-group">
              <label class="form-label">Away Team</label>
              <input class="form-input" id="games-away" type="text"
                     placeholder="e.g. LAL" maxlength="3" style="text-transform:uppercase;" />
            </div>
  
            <button class="btn btn-primary" id="games-predict-btn"
                    style="width:100%;margin-top:4px;">
              Run Prediction
            </button>
          </div>
        </div>
  
        <!-- Right: result -->
        <div id="games-result-pane">
          <div class="card">
            <div class="state-empty">
              <span class="icon">🏀</span>
              Select a matchup and run a prediction to see results.
            </div>
          </div>
        </div>
  
      </div>
  
      <!-- Recent predictions log -->
      <div class="card" id="games-log-card">
        <div class="card-title">Recent Predictions</div>
        <div id="games-log-body">
          <div class="state-empty" style="padding:24px 0;">No predictions logged yet.</div>
        </div>
      </div>
    `;
  
    // ── Load upcoming games into select ──────────────────────────
    async function loadUpcomingGames() {
      const sel = document.getElementById('games-upcoming-select');
      try {
        const res  = await fetch(`${window.API}/games/upcoming`);
        const data = await res.json();
        if (!data.success || !data.games.length) {
          sel.innerHTML = '<option value="">No scheduled games found</option>';
          return;
        }
        sel.innerHTML = '<option value="">— pick a game —</option>' +
          data.games.map(g =>
            `<option value="${g.home_team}|${g.away_team}|${g.game_id}">
               ${g.home_team} vs ${g.away_team} · ${g.game_date}
             </option>`
          ).join('');
      } catch {
        sel.innerHTML = '<option value="">Could not load games (is Flask running?)</option>';
      }
    }
  
    // ── Populate manual fields when dropdown changes ──────────────
    document.getElementById('games-upcoming-select').addEventListener('change', function () {
      if (!this.value) return;
      const [home, away] = this.value.split('|');
      document.getElementById('games-home').value = home;
      document.getElementById('games-away').value = away;
    });
  
    // ── Run prediction ────────────────────────────────────────────
    document.getElementById('games-predict-btn').addEventListener('click', async () => {
      const home    = document.getElementById('games-home').value.trim().toUpperCase();
      const away    = document.getElementById('games-away').value.trim().toUpperCase();
      const selVal  = document.getElementById('games-upcoming-select').value;
      const gameId  = selVal ? selVal.split('|')[2] : null;
      const pane    = document.getElementById('games-result-pane');
  
      if (!home || !away) {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">⚠️</span>Enter both team abbreviations.</div>
        </div>`;
        return;
      }
  
      pane.innerHTML = `<div class="card"><div class="loading-bar"></div>
        <div style="color:var(--muted);font-size:13px;">Running model...</div>
      </div>`;
  
      try {
        const res  = await fetch(`${window.API}/games/predict`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ home_team: home, away_team: away, game_id: gameId }),
        });
        const data = await res.json();
  
        if (!data.success) {
          pane.innerHTML = `<div class="card">
            <div class="state-empty"><span class="icon">❌</span>${data.error}</div>
          </div>`;
          return;
        }
  
        renderPrediction(data.prediction, pane);
        appendToLog(data.prediction);
  
      } catch (err) {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">❌</span>Could not reach API.</div>
        </div>`;
      }
    });
  

    function renderPrediction(p, pane) {
      const homePct = (p.home_win_prob * 100).toFixed(1);
      const awayPct = (p.away_win_prob * 100).toFixed(1);
      const winner  = p.predicted_winner;
      const factors = p.key_factors || [];
  
      pane.innerHTML = `
        <div class="card">
          <div class="card-title">Win Probability</div>
  
          <div class="prob-bar-wrap">
            <div class="prob-teams">
              <div class="prob-team" style="${winner === p.home_team ? 'color:var(--orange)' : ''}">
                ${p.home_team} <span class="pct">${homePct}%</span>
              </div>
              <div class="prob-team" style="${winner === p.away_team ? 'color:var(--gold)' : ''}; text-align:right;">
                ${p.away_team} <span class="pct">${awayPct}%</span>
              </div>
            </div>
            <div class="prob-bar">
              <div class="home-fill" style="width:${homePct}%"></div>
              <div class="away-fill"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:8px;">
              <span class="badge badge-muted">Home</span>
              <span style="font-size:12px;color:var(--muted);">Predicted winner:
                <strong style="color:var(--text)">${winner}</strong>
              </span>
              <span class="badge badge-muted">Away</span>
            </div>
          </div>
  
          ${factors.length ? `
            <div class="card-title" style="margin-top:20px;">Key Factors</div>
            ${factors.map(f => `
              <div class="stat-row">
                <span class="stat-label">${f.factor}</span>
                <span class="badge badge-orange">${f.impact}</span>
              </div>
            `).join('')}
          ` : ''}
        </div>
      `;
    }
  
    const predictionLog = [];
  
    function appendToLog(p) {
      predictionLog.unshift(p);
      const body = document.getElementById('games-log-body');
      body.innerHTML = `
        <table class="data-table">
          <thead>
            <tr>
              <th>Home</th><th>Away</th>
              <th>Home Win %</th><th>Away Win %</th><th>Prediction</th>
            </tr>
          </thead>
          <tbody>
            ${predictionLog.slice(0, 10).map(p => `
              <tr>
                <td>${p.home_team}</td>
                <td>${p.away_team}</td>
                <td><span class="stat-value accent" style="font-size:16px">
                  ${(p.home_win_prob * 100).toFixed(1)}%
                </span></td>
                <td><span class="stat-value gold" style="font-size:16px">
                  ${(p.away_win_prob * 100).toFixed(1)}%
                </span></td>
                <td><span class="badge badge-orange">${p.predicted_winner}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }
  
    window.init_games = loadUpcomingGames;
  
  }());