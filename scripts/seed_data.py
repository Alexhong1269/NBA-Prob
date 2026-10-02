"""
seed_data.py — Hybrid seed strategy:

  Phase 1 (fast, offline): Load historical data from Kaggle CSVs
  Phase 2 (targeted, online): Top up with recent seasons via nba_api

Kaggle dataset: https://www.kaggle.com/datasets/nathanlauga/nba-games
Download and unzip into: data/kaggle/
Expected files:
  data/kaggle/games.csv
  data/kaggle/games_details.csv
  data/kaggle/players.csv
  data/kaggle/teams.csv

Usage:
    python scripts/seed_data.py                  # both phases
    python scripts/seed_data.py --kaggle-only    # skip nba_api top-up
    python scripts/seed_data.py --topup-only     # skip Kaggle, just top up
"""

import sys
import os
import time
import argparse
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from backend.data.cache import (
    init_db,
    save_games_to_db,
    save_player_stats_to_db,
    get_db_connection,
)

# ── Configuration ─────────────────────────────────────────────────────────────

KAGGLE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'kaggle')

# Seasons the Kaggle dataset already covers — we won't re-fetch these
KAGGLE_SEASONS = {
    '2003-04', '2004-05', '2005-06', '2006-07', '2007-08',
    '2008-09', '2009-10', '2010-11', '2011-12', '2012-13',
    '2013-14', '2014-15', '2015-16', '2016-17', '2017-18',
    '2018-19', '2019-20',
}

# Seasons to fetch from nba_api (everything Kaggle doesn't have)
TOPUP_SEASONS = [
    '2020-21', '2021-22', '2022-23', '2023-24', '2024-25',
]


# ── Phase 1: Kaggle CSV ingestion ─────────────────────────────────────────────

def load_kaggle_games() -> int:
    """
    Reads games.csv and teams.csv from the Kaggle dataset and
    writes them into the games table in SQLite.

    Kaggle games.csv columns we care about:
      GAME_ID, GAME_DATE_EST, HOME_TEAM_ID, VISITOR_TEAM_ID,
      PTS_home, PTS_away, HOME_TEAM_WINS, SEASON

    Returns the number of games inserted.
    """
    games_path = os.path.join(KAGGLE_DIR, 'games.csv')
    teams_path = os.path.join(KAGGLE_DIR, 'teams.csv')

    if not os.path.exists(games_path):
        print(f"  ✗ games.csv not found at {games_path}")
        print("    Download from: https://www.kaggle.com/datasets/nathanlauga/nba-games")
        return 0

    print("  Reading games.csv...")
    df_games = pd.read_csv(games_path)
    df_games.columns = [c.lower() for c in df_games.columns]

    # Build a team_id → abbreviation lookup from teams.csv
    team_abbrev = {}
    if os.path.exists(teams_path):
        df_teams = pd.read_csv(teams_path)
        df_teams.columns = [c.lower() for c in df_teams.columns]
        # Kaggle teams.csv has: TEAM_ID, ABBREVIATION, NICKNAME, CITY, ARENA, etc.
        abbrev_col = next(
            (c for c in df_teams.columns if 'abbrev' in c.lower()),
            None
        )
        id_col = next(
            (c for c in df_teams.columns if 'team_id' in c.lower() or c == 'id'),
            None
        )
        if abbrev_col and id_col:
            team_abbrev = dict(zip(df_teams[id_col], df_teams[abbrev_col]))
            print(f"  Loaded {len(team_abbrev)} team abbreviations.")
        else:
            print(f"  Warning: could not find id/abbrev columns in teams.csv. Cols: {df_teams.columns.tolist()}")
    else:
        print("  Warning: teams.csv not found — team names will use IDs.")

    # Identify the actual column names in games.csv (Kaggle uses mixed naming)
    col_map = {c.lower(): c for c in df_games.columns}
    print(f"  games.csv columns: {df_games.columns.tolist()[:12]}")

    # Normalise date column
    date_col     = next((c for c in df_games.columns if 'date' in c), None)
    home_id_col  = next((c for c in df_games.columns if 'home_team_id' in c), None)
    away_id_col  = next((c for c in df_games.columns if 'visitor' in c and 'id' in c), None)
    home_pts_col = next((c for c in df_games.columns if 'pts_home' in c), None)
    away_pts_col = next((c for c in df_games.columns if 'pts_away' in c or 'pts_visitor' in c.lower()), None)
    win_col      = next((c for c in df_games.columns if 'home_team_wins' in c), None)
    game_id_col  = next((c for c in df_games.columns if 'game_id' in c), None)
    season_col   = next((c for c in df_games.columns if 'season' in c), None)

    print(f"  Mapped columns — date:{date_col} home_id:{home_id_col} away_id:{away_id_col} "
          f"home_pts:{home_pts_col} away_pts:{away_pts_col} win:{win_col}")

    if not all([date_col, home_id_col, away_id_col, home_pts_col, away_pts_col, win_col, game_id_col]):
        print("  ✗ Could not map required columns. Check your games.csv file.")
        return 0

    # Resolve team IDs to abbreviations
    def resolve_team(tid):
        abbrev = team_abbrev.get(int(tid) if pd.notna(tid) else 0, str(int(tid)) if pd.notna(tid) else 'UNK')
        return abbrev

    # Convert season integer (e.g. 2019) → season string (e.g. '2019-20')
    def season_str(s):
        try:
            y = int(s)
            return f"{y}-{str(y+1)[-2:]}"
        except:
            return str(s)

    df_games = df_games.dropna(subset=[home_pts_col, away_pts_col])

    normalized = pd.DataFrame({
        'game_id':   df_games[game_id_col].astype(str),
        'game_date': pd.to_datetime(df_games[date_col]).dt.strftime('%Y-%m-%d'),
        'home_team': df_games[home_id_col].apply(resolve_team),
        'away_team': df_games[away_id_col].apply(resolve_team),
        'home_pts':  df_games[home_pts_col].fillna(0).astype(int),
        'away_pts':  df_games[away_pts_col].fillna(0).astype(int),
        'wl_home':   df_games[win_col].apply(lambda x: 'W' if x == 1 else 'L'),
        'season':    df_games[season_col].apply(season_str) if season_col else 'unknown',
        'status':    'FINAL',
    })

    save_games_to_db(normalized)
    print(f"  ✓ Inserted {len(normalized):,} games from Kaggle.")
    return len(normalized)


def load_kaggle_player_stats() -> int:
    """
    Reads games_details.csv from the Kaggle dataset and writes
    player box scores into the player_stats table.

    Kaggle games_details.csv columns:
      GAME_ID, TEAM_ID, TEAM_ABBREVIATION, PLAYER_ID, PLAYER_NAME,
      MIN, PTS, REB, AST, STL, BLK, ...

    Returns the number of player-game rows inserted.
    """
    details_path = os.path.join(KAGGLE_DIR, 'games_details.csv')

    if not os.path.exists(details_path):
        print(f"  ✗ games_details.csv not found at {details_path}")
        return 0

    print("  Reading games_details.csv (this may take a moment)...")
    df = pd.read_csv(details_path, low_memory=False)
    df.columns = [c.lower() for c in df.columns]

    print(f"  games_details.csv columns: {df.columns.tolist()[:14]}")

    # Filter out DNP rows (no minutes played)
    min_col = next((c for c in df.columns if c == 'min'), None)
    if min_col:
        df = df[df[min_col].notna() & (df[min_col] != '')].copy()

    # Identify columns
    game_id_col  = next((c for c in df.columns if c == 'game_id'), None)
    player_id    = next((c for c in df.columns if c == 'player_id'), None)
    player_name  = next((c for c in df.columns if c == 'player_name'), None)
    team_abbrev  = next((c for c in df.columns if 'team_abbreviation' in c), None)
    pts_col      = next((c for c in df.columns if c == 'pts'), None)
    reb_col      = next((c for c in df.columns if c == 'reb'), None)
    ast_col      = next((c for c in df.columns if c == 'ast'), None)
    stl_col      = next((c for c in df.columns if c == 'stl'), None)
    blk_col      = next((c for c in df.columns if c == 'blk'), None)

    if not all([game_id_col, player_id, player_name, pts_col]):
        print(f"  ✗ Could not map required player columns.")
        return 0

    # We need game_date — join from games table
    conn = get_db_connection()
    df_dates = pd.read_sql_query(
        "SELECT game_id, game_date FROM games", conn
    )
    conn.close()

    df['game_id_str'] = df[game_id_col].astype(str)
    df_dates['game_id'] = df_dates['game_id'].astype(str)
    df = df.merge(df_dates, left_on='game_id_str', right_on='game_id', how='left')

    normalized = pd.DataFrame({
        'game_id':           df['game_id_str'],
        'player_id':         df[player_id].fillna(0).astype(int),
        'player_name':       df[player_name].fillna('Unknown'),
        'team_abbreviation': df[team_abbrev].fillna('UNK') if team_abbrev else 'UNK',
        'pts':  df[pts_col].fillna(0).astype(int),
        'reb':  df[reb_col].fillna(0).astype(int) if reb_col else 0,
        'ast':  df[ast_col].fillna(0).astype(int) if ast_col else 0,
        'stl':  df[stl_col].fillna(0).astype(int) if stl_col else 0,
        'blk':  df[blk_col].fillna(0).astype(int) if blk_col else 0,
        'min':  df[min_col].astype(str) if min_col else '0',
        'game_date': df['game_date'].fillna(''),
    })

    # Drop rows with no valid player_id
    normalized = normalized[normalized['player_id'] > 0]

    # Insert in batches for speed
    batch_size = 5000
    total = len(normalized)
    for i in range(0, total, batch_size):
        batch = normalized.iloc[i:i + batch_size]
        save_player_stats_to_db(batch)
        if (i // batch_size + 1) % 10 == 0 or i + batch_size >= total:
            done = min(i + batch_size, total)
            print(f"  Player stats: {done:,}/{total:,} rows inserted")

    print(f"  ✓ Inserted {total:,} player-game rows from Kaggle.")
    return total


# ── Phase 2: nba_api top-up for recent seasons ────────────────────────────────

def get_seeded_seasons() -> set:
    """Returns the set of season strings already in the games table."""
    conn = get_db_connection()
    rows = conn.execute("SELECT DISTINCT season FROM games").fetchall()
    conn.close()
    return {row['season'] for row in rows}


def topup_recent_seasons(seasons: list) -> None:
    """
    Fetches game logs for seasons not already in the database.
    Only fetches the team game log (fast — one call per season).
    Player box scores for recent seasons are fetched lazily by
    update_results.py going forward.
    """
    already_seeded = get_seeded_seasons()
    to_fetch = [s for s in seasons if s not in already_seeded]

    if not to_fetch:
        print("  All recent seasons already in database — nothing to top up.")
        return

    print(f"  Seasons to fetch: {', '.join(to_fetch)}")

    # Import here so the script still works if nba_api has issues
    try:
        from backend.data.fetcher import fetch_season_games
    except ImportError as e:
        print(f"  ✗ Could not import fetcher: {e}")
        return

    for season in to_fetch:
        print(f"\n  Fetching {season} from nba_api...")
        df = fetch_season_games(season)

        if df.empty:
            print(f"  ✗ Could not fetch {season} — skipping.")
            print("    You can retry later with: python scripts/seed_data.py --topup-only")
            continue

        save_games_to_db(df)
        print(f"  ✓ {season}: {len(df):,} games saved.")

        # Polite pause between seasons
        time.sleep(3)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    conn = get_db_connection()
    game_count    = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    player_count  = conn.execute("SELECT COUNT(*) FROM player_stats").fetchone()[0]
    season_rows   = conn.execute(
        "SELECT season, COUNT(*) as cnt FROM games GROUP BY season ORDER BY season"
    ).fetchall()
    conn.close()

    print("\n" + "=" * 55)
    print("  Seed complete.")
    print(f"  Games in DB       : {game_count:,}")
    print(f"  Player rows in DB : {player_count:,}")
    print("\n  Games per season:")
    for row in season_rows:
        print(f"    {row['season']:<10} {row['cnt']:>5,} games")
    print("=" * 55)
    print("\nNext step: python scripts/retrain.py")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Seed the CourtIQ database.')
    parser.add_argument('--kaggle-only', action='store_true',
                        help='Only load Kaggle CSVs, skip nba_api top-up')
    parser.add_argument('--topup-only', action='store_true',
                        help='Skip Kaggle, only fetch recent seasons from nba_api')
    args = parser.parse_args()

    print("=" * 55)
    print("  CourtIQ — Database Seed Script")
    print("=" * 55)

    init_db()

    # Phase 1: Kaggle
    if not args.topup_only:
        print("\n── Phase 1: Kaggle historical data ─────────────────")
        games_loaded = load_kaggle_games()
        if games_loaded > 0:
            print("\n── Phase 1b: Kaggle player stats ───────────────────")
            load_kaggle_player_stats()
        else:
            print("\n  Skipping player stats — no games were loaded.")
            print("  Make sure your Kaggle CSVs are in data/kaggle/")
    else:
        print("\n── Phase 1: Skipped (--topup-only) ─────────────────")

    # Phase 2: nba_api top-up
    if not args.kaggle_only:
        print("\n── Phase 2: nba_api top-up (recent seasons) ────────")
        print("  Note: if nba_api times out, your Kaggle data is")
        print("  already saved. Re-run with --topup-only later.\n")
        topup_recent_seasons(TOPUP_SEASONS)
    else:
        print("\n── Phase 2: Skipped (--kaggle-only) ────────────────")

    print_summary()


if __name__ == '__main__':
    main()