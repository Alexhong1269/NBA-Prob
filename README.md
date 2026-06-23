# 🏀 NBA Prediction App

A local machine learning application that predicts NBA game outcomes and player performance using Gradient Boosting with an incremental feedback loop — the model retrains on real results over time, getting smarter each week.

---

## 📌 Project Goals

- Predict which NBA team will win a given matchup (with win probability %)
- Project individual player stat lines (pts, reb, ast, stl, blk) for a given game
- Display model accuracy over time and per team
- Run entirely on localhost — free, no API keys, no cloud

---

## 🧠 ML Approach

### Primary Model: Gradient Boosting
- Uses **XGBoost** for both game outcome and player performance prediction
- Trained on historical NBA data pulled from `nba_api`
- Features include rolling averages, rest days, home/away splits, and H2H records

### Feedback Loop (Incremental Learning)
Inspired by RL's core idea of learning from outcomes over time:
1. Before a game → model makes a prediction and logs it
2. After the game → real result is fetched and compared
3. New labeled data is appended to the training set
4. Model retrains on the expanded dataset (triggered weekly or manually)
5. Accuracy metrics update on the dashboard

This creates a self-improving loop: the more games played, the better the predictions.

---

## 🗂️ Project Structure

```
nba-prediction-app/
│
├── backend/
│   ├── app.py                  # Flask API entry point
│   ├── data/
│   │   ├── fetcher.py          # nba_api data fetching
│   │   ├── cache.py            # SQLite read/write helpers
│   │   └── features.py         # Feature engineering (rolling avgs, H2H, etc.)
│   ├── models/
│   │   ├── game_predictor.py   # XGBoost game outcome model
│   │   ├── player_predictor.py # XGBoost player stat projection model
│   │   ├── trainer.py          # Training + retraining pipeline
│   │   └── accuracy.py         # Prediction logging + accuracy tracking
│   └── database/
│       └── nba.db              # SQLite database (auto-created on first run)
│
├── frontend/
│   ├── index.html              # Main app shell
│   ├── pages/
│   │   ├── games.html          # Game predictions view
│   │   ├── players.html        # Player performance view
│   │   ├── h2h.html            # Head-to-head history view
│   │   └── accuracy.html       # Accuracy dashboard
│   ├── static/
│   │   ├── css/
│   │   │   └── styles.css
│   │   └── js/
│   │       ├── games.js
│   │       ├── players.js
│   │       └── charts.js       # Chart.js visualizations
│   └── components/             # Reusable UI pieces (nav, cards, etc.)
│
├── scripts/
│   ├── seed_data.py            # One-time historical data pull (2-3 seasons)
│   ├── retrain.py              # Manual retrain trigger
│   └── update_results.py       # Fetch last week's results + log accuracy
│
├── requirements.txt
└── README.md
```

---

## ⚙️ Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Data source | `nba_api` | Free, no key, official NBA stats |
| Local database | SQLite | Zero setup, stores cache + predictions |
| ML models | XGBoost + scikit-learn | Best for tabular sports data |
| Backend API | Flask | Lightweight, easy local server |
| Frontend | HTML + JS + Chart.js | Simple, no build tools needed |
| Model storage | `joblib` | Serialize trained models to disk |

---

## 🔧 Features

### Game Predictions
- Select any upcoming matchup
- See win probability % for each team
- View key contributing features (e.g. rest advantage, recent form)

### Player Performance Projections
- Select a player + opponent
- Get projected stat line vs their season average vs their H2H average against that team
- Highlights when a player historically over/underperforms a specific opponent

### Head-to-Head View
- Historical record between two teams
- Rolling stat comparisons across recent matchups

### Accuracy Dashboard
- Overall prediction accuracy %
- Rolling accuracy chart over time (Chart.js)
- Per-team accuracy breakdown
- Confidence calibration (are 70% predictions winning ~70% of the time?)

---

## 🚀 Getting Started

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Seed historical data (run once)
```bash
python scripts/seed_data.py
```
This pulls 2–3 seasons of game logs and player stats from `nba_api` into SQLite. Takes a few minutes due to rate limiting.

### 3. Train the initial models
```bash
python scripts/retrain.py
```

### 4. Start the Flask server
```bash
python backend/app.py
```

### 5. Open the app
Navigate to `http://localhost:5000` in your browser.

---

## 🔁 Feedback Loop — Weekly Workflow

```
Every week (or after a set of games):
  1. python scripts/update_results.py   # fetch real results, log accuracy
  2. python scripts/retrain.py          # retrain models on new data
```

Over time this gives you a clear accuracy trend and a model that adapts to the current season.

---

## 📦 Requirements

```
nba_api
xgboost
scikit-learn
pandas
numpy
flask
flask-cors
joblib
```

---

## 📋 Development Phases

- [ ] **Phase 1** — Data pipeline: fetcher, SQLite cache, feature engineering
- [ ] **Phase 2** — Game outcome model: train, serialize, expose via Flask
- [ ] **Phase 3** — Player performance model: train, expose via Flask
- [ ] **Phase 4** — Frontend: game predictions page + player stats page
- [ ] **Phase 5** — Feedback loop: result logging, retraining pipeline
- [ ] **Phase 6** — Accuracy dashboard: charts, per-team breakdown, calibration

---

## 📝 Notes

- `nba_api` has rate limits — the seed script includes sleep delays to avoid getting blocked
- Models are saved to disk with `joblib` so Flask loads them at startup without retraining
- SQLite database is auto-created on first run — no setup needed
- All data stays local; nothing is sent to any external service after the initial `nba_api` fetch
