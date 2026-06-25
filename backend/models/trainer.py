import os
import joblib
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.calibration import CalibratedClassifierCV

from backend.data.features import generate_training_datasets
from backend.models.game_predictor import GAME_FEATURES
from backend.models.player_predictor import PLAYER_FEATURES, STAT_TARGETS

MODELS_DIR = os.path.join(os.path.dirname(__file__), 'saved')
os.makedirs(MODELS_DIR, exist_ok=True)

GAME_MODEL_PATH = os.path.join(MODELS_DIR, 'game_model.joblib')


def train_game_model(team_features_df: pd.DataFrame, save: bool = True) -> dict:
    """
    Trains an XGBoost classifier to predict home team win probability.
    Applies Platt scaling via CalibratedClassifierCV so probabilities are
    reliable (a 70% prediction should win ~70% of the time).

    Args:
        team_features_df: Engineered matchup DataFrame from features.py
        save: Whether to serialize the trained model to disk

    Returns:
        Dict with accuracy, sample_count, and feature_importances
    """
    df = team_features_df.dropna(subset=GAME_FEATURES + ['home_win_target'])

    if len(df) < 50:
        print("Not enough game data to train. Need at least 50 games.")
        return {}

    X = df[GAME_FEATURES]
    y = df['home_win_target']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Base gradient boosting classifier
    base_model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric='logloss',
        random_state=42,
        verbosity=0,
    )

    # Wrap with calibration so win probabilities are trustworthy
    model = CalibratedClassifierCV(base_model, cv=5, method='isotonic')
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = round(accuracy_score(y_test, y_pred), 4)

    # Extract feature importances from the underlying XGBoost estimator
    importances = {}
    try:
        raw_importances = model.calibrated_classifiers_[0].estimator.feature_importances_
        importances = dict(zip(GAME_FEATURES, [round(float(v), 4) for v in raw_importances]))
        importances = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))
    except Exception:
        pass

    if save:
        joblib.dump(model, GAME_MODEL_PATH)
        print(f"Game model saved → {GAME_MODEL_PATH}")

    print(f"Game model accuracy: {accuracy * 100:.1f}% on {len(X_test)} test games")
    return {
        'accuracy': accuracy,
        'sample_count': len(df),
        'feature_importances': importances,
    }


# ---------------------------------------------------------------------------
# Player performance models (one per stat)
# ---------------------------------------------------------------------------

def _build_player_training_data(player_features_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merges H2H context into the player feature set for training.
    For each row, the 'opponent' column is used to compute historical H2H averages
    within the training set itself (using only past games to avoid leakage).
    """
    df = player_features_df.copy()

    # Compute per-player per-opponent historical average BEFORE each game (shift to avoid leakage)
    for stat in ['pts', 'reb', 'ast']:
        h2h_col = f'h2h_avg_{stat}'
        df[h2h_col] = (
            df.groupby(['player_id', 'team_abbreviation'])[stat]
            .transform(lambda x: x.shift(1).expanding(min_periods=1).mean())
            .fillna(0)
        )

    df['h2h_game_count'] = (
        df.groupby(['player_id', 'team_abbreviation']).cumcount()
    )

    # is_home isn't in the raw player stats — we'll leave it as 0 during training
    # (it gets populated correctly at inference time)
    df['is_home'] = 0

    return df.dropna(subset=PLAYER_FEATURES)


def train_player_models(player_features_df: pd.DataFrame, save: bool = True) -> dict:
    """
    Trains one XGBRegressor per stat target (pts, reb, ast, stl, blk).
    Each model is saved independently so they can be loaded selectively.

    Args:
        player_features_df: Engineered player DataFrame from features.py
        save: Whether to serialize trained models to disk

    Returns:
        Dict of { stat: { mae, sample_count } } for each trained model
    """
    df = _build_player_training_data(player_features_df)

    if len(df) < 100:
        print("Not enough player data to train. Need at least 100 player-game rows.")
        return {}

    results = {}

    for stat in STAT_TARGETS:
        X = df[PLAYER_FEATURES]
        y = df[stat]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        model = XGBRegressor(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        mae = round(float(mean_absolute_error(y_test, y_pred)), 3)

        if save:
            path = os.path.join(MODELS_DIR, f'player_{stat}_model.joblib')
            joblib.dump(model, path)
            print(f"Player '{stat}' model saved → {path}  |  MAE: {mae}")

        results[stat] = {'mae': mae, 'sample_count': len(df)}

    return results


# ---------------------------------------------------------------------------
# Incremental retraining — the feedback loop
# ---------------------------------------------------------------------------

def retrain_all(verbose: bool = True) -> dict:
    """
    Full retraining pipeline. Called by scripts/retrain.py after new game
    results have been fetched and logged.

    Pulls all data from SQLite → rebuilds features → retrains both models.
    The expanded dataset (including recent game results) is what makes the
    feedback loop work — each retrain the model learns from newer games.

    Returns:
        Dict summary of game model accuracy and per-stat player MAE
    """
    if verbose:
        print("Starting full retrain pipeline...")

    team_features_df, player_features_df = generate_training_datasets()

    if verbose:
        print(f"Loaded {len(team_features_df)} matchups and {len(player_features_df)} player-game rows.")

    game_results = train_game_model(team_features_df, save=True)
    player_results = train_player_models(player_features_df, save=True)

    summary = {
        'game_model': game_results,
        'player_models': player_results,
    }

    if verbose:
        print("\n=== Retrain Summary ===")
        if game_results:
            print(f"  Game model accuracy : {game_results['accuracy'] * 100:.1f}%")
        for stat, res in player_results.items():
            print(f"  Player '{stat}' MAE  : {res['mae']}")

    return summary


if __name__ == '__main__':
    retrain_all()