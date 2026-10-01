import time
import pandas as pd
from nba_api.stats.endpoints import leaguegamelog, boxscoretraditionalv2

# nba.com blocks requests without a real browser User-Agent.
NBA_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Referer':              'https://www.nba.com/',
    'Accept':               'application/json, text/plain, */*',
    'Accept-Language':      'en-US,en;q=0.9',
    'Origin':               'https://www.nba.com',
    'x-nba-stats-origin':   'stats',
    'x-nba-stats-token':    'true',
}


def fetch_season_games(season_year):
    """
    Fetches all base team game logs for a given season (e.g., '2024-25').
    Cleans and pivots the data so each row represents one distinct matchup.
    """
    print(f"Fetching team game logs for season: {season_year}...")
    try:
        log = leaguegamelog.LeagueGameLog(
            season=season_year,
            league_id='00',
            headers=NBA_HEADERS,
            timeout=30,
        )
        df = log.get_data_frames()[0]

        if df.empty:
            print("  API returned empty DataFrame.")
            return pd.DataFrame()

        df.columns = [col.lower() for col in df.columns]

        # Split into home (vs.) and away (@) rows
        df_home = df[df['matchup'].str.contains('vs.')].copy()
        df_away = df[df['matchup'].str.contains('@')].copy()

        # Only bring the columns we need from each side.
        # NOTE: 'wl' only exists in df_home so after the merge it stays
        # as plain 'wl' — it does NOT become 'wl_home'.
        merged = pd.merge(
            df_home[['game_id', 'game_date', 'team_abbreviation', 'pts', 'wl']],
            df_away[['game_id', 'team_abbreviation', 'pts']],
            on='game_id',
            suffixes=('_home', '_away')
        )

        # Debug print — remove once seeding is confirmed working
        print(f"  Columns after merge: {merged.columns.tolist()}")

        # 'wl' is the correct name — rename it to 'wl_home' to match DB schema
        final_games = pd.DataFrame({
            'game_id':   merged['game_id'],
            'game_date': merged['game_date'],
            'home_team': merged['team_abbreviation_home'],
            'away_team': merged['team_abbreviation_away'],
            'home_pts':  merged['pts_home'],
            'away_pts':  merged['pts_away'],
            'wl_home':   merged['wl'],       # <-- 'wl' not 'wl_home'
            'season':    season_year,
            'status':    'FINAL',
        })

        print(f"  Built {len(final_games)} game rows.")
        return final_games

    except Exception as e:
        print(f"Error fetching games for season {season_year}: {e}")
        import traceback
        traceback.print_exc()          # full stack trace for easier debugging
        return pd.DataFrame()


def fetch_player_box_scores(game_id, game_date):
    """
    Fetches individual player box score metrics for a single specific game ID.
    Includes a built-in safety sleep delay to respect NBA API rate limits.
    """
    print(f"Fetching box score for game: {game_id}...")
    try:
        time.sleep(1.5)

        box = boxscoretraditionalv2.BoxScoreTraditionalV2(
            game_id=game_id,
            headers=NBA_HEADERS,
            timeout=30,
        )
        df_players = box.get_data_frames()[0]

        if df_players.empty:
            return pd.DataFrame()

        df_players.columns = [col.lower() for col in df_players.columns]

        # Filter out DNP players (no minutes logged)
        df_active = df_players[df_players['min'].notna()].copy()

        player_stats = pd.DataFrame({
            'game_id':           df_active['game_id'],
            'player_id':         df_active['player_id'],
            'player_name':       df_active['player_name'],
            'team_abbreviation': df_active['team_abbreviation'],
            'pts': df_active['pts'].fillna(0).astype(int),
            'reb': df_active['reb'].fillna(0).astype(int),
            'ast': df_active['ast'].fillna(0).astype(int),
            'stl': df_active['stl'].fillna(0).astype(int),
            'blk': df_active['blk'].fillna(0).astype(int),
            'min': df_active['min'],
            'game_date': game_date,
        })

        return player_stats

    except Exception as e:
        print(f"Error fetching box score for game {game_id}: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()