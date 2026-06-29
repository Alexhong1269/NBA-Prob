# backend/models/__init__.py
# Model layer — prediction, training, and accuracy tracking.
# Exposes the functions app.py routes call directly.

from backend.models.game_predictor import predict_game, predict_batch
from backend.models.player_predictor import predict_player_game, predict_team_players
from backend.models.trainer import retrain_all
from backend.models.accuracy import (
    log_prediction,
    log_predictions_batch,
    resolve_game_results,
    get_full_accuracy_summary,
    get_overall_accuracy,
    get_pending_predictions,
)

__all__ = [
    'predict_game',
    'predict_batch',
    'predict_player_game',
    'predict_team_players',
    'retrain_all',
    'log_prediction',
    'log_predictions_batch',
    'resolve_game_results',
    'get_full_accuracy_summary',
    'get_overall_accuracy',
    'get_pending_predictions',
]