// pages/accuracy.js
// Renders into #page-accuracy and calls /api/accuracy
// Uses Chart.js (loaded globally in index.html)

(function () {

    const container = document.getElementById('page-accuracy');
  
    container.innerHTML = `
      <div class="page-header">
        <h1>MODEL <span>ACCURACY</span></h1>
        <p>Track how well the prediction engine performs over time.</p>
      </div>
  
      <!-- Top stat strip -->
      <div id="accuracy-stats-strip" style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px;">
        ${['overall','correct','incorrect','pending'].map(k => `
          <div class="card" style="margin-bottom:0;text-align:center;padding:20px 16px;">
            <div class="card-title" style="margin-bottom:8px;" id="strip-label-${k}">—</div>
            <div class="stat-value accent" style="font-size:36px;" id="strip-val-${k}">—</div>
          </div>
        `).join('')}
      </div>
  
      <div class="grid-2">
  
        <!-- Rolling accuracy chart -->
        <div class="card">
          <div class="card-title">Rolling Accuracy (20-game window)</div>
          <canvas id="chart-rolling" height="220"></canvas>
        </div>
  
        <!-- Calibration chart -->
        <div class="card">
          <div class="card-title">Confidence Calibration</div>
          <canvas id="chart-calibration" height="220"></canvas>
          <div style="margin-top:12px;font-size:12px;color:var(--muted);">
            A well-calibrated model's bars track the diagonal — 70% predictions
            should win ~70% of the time.
          </div>
        </div>
  
      </div>
  
      <!-- Per-team accuracy table -->
      <div class="card" style="margin-top:4px;">
        <div class="card-title">Accuracy by Team</div>
        <div id="accuracy-by-team">
          <div class="state-empty" style="padding:24px 0;">Loading...</div>
        </div>
      </div>
  
      <!-- Retrain button -->
      <div style="margin-top:24px;display:flex;align-items:center;gap:16px;">
        <button class="btn btn-secondary" id="retrain-btn">
          ↺ Trigger Retrain
        </button>
        <span id="retrain-status" style="font-size:13px;color:var(--muted);"></span>
      </div>
    `;
  
    // ── Chart instances (kept for destroy/re-render) ──────────────
    let rollingChart     = null;
    let calibrationChart = null;
  
    // ── Chart.js global defaults ──────────────────────────────────
    Chart.defaults.color          = '#8A8F9E';
    Chart.defaults.borderColor    = '#2E3340';
    Chart.defaults.font.family    = "'Inter', sans-serif";
    Chart.defaults.font.size      = 12;
  
    // ── Load and render accuracy data ────────────────────────────
    async function loadAccuracy() {
      try {
        const res  = await fetch(`${window.API}/accuracy`);
        const data = await res.json();
  
        if (!data.success) {
          console.error('Accuracy API error:', data.error);
          return;
        }
  
        const m = data.metrics;
        renderStatsStrip(m.overall);
        renderRollingChart(m.rolling);
        renderCalibrationChart(m.calibration);
        renderTeamTable(m.by_team);
  
      } catch (err) {
        console.error('Could not load accuracy:', err);
      }
    }
  
    // ── Stats strip ───────────────────────────────────────────────
    function renderStatsStrip(overall) {
      const map = {
        overall:   { label: 'Overall Accuracy', val: overall.accuracy_pct != null ? `${overall.accuracy_pct}%` : '—' },
        correct:   { label: 'Correct',   val: overall.correct   ?? '—' },
        incorrect: { label: 'Incorrect', val: overall.incorrect ?? '—' },
        pending:   { label: 'Pending',   val: overall.pending   ?? '—' },
      };
  
      for (const [key, { label, val }] of Object.entries(map)) {
        document.getElementById(`strip-label-${key}`).textContent = label;
        const el = document.getElementById(`strip-val-${key}`);
        el.textContent = val;
        if (key === 'correct')   el.className = 'stat-value green';
        if (key === 'incorrect') el.className = 'stat-value red';
        if (key === 'pending')   el.className = 'stat-value';
      }
    }
  
    // ── Rolling accuracy line chart ───────────────────────────────
    function renderRollingChart(rolling) {
      if (!rolling || !rolling.length) return;
  
      const labels = rolling.map(r => r.game_date.slice(5));  // MM-DD
      const values = rolling.map(r => r.rolling_accuracy_pct);
  
      if (rollingChart) rollingChart.destroy();
  
      rollingChart = new Chart(document.getElementById('chart-rolling'), {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'Rolling accuracy %',
            data: values,
            borderColor: '#F7620A',
            backgroundColor: 'rgba(247,98,10,0.08)',
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            fill: true,
            tension: 0.4,
          }],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: ctx => ` ${ctx.parsed.y.toFixed(1)}%`,
              },
            },
          },
          scales: {
            x: {
              ticks: { maxTicksLimit: 8 },
              grid: { color: '#2E3340' },
            },
            y: {
              min: 0, max: 100,
              ticks: { callback: v => `${v}%` },
              grid: { color: '#2E3340' },
            },
          },
        },
      });
    }
  
    // ── Calibration bar chart ─────────────────────────────────────
    function renderCalibrationChart(calibration) {
      if (!calibration || !calibration.length) return;
  
      const labels      = calibration.map(c => c.bucket_label);
      const predicted   = calibration.map(c => c.predicted_prob);
      const actualRates = calibration.map(c => c.actual_win_rate);
  
      if (calibrationChart) calibrationChart.destroy();
  
      calibrationChart = new Chart(document.getElementById('chart-calibration'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: 'Actual win rate %',
              data: actualRates,
              backgroundColor: 'rgba(247,98,10,0.7)',
              borderColor: '#F7620A',
              borderWidth: 1,
              borderRadius: 4,
            },
            {
              label: 'Predicted prob %',
              data: predicted,
              backgroundColor: 'rgba(201,168,76,0.25)',
              borderColor: '#C9A84C',
              borderWidth: 1,
              borderRadius: 4,
              type: 'line',
              pointRadius: 3,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            legend: {
              labels: { boxWidth: 12 },
            },
            tooltip: {
              callbacks: {
                label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`,
              },
            },
          },
          scales: {
            x: { grid: { color: '#2E3340' } },
            y: {
              min: 0, max: 100,
              ticks: { callback: v => `${v}%` },
              grid: { color: '#2E3340' },
            },
          },
        },
      });
    }
  
    // ── Per-team accuracy table ───────────────────────────────────
    function renderTeamTable(byTeam) {
      const el = document.getElementById('accuracy-by-team');
  
      if (!byTeam || !byTeam.length) {
        el.innerHTML = `<div class="state-empty" style="padding:24px 0;">
          No resolved predictions yet.</div>`;
        return;
      }
  
      el.innerHTML = `
        <table class="data-table">
          <thead>
            <tr>
              <th>Team</th>
              <th>Predictions</th>
              <th>Correct</th>
              <th>Accuracy</th>
            </tr>
          </thead>
          <tbody>
            ${byTeam.map(row => {
              const pct = row.accuracy_pct;
              const cls = pct >= 65 ? 'green' : pct >= 55 ? 'accent' : 'red';
              return `
                <tr>
                  <td><span class="badge badge-muted">${row.team}</span></td>
                  <td style="color:var(--muted)">${row.predicted_count}</td>
                  <td style="color:var(--muted)">${row.correct}</td>
                  <td><span class="stat-value ${cls}" style="font-size:18px">${pct}%</span></td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `;
    }
  
    // ── Retrain trigger ───────────────────────────────────────────
    document.getElementById('retrain-btn').addEventListener('click', async () => {
      const btn    = document.getElementById('retrain-btn');
      const status = document.getElementById('retrain-status');
  
      btn.disabled     = true;
      btn.textContent  = 'Retraining...';
      status.textContent = '';
  
      try {
        const res  = await fetch(`${window.API}/admin/retrain`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Admin-Token': 'local-dev-only',
          },
        });
        const data = await res.json();
  
        if (data.success) {
          status.style.color = 'var(--green)';
          status.textContent = '✓ Retrain complete. Refreshing metrics...';
          setTimeout(() => loadAccuracy(), 800);
        } else {
          status.style.color = 'var(--red)';
          status.textContent = `✗ ${data.error}`;
        }
      } catch {
        status.style.color = 'var(--red)';
        status.textContent = '✗ Could not reach API.';
      } finally {
        btn.disabled    = false;
        btn.textContent = '↺ Trigger Retrain';
      }
    });
  
    // ── Init — called once when tab is first opened ───────────────
    window.init_accuracy = loadAccuracy;
  
  }());