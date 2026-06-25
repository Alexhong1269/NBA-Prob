import os
import joblib
import numpy as np
import pandas as pd

MODELS_DIR = os.path.join(os.path.dirname(__file__), 'saved')

# Stats we project — one XGBoost regressor is trained per stat
STAT_TARGETS = ['pts', 'reb', 'ast', 'stl', 'blk']

# Features fed into each player stat model
PLAYER_FEATURES = [
    'rolling_pts',
    'rolling_reb',
    'rolling_ast',
    'rolling_stl',
    'rolling_blk',
    'h2h_avg_pts',      # player's historical avg pts vs this specific opponent
    'h2h_avg_reb',
    'h2h_avg_ast',
    'h2h_game_count',   # how many times they've faced this opponent (confidence weight)
    'is_home',
]


def load_player_models() -> dict:
    """
    Loads all per-stat player models from disk.
    Returns a dict: { 'pts': model, 'reb': model, ... }
    Returns empty dict if models haven't been trained yet.
    """
    models = {}
    for stat in STAT_TARGETS:
        path = os.path.join(MODELS_DIR, f'player_{stat}_model.joblib')
        if os.path.exists(path):
            models[stat] = joblib.load(path)
        else:
            print(f"Player model for '{stat}' not found. Run trainer.py first.")
    return models


def build_h2h_player_features(player_id: int, opponent_team: str, df_players: pd.DataFrame) -> dict:
    """
    Computes a player's historical average stats against a specific opponent team.
    Called at prediction time to enrich the feature row.

    Args:
        player_id: NBA player ID
        opponent_team: Team abbreviation of the opponent (e.g. 'MIA')
        df_players: Full player stats DataFrame from the database

    Returns:
        Dict of H2H features for this player vs opponent
    """
    h2h = df_players[
        (df_players['player_id'] == player_id) &
        (df_players['team_abbreviation'] == opponent_team)
    ]

    if h2h.empty:
        # No prior matchup data — fall back to neutral values
        return {
            'h2h_avg_pts': 0.0,
            'h2h_avg_reb': 0.0,
            'h2h_avg_ast': 0.0,
            'h2h_game_count': 0,
        }

    return {
        'h2h_avg_pts': round(h2h['pts'].mean(), 2),
        'h2h_avg_reb': round(h2h['reb'].mean(), 2),
        'h2h_avg_ast': round(h2h['ast'].mean(), 2),
        'h2h_game_count': len(h2h),
    }


def predict_player_game(player_row: dict, opponent_team: str,
                         df_players: pd.DataFrame, is_home: int = 1) -> dict:
    """
    Projects a player's full stat line for an upcoming game.

    Args:
        player_row: Dict containing the player's rolling averages (from features.py)
        opponent_team: Abbreviation of the opposing team
        df_players: Raw player stats DataFrame (used to compute H2H)
        is_home: 1 if player's team is home, 0 if away

    Returns:
        Dict with projected stat line, season averages, and H2H averages
    """
    models = load_player_models()
    if not models:
        return {}

    player_id = player_row.get('player_id')
    h2h_features = build_h2h_player_features(player_id, opponent_team, df_players)

    feature_row = {
        'rolling_pts':  player_row.get('rolling_pts', 0),
        'rolling_reb':  player_row.get('rolling_reb', 0),
        'rolling_ast':  player_row.get('rolling_ast', 0),
        'rolling_stl':  player_row.get('rolling_stl', 0),
        'rolling_blk':  player_row.get('rolling_blk', 0),
        'is_home':      is_home,
        **h2h_features,
    }

    X = pd.DataFrame([feature_row])[PLAYER_FEATURES]

    projections = {}
    for stat, model in models.items():
        raw = float(model.predict(X)[0])
        projections[f'projected_{stat}'] = round(max(raw, 0), 1)  # floor at 0

    # Attach context so the frontend can show projected vs season avg vs H2H avg
    projections['player_id'] = player_id
    projections['player_name'] = player_row.get('player_name', '')
    projections['opponent'] = opponent_team
    projections['rolling_avg_pts'] = player_row.get('rolling_pts', 0)
    projections['h2h_avg_pts'] = h2h_features['h2h_avg_pts']
    projections['h2h_game_count'] = h2h_features['h2h_game_count']

    return projections


def predict_team_players(team_players: list[dict], opponent_team: str,
                          df_players: pd.DataFrame, is_home: int = 1) -> list[dict]:
    """
    Projects stat lines for all players on a team's expected roster.

    Args:
        team_players: List of player_row dicts (one per player on the team)
        opponent_team: Opposing team abbreviation
        df_players: Raw player stats DataFrame
        is_home: 1 if this team is home, 0 if away

    Returns:
        List of projection dicts, sorted by projected_pts descending
    """
    results = []
    for player_row in team_players:
        projection = predict_player_game(player_row, opponent_team, df_players, is_home)
        if projection:
            results.append(projection)

    return sorted(results, key=lambda x: x.get('projected_pts', 0), reverse=True)