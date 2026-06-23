import pandas as pd
import numpy as np
import sqlite3
from backend.data.cache import get_db_connection

def load_raw_data():
    """Loads raw games and player stats from the SQLite database."""
    conn = get_db_connection()
    df_games = pd.read_sql_query("SELECT * FROM games WHERE status = 'FINAL' ORDER BY game_date ASC", conn)
    df_players = pd.read_sql_query("SELECT * FROM player_stats ORDER BY game_date ASC", conn)
    conn.close()
    
    df_games['game_date'] = pd.to_datetime(df_games['game_date'])
    df_players['game_date'] = pd.to_datetime(df_players['game_date'])
    return df_games, df_players

def build_team_features(df_games):
    """
    Transforms raw game matchups into an engineered dataset.
    Includes short-term form (last 5), cumulative season performance, and historical H2H records.
    """
    if df_games.empty:
        return pd.DataFrame()

    # Step 1: Melt dataframe to get a chronological row per team performance
    home_df = df_games[['game_id', 'game_date', 'home_team', 'away_team', 'home_pts', 'away_pts', 'wl_home', 'season']].copy()
    home_df.columns = ['game_id', 'game_date', 'team', 'opponent', 'pts_scored', 'pts_allowed', 'wl', 'season']
    home_df['is_home'] = 1
    
    away_df = df_games[['game_id', 'game_date', 'away_team', 'home_team', 'away_pts', 'home_pts', 'wl_home', 'season']].copy()
    away_df.columns = ['game_id', 'game_date', 'team', 'opponent', 'pts_scored', 'pts_allowed', 'wl', 'season']
    away_df['wl'] = away_df['wl'].apply(lambda x: 'W' if x == 'L' else 'L' if x == 'W' else None)
    away_df['is_home'] = 0
    
    team_timeline = pd.concat([home_df, away_df]).sort_values(by=['team', 'game_date']).reset_index(drop=True)
    team_timeline['is_win'] = team_timeline['wl'].apply(lambda x: 1 if x == 'W' else 0)
    
    # Step 2: Compute Rolling Form (Last 5 Games)
    team_groups = team_timeline.groupby('team')
    team_timeline['rolling_ppg_scored'] = team_groups['pts_scored'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    team_timeline['rolling_ppg_allowed'] = team_groups['pts_allowed'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    team_timeline['rolling_win_pct'] = team_groups['is_win'].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    
    # Step 3: Compute Cumulative Season Win % (Your idea: expanding window per season)
    # This tracks how the team is doing across the entire season up to the day before this game
    season_team_groups = team_timeline.groupby(['season', 'team'])
    team_timeline['season_cumulative_win_pct'] = season_team_groups['is_win'].transform(lambda x: x.shift(1).expanding(min_periods=1).mean()).fillna(0.5)

    # Compute Days of Rest
    team_timeline['days_rest'] = team_groups['game_date'].diff().dt.days.shift(1).fillna(4).clip(0, 7)
    
    # Step 4: Reconstruct the matchup view
    home_features = team_timeline[team_timeline['is_home'] == 1].drop(columns=['is_home', 'wl'])
    away_features = team_timeline[team_timeline['is_home'] == 0].drop(columns=['is_home', 'wl', 'pts_scored', 'pts_allowed', 'is_win'])
    
    matchup_features = pd.merge(
        home_features, away_features, 
        on=['game_id', 'game_date', 'season'], 
        suffixes=('_home', '_away')
    )
    
    # Step 5: Compute Historical Head-to-Head (H2H) Win %
    # Sort matchups chronologically to calculate running historical dominance between the two teams
    matchup_features = matchup_features.sort_values(by='game_date').reset_index(drop=True)
    
    # Create a unique key for the specific matchup pair (un-ordered by home/away to find ALL previous games)
    matchup_features['matchup_key'] = matchup_features.apply(
        lambda r: f"{min(r['team_home'], r['team_away'])}vs{max(r['team_home'], r['team_away'])}", axis=1
    )
    
    # Track if the home team won this matchup
    matchup_features['home_win_target'] = matchup_features['wl_home'].apply(lambda x: 1 if x == 'W' else 0)
    
    # Calculate historical H2H win rates safely
    h2h_wins = []
    h2h_history = {} # Key: matchup_key, Value: [list of historical winners as home or away]
    
    for idx, row in matchup_features.iterrows():
        key = row['matchup_key']
        home_team = row['team_home']
        
        if key not in h2h_history:
            # No prior history in database yet: default to an even 50/50 split (0.5)
            h2h_wins.append(0.5)
            h2h_history[key] = []
        else:
            # Look back at past games for this pair and calculate how often the current HOME team won
            past_games = h2h_history[key]
            home_team_wins = sum(1 for past_winner in past_games if past_winner == home_team)
            h2h_win_pct = home_team_wins / len(past_games)
            h2h_wins.append(h2h_win_pct)
            
        # Append the actual winner of this game to our history tracker for subsequent matchups
        actual_winner = row['team_home'] if row['home_win_target'] == 1 else row['team_away']
        h2h_history[key].append(actual_winner)
        
    matchup_features['historical_h2h_home_win_pct'] = h2h_wins

    # Clean up column names to match model expectations
    matchup_features = matchup_features.rename(columns={
        'pts_scored_home': 'home_pts',
        'pts_allowed_home': 'away_pts',
    })
    
    return matchup_features.dropna()

def build_player_features(df_players):
    """Engineers rolling box score metrics for individual players (unchanged)."""
    if df_players.empty:
        return pd.DataFrame()
        
    df_players = df_players.sort_values(by=['player_id', 'game_date']).reset_index(drop=True)
    player_groups = df_players.groupby('player_id')
    
    stats_to_roll = ['pts', 'reb', 'ast', 'stl', 'blk']
    for stat in stats_to_roll:
        df_players[f'rolling_{stat}'] = player_groups[stat].transform(lambda x: x.shift(1).rolling(5, min_periods=1).mean())
    
    df_players[[f'rolling_{s}' for s in stats_to_roll]] = df_players[[f'rolling_{s}' for s in stats_to_roll]].fillna(0)
    return df_players

def generate_training_datasets():
    df_games, df_players = load_raw_data()
    team_features_df = build_team_features(df_games)
    player_features_df = build_player_features(df_players)
    return team_features_df, player_features_df