import os
import joblib
import numpy as np
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'saved', 'game_model.joblib')

# These are the exact columns the model was trained on — order matters for prediction
GAME_FEATURES = [
    'rolling_ppg_scored_home',
    'rolling_ppg_allowed_home',
    'rolling_win_pct_home',
    'season_cumulative_win_pct_home',
    'days_rest_home',
    'rolling_ppg_scored_away',
    'rolling_ppg_allowed_away',
    'rolling_win_pct_away',
    'season_cumulative_win_pct_away',
    'days_rest_away',
    'historical_h2h_home_win_pct',
]


def load_model():
    """Loads the serialized game model from disk. Returns None if not yet trained."""
    if not os.path.exists(MODEL_PATH):
        print("Game model not found. Run trainer.py first.")
        return None
    return joblib.load(MODEL_PATH)


def predict_game(home_team: str, away_team: str, feature_row: dict) -> dict:
    """
    Predicts the win probability for a single upcoming matchup.

    Args:
        home_team: Team abbreviation for the home team (e.g. 'BOS')
        away_team: Team abbreviation for the away team (e.g. 'LAL')
        feature_row: Dict of engineered features for this matchup (keys match GAME_FEATURES)

    Returns:
        Dict with home_win_prob, away_win_prob, and predicted_winner
    """
    model = load_model()
    if model is None:
        return {}

    # Build input vector in the correct feature order
    X = pd.DataFrame([feature_row])[GAME_FEATURES]

    home_win_prob = float(model.predict_proba(X)[0][1])
    away_win_prob = round(1 - home_win_prob, 4)
    home_win_prob = round(home_win_prob, 4)

    predicted_winner = home_team if home_win_prob >= 0.5 else away_team

    return {
        'home_team': home_team,
        'away_team': away_team,
        'home_win_prob': home_win_prob,
        'away_win_prob': away_win_prob,
        'predicted_winner': predicted_winner,
    }


def predict_batch(matchups_df: pd.DataFrame) -> pd.DataFrame:
    """
    Runs predictions for a batch of upcoming matchups at once.
    Useful for seeding the prediction_logs table before a game day.

    Args:
        matchups_df: DataFrame with at minimum GAME_FEATURES columns
                     plus 'home_team', 'away_team', and 'game_id'

    Returns:
        Original DataFrame with appended prediction columns
    """
    model = load_model()
    if model is None:
        return matchups_df

    X = matchups_df[GAME_FEATURES]
    probs = model.predict_proba(X)

    matchups_df = matchups_df.copy()
    matchups_df['home_win_prob'] = np.round(probs[:, 1], 4)
    matchups_df['away_win_prob'] = np.round(probs[:, 0], 4)
    matchups_df['predicted_winner'] = matchups_df.apply(
        lambda r: r['home_team'] if r['home_win_prob'] >= 0.5 else r['away_team'], axis=1
    )

    return matchups_df