// pages/h2h.js
// Renders into #page-h2h and calls /api/h2h

(function () {

    const container = document.getElementById('page-h2h');
  
    container.innerHTML = `
      <div class="page-header">
        <h1>HEAD-TO-<span>HEAD</span></h1>
        <p>Historical matchup record and recent game results between any two teams.</p>
      </div>
  
      <div class="grid-2">
  
        <!-- Left: team selector -->
        <div>
          <div class="card">
            <div class="card-title">Select Teams</div>
  
            <div class="form-group">
              <label class="form-label">Team 1</label>
              <input class="form-input" id="h2h-team1" type="text"
                     placeholder="e.g. BOS" maxlength="3"
                     style="text-transform:uppercase;" />
            </div>
  
            <div class="form-group">
              <label class="form-label">Team 2</label>
              <input class="form-input" id="h2h-team2" type="text"
                     placeholder="e.g. MIA" maxlength="3"
                     style="text-transform:uppercase;" />
            </div>
  
            <button class="btn btn-primary" id="h2h-fetch-btn" style="width:100%;margin-top:4px;">
              Load History
            </button>
          </div>
  
          <!-- Win summary card (populated on load) -->
          <div id="h2h-summary-card" style="display:none;">
            <div class="card">
              <div class="card-title">All-Time Record (Last 20)</div>
              <div id="h2h-summary-body"></div>
            </div>
          </div>
        </div>
  
        <!-- Right: game log -->
        <div id="h2h-games-pane">
          <div class="card">
            <div class="state-empty">
              <span class="icon">🏟️</span>
              Enter two team abbreviations to see their matchup history.
            </div>
          </div>
        </div>
  
      </div>
    `;
  
    // ── Fetch H2H data ────────────────────────────────────────────
    document.getElementById('h2h-fetch-btn').addEventListener('click', async () => {
      const team1 = document.getElementById('h2h-team1').value.trim().toUpperCase();
      const team2 = document.getElementById('h2h-team2').value.trim().toUpperCase();
      const pane  = document.getElementById('h2h-games-pane');
  
      if (!team1 || !team2) {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">⚠️</span>Enter both team abbreviations.</div>
        </div>`;
        return;
      }
  
      pane.innerHTML = `<div class="card"><div class="loading-bar"></div>
        <div style="color:var(--muted);font-size:13px;">Loading matchup history...</div>
      </div>`;
  
      try {
        const res  = await fetch(`${window.API}/h2h?team1=${team1}&team2=${team2}`);
        const data = await res.json();
  
        if (!data.success) {
          pane.innerHTML = `<div class="card">
            <div class="state-empty"><span class="icon">❌</span>${data.error}</div>
          </div>`;
          return;
        }
  
        renderH2H(data.h2h, team1, team2, pane);
  
      } catch {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">❌</span>Could not reach API.</div>
        </div>`;
      }
    });
  
    // ── Render H2H results ────────────────────────────────────────
    function renderH2H(h2h, team1, team2, pane) {
      const summary  = h2h.summary;
      const games    = h2h.games || [];
      const t1Wins   = summary[team1] || 0;
      const t2Wins   = summary[team2] || 0;
      const total    = t1Wins + t2Wins;
      const t1Pct    = total ? ((t1Wins / total) * 100).toFixed(0) : 50;
      const t2Pct    = total ? ((t2Wins / total) * 100).toFixed(0) : 50;
  
      // Summary card
      const summaryCard = document.getElementById('h2h-summary-card');
      const summaryBody = document.getElementById('h2h-summary-body');
      summaryCard.style.display = 'block';
  
      summaryBody.innerHTML = `
        <div class="prob-bar-wrap" style="margin:0;">
          <div class="prob-teams">
            <div class="prob-team" style="color:var(--orange);">
              ${team1} <span class="pct">${t1Wins}W</span>
            </div>
            <div class="prob-team" style="color:var(--gold);text-align:right;">
              ${team2} <span class="pct">${t2Wins}W</span>
            </div>
          </div>
          <div class="prob-bar">
            <div class="home-fill" style="width:${t1Pct}%"></div>
            <div class="away-fill"></div>
          </div>
          <div style="display:flex;justify-content:space-between;margin-top:8px;
                      font-size:12px;color:var(--muted);">
            <span>${t1Pct}% win rate</span>
            <span>${total} games played</span>
            <span>${t2Pct}% win rate</span>
          </div>
        </div>
      `;
  
      // Games table
      if (!games.length) {
        pane.innerHTML = `<div class="card">
          <div class="state-empty"><span class="icon">📭</span>
            No game history found for ${team1} vs ${team2}.
          </div>
        </div>`;
        return;
      }
  
      pane.innerHTML = `
        <div class="card">
          <div class="card-title">Recent Games — ${team1} vs ${team2}</div>
          <table class="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Matchup</th>
                <th>Score</th>
                <th>Winner</th>
              </tr>
            </thead>
            <tbody>
              ${games.map(g => {
                const homeWon = g.wl_home === 'W';
                const winner  = homeWon ? g.home_team : g.away_team;
                const isT1Win = winner === team1;
  
                return `
                  <tr>
                    <td style="color:var(--muted)">${g.game_date}</td>
                    <td>${g.home_team} vs ${g.away_team}</td>
                    <td style="font-family:var(--font-display);letter-spacing:.04em;">
                      ${g.home_pts ?? '—'} – ${g.away_pts ?? '—'}
                    </td>
                    <td>
                      <span class="badge ${isT1Win ? 'badge-orange' : 'badge-gold'}">
                        ${winner}
                      </span>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    }
  
    // ── Init ──────────────────────────────────────────────────────
    window.init_h2h = function () {};
  
  }());