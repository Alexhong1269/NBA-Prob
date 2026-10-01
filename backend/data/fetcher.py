import time
import random
import pandas as pd
from nba_api.stats.endpoints import leaguegamelog, boxscoretraditionalv2

NBA_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Referer':             'https://www.nba.com/',
    'Accept':              'application/json, text/plain, */*',
    'Accept-Language':     'en-US,en;q=0.9',
    'Origin':              'https://www.nba.com',
    'x-nba-stats-origin':  'stats',
    'x-nba-stats-token':   'true',
    'Connection':          'keep-alive',
}

# How many times to retry a timed-out request before giving up
MAX_RETRIES = 4


def _sleep_with_jitter(base_seconds: float):
    """Sleeps for base_seconds plus a small random jitter to avoid patterns."""
    jitter = random.uniform(0.5, 2.0)
    total  = base_seconds + jitter
    print(f"  Waiting {total:.1f}s before retry...")
    time.sleep(total)


def fetch_season_games(season_year: str) -> pd.DataFrame:
    """
    Fetches all team game logs for a given season (e.g. '2024-25').
    Retries up to MAX_RETRIES times with exponential backoff on timeout.
    """
    print(f"Fetching team game logs for season: {season_year}...")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if attempt > 1:
                print(f"  Attempt {attempt}/{MAX_RETRIES}...")

            log = leaguegamelog.LeagueGameLog(
                season=season_year,
                league_id='00',
                headers=NBA_HEADERS,
                timeout=60,           # raised from 30 — nba.com is slow
            )
            df = log.get_data_frames()[0]

            if df.empty:
                print("  API returned empty DataFrame.")
                return pd.DataFrame()

            df.columns = [col.lower() for col in df.columns]

            df_home = df[df['matchup'].str.contains('vs.')].copy()
            df_away = df[df['matchup'].str.contains('@')].copy()

            merged = pd.merge(
                df_home[['game_id', 'game_date', 'team_abbreviation', 'pts', 'wl']],
                df_away[['game_id', 'team_abbreviation', 'pts']],
                on='game_id',
                suffixes=('_home', '_away')
            )

            # 'wl' stays as 'wl' after merge (not 'wl_home') — rename here
            final_games = pd.DataFrame({
                'game_id':   merged['game_id'],
                'game_date': merged['game_date'],
                'home_team': merged['team_abbreviation_home'],
                'away_team': merged['team_abbreviation_away'],
                'home_pts':  merged['pts_home'],
                'away_pts':  merged['pts_away'],
                'wl_home':   merged['wl'],
                'season':    season_year,
                'status':    'FINAL',
            })

            print(f"  Got {len(final_games)} games for {season_year}.")
            return final_games

        except Exception as e:
            err = str(e)
            if 'timeout' in err.lower() or 'timed out' in err.lower():
                if attempt < MAX_RETRIES:
                    # Exponential backoff: 5s, 10s, 20s between retries
                    _sleep_with_jitter(5 * (2 ** (attempt - 1)))
                    continue
                else:
                    print(f"  Gave up after {MAX_RETRIES} attempts — stats.nba.com kept timing out.")
                    print("  Try running seed_data.py again in a few minutes.")
            else:
                print(f"  Non-timeout error: {e}")
                import traceback; traceback.print_exc()

            return pd.DataFrame()

    return pd.DataFrame()


def fetch_player_box_scores(game_id: str, game_date: str) -> pd.DataFrame:
    """
    Fetches player box scores for a single game with retry on timeout.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Always sleep between box score calls — one per game, very rate-limited
            time.sleep(1.5)

            box = boxscoretraditionalv2.BoxScoreTraditionalV2(
                game_id=game_id,
                headers=NBA_HEADERS,
                timeout=60,
            )
            df_players = box.get_data_frames()[0]

            if df_players.empty:
                return pd.DataFrame()

            df_players.columns = [col.lower() for col in df_players.columns]
            df_active = df_players[df_players['min'].notna()].copy()

            return pd.DataFrame({
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

        except Exception as e:
            err = str(e)
            if 'timeout' in err.lower() or 'timed out' in err.lower():
                if attempt < MAX_RETRIES:
                    _sleep_with_jitter(3 * (2 ** (attempt - 1)))
                    continue
                else:
                    print(f"  Box score for {game_id} timed out after {MAX_RETRIES} attempts, skipping.")
            else:
                print(f"  Error fetching box score {game_id}: {e}")

            return pd.DataFrame()

    return pd.DataFrame()