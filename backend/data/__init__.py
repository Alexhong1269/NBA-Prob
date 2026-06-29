# backend/data/__init__.py
# Data layer — fetching, caching, and feature engineering.
# Exposes the three core functions app.py and scripts need directly.

from backend.data.cache import init_db, get_db_connection, save_games_to_db, save_player_stats_to_db
from backend.data.fetcher import fetch_season_games, fetch_player_box_scores
from backend.data.features import generate_training_datasets, build_player_features, build_team_features

__all__ = [
    'init_db',
    'get_db_connection',
    'save_games_to_db',
    'save_player_stats_to_db',
    'fetch_season_games',
    'fetch_player_box_scores',
    'generate_training_datasets',
    'build_player_features',
    'build_team_features',
]