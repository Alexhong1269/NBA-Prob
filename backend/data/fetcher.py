import time
import pandas as pd
from nba_api.stats.endpoints import leaguegamelog, boxscoretraditionalv2

def fetch_season_games(season_year):
    """
    Fetches all base team game logs for a given season (e.g., '2024-25').
    Cleans and pivots the data so each row represents one distinct matchup.
    """
    print(f"Fetching team game logs for season: {season_year}...")
    try:
        # Pull logs from the NBA api
        log = leaguegamelog.LeagueGameLog(season=season_year, league_id_nullable='00')
        df = log.get_data_frames()[0]
        
        if df.empty:
            return pd.DataFrame()
            
        # Clean columns to lowercase for consistency
        df.columns = [col.lower() for col in df.columns]
        
        # Filter down to regular season games to keep model data clean
        # nba_api includes 'vs.' for home matchups and '@' for away matchups
        df_home = df[df['matchup'].str.contains('vs.')].copy()
        df_away = df[df['matchup'].str.contains('@')].copy()
        
        # Merge home and away rows on game_id to create a single row per game
        merged = pd.merge(
            df_home[['game_id', 'game_date', 'team_abbreviation', 'pts', 'wl']],
            df_away[['game_id', 'team_abbreviation', 'pts']],
            on='game_id',
            suffixes=('_home', '_away')
        )
        
        # Format explicitly to match our database schema
        final_games = pd.DataFrame({
            'game_id': merged['game_id'],
            'game_date': merged['game_date'],
            'home_team': merged['team_abbreviation_home'],
            'away_team': merged['team_abbreviation_away'],
            'home_pts': merged['pts_home'],
            'away_pts': merged['pts_away'],
            'wl_home': merged['wl_home'],
            'season': season_year,
            'status': 'FINAL'
        })
        
        return final_games
        
    except Exception as e:
        print(f"Error fetching games for season {season_year}: {e}")
        return pd.DataFrame()

def fetch_player_box_scores(game_id, game_date):
    """
    Fetches individual player box score metrics for a single specific game ID.
    Includes a built-in safety sleep delay to respect NBA API rate limits.
    """
    print(f"Fetching box score for game: {game_id}...")
    try:
        # Enforce rate limit padding
        time.sleep(1.5)
        
        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        df_players = box.get_data_frames()[0]
        
        if df_players.empty:
            return pd.DataFrame()
            
        df_players.columns = [col.lower() for col in df_players.columns]
        
        # Filter out players who did not step onto the court (DNP)
        df_active = df_players[df_players['min'].notna()].copy()
        
        # Construct the DataFrame mapped directly to our cache schema
        player_stats = pd.DataFrame({
            'game_id': df_active['game_id'],
            'player_id': df_active['player_id'],
            'player_name': df_active['player_name'],
            'team_abbreviation': df_active['team_abbreviation'],
            'pts': df_active['pts'].fillna(0).astype(int),
            'reb': df_active['reb'].fillna(0).astype(int),
            'ast': df_active['ast'].fillna(0).astype(int),
            'stl': df_active['stl'].fillna(0).astype(int),
            'blk': df_active['blk'].fillna(0).astype(int),
            'min': df_active['min'],
            'game_date': game_date
        })
        
        return player_stats
        
    except Exception as e:
        print(f"Error fetching box score for game {game_id}: {e}")
        return pd.DataFrame()