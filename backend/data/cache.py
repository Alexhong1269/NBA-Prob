import sqlite3
import os
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'nba.db')

def get_db_connection():
    """Establishes a connection to the SQLite database with row factory enabled."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if the tables do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Games table to store historical results and upcoming schedules
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            game_date TEXT,
            home_team TEXT,
            away_team TEXT,
            home_pts INTEGER,
            away_pts INTEGER,
            wl_home TEXT,
            season TEXT,
            status TEXT DEFAULT 'FINAL' -- 'FINAL' or 'SCHEDULED'
        )
    ''')
    
    # 2. Player stats table for granular box-score details
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_stats (
            game_id TEXT,
            player_id INTEGER,
            player_name TEXT,
            team_abbreviation TEXT,
            pts INTEGER,
            reb INTEGER,
            ast INTEGER,
            stl INTEGER,
            blk INTEGER,
            min TEXT,
            game_date TEXT,
            PRIMARY KEY (game_id, player_id)
        )
    ''')
    
    # 3. Model predictions logging table to track performance/calibration over time
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prediction_logs (
            game_id TEXT PRIMARY KEY,
            game_date TEXT,
            home_team TEXT,
            away_team TEXT,
            predicted_home_win_prob REAL,
            actual_winner TEXT,
            is_correct INTEGER -- 1 for true, 0 for false, NULL for pending
        )
    ''')
    
    conn.commit()
    conn.close()
    print("SQLite database initialized successfully.")

def save_games_to_db(df_games):
    """Saves or updates a Pandas DataFrame of games into the SQLite database."""
    if df_games.empty:
        return
    conn = get_db_connection()
    # Using 'REPLACE' updates game scores/status if they change from SCHEDULED to FINAL
    df_games.to_sql('games', conn, if_exists='append', index=False, chunksize=500, method='multi')
    conn.close()

def save_player_stats_to_db(df_stats):
    """Saves a Pandas DataFrame of individual player box scores into the SQLite database."""
    if df_stats.empty:
        return
    conn = get_db_connection()
    
    # Execute an INSERT OR REPLACE manually to avoid pandas to_sql duplicate key crashes on PRIMARY KEY
    cursor = conn.cursor()
    for _, row in df_stats.iterrows():
        cursor.execute('''
            INSERT OR REPLACE INTO player_stats 
            (game_id, player_id, player_name, team_abbreviation, pts, reb, ast, stl, blk, min, game_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(row['game_id']), int(row['player_id']), row['player_name'], row['team_abbreviation'],
            int(row['pts']), int(row['reb']), int(row['ast']), int(row['stl']), int(row['blk']),
            str(row['min']), row['game_date']
        ))
    conn.commit()
    conn.close()

# Initialize database right away when this module is imported or run directly
if __name__ == '__main__':
    init_db()