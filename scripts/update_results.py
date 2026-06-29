"""
update_results.py — Weekly maintenance script for the feedback loop.

Does three things in order:
  1. Fetches the most recent completed games from nba_api and updates SQLite
  2. Resolves any pending predictions against the real results
  3. Prints an accuracy summary so you can see how the model is doing

Run this after each game week, then follow with retrain.py to improve the model.

Usage:
    python scripts/update_results.py [--season 2024-25]
"""

import sys
import os
import argparse
import time
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from backend.data.fetcher import fetch_season_games, fetch_player_box_scores
from backend.data.cache import (
    init_db,
    save_games_to_db,
    save_player_stats_to_db,
    get_db_connection,
)
from backend.models.accuracy import (
    resolve_game_results,
    get_pending_predictions,
    get_overall_accuracy,
    get_accuracy_by_team,
)


def get_current_season() -> str:
    """
    Infers the current NBA season string based on today's date.
    NBA seasons start in October, so Oct–Dec belong to the new season year.
    """
    today = datetime.today()
    year  = today.year
    if today.month >= 10:
        return f"{year}-{str(year + 1)[-2:]}"
    else:
        return f"{year - 1}-{str(year)[-2:]}"


def fetch_recent_games(season: str, days_back: int = 10) -> list[str]:
    """
    Fetches all FINAL games for the current season from nba_api, filters
    to those played within the last `days_back` days, and upserts them into SQLite.

    Returns a list of newly inserted or updated game_ids.
    """
    print(f"Fetching recent games for season {season}...")
    df = fetch_season_games(season)

    if df.empty:
        print("No games returned from nba_api.")
        return []

    # Filter to recent games only
    cutoff = datetime.today() - timedelta(days=days_back)
    df['game_date'] = df['game_date'].astype(str)
    recent = df[df['game_date'] >= cutoff.strftime('%Y-%m-%d')]

    if recent.empty:
        print(f"No games found in the last {days_back} days.")
        return []

    print(f"Found {len(recent)} recent games — updating database...")
    save_games_to_db(recent)

    return recent['game_id'].astype(str).tolist()


def update_player_box_scores(game_ids: list[str]) -> None:
    """
    Fetches and saves player box scores for the provided game IDs.
    Skips any games already present in player_stats.
    """
    if not game_ids:
        return

    # Find which ones we don't have yet
    conn    = get_db_connection()
    existing = {
        row['game_id']
        for row in conn.execute('SELECT DISTINCT game_id FROM player_stats').fetchall()
    }
    conn.close()

    to_fetch = [gid for gid in game_ids if gid not in existing]

    if not to_fetch:
        print("Player box scores already up to date.")
        return

    print(f"Fetching player box scores for {len(to_fetch)} new games...")

    # We need game_date for each game_id — pull from games table
    conn = get_db_connection()
    rows = conn.execute(
        f"SELECT game_id, game_date FROM games WHERE game_id IN ({','.join('?' * len(to_fetch))})",
        to_fetch
    ).fetchall()
    conn.close()

    date_map = {str(row['game_id']): row['game_date'] for row in rows}

    for i, game_id in enumerate(to_fetch, start=1):
        game_date  = date_map.get(game_id, '')
        df_players = fetch_player_box_scores(game_id, game_date)

        if not df_players.empty:
            save_player_stats_to_db(df_players)

        if i % 10 == 0 or i == len(to_fetch):
            print(f"  [{i}/{len(to_fetch)}] box scores fetched")


def resolve_pending(recent_game_ids: list[str]) -> dict:
    """
    Matches pending predictions against real results and marks them correct/incorrect.
    Only attempts resolution for games we've just fetched results for.
    """
    pending = get_pending_predictions()

    if not pending:
        print("No pending predictions to resolve.")
        return {}

    # Cross-reference pending predictions with games we have results for
    resolvable_ids = set(recent_game_ids)
    to_resolve     = [p for p in pending if p['game_id'] in resolvable_ids]

    if not to_resolve:
        print(f"{len(pending)} pending prediction(s) found, but none match recently fetched games.")
        print("Tip: try increasing --days-back if predictions are older than 10 days.")
        return {}

    print(f"Resolving {len(to_resolve)} pending prediction(s)...")

    # Build a results DataFrame from the games table for these IDs
    import pandas as pd
    conn = get_db_connection()
    ids_placeholder = ','.join('?' * len(to_resolve))
    resolve_ids     = [p['game_id'] for p in to_resolve]

    df_results = pd.read_sql_query(
        f"""SELECT game_id, home_team, away_team, home_pts, away_pts, wl_home
            FROM games
            WHERE game_id IN ({ids_placeholder}) AND status = 'FINAL'""",
        conn,
        params=resolve_ids
    )
    conn.close()

    if df_results.empty:
        print("No FINAL results found for pending predictions.")
        return {}

    counts = resolve_game_results(df_results)
    return counts


def print_accuracy_summary() -> None:
    """Prints a formatted accuracy summary to the terminal."""
    overall = get_overall_accuracy()
    by_team = get_accuracy_by_team()

    print("\n" + "=" * 55)
    print("  Model Accuracy Summary")
    print("=" * 55)

    if overall['resolved'] == 0:
        print("  No resolved predictions yet.")
    else:
        print(f"  Overall accuracy : {overall['accuracy_pct']}%")
        print(f"  Correct          : {overall['correct']}")
        print(f"  Incorrect        : {overall['incorrect']}")
        print(f"  Pending          : {overall['pending']}")
        print(f"  Total logged     : {overall['total_predictions']}")

    if by_team:
        print("\n  Per-Team Accuracy (top 10 by predictions):")
        print(f"  {'Team':<8} {'Predictions':>12} {'Correct':>8} {'Accuracy':>10}")
        print(f"  {'─'*8} {'─'*12} {'─'*8} {'─'*10}")
        for row in sorted(by_team, key=lambda r: r['predicted_count'], reverse=True)[:10]:
            print(f"  {row['team']:<8} {row['predicted_count']:>12} "
                  f"{int(row['correct']):>8} {row['accuracy_pct']:>9.1f}%")

    print("=" * 55)
    print("\nNext step: python scripts/retrain.py")


def main():
    parser = argparse.ArgumentParser(description='Update results and resolve predictions.')
    parser.add_argument('--season',    default=None,
                        help='Season string e.g. 2024-25 (defaults to current season)')
    parser.add_argument('--days-back', type=int, default=10,
                        help='How many days back to fetch results for (default: 10)')
    parser.add_argument('--skip-players', action='store_true',
                        help='Skip fetching player box scores (faster, game model only)')
    args = parser.parse_args()

    season = args.season or get_current_season()

    print("=" * 55)
    print("  CourtIQ — Update Results Script")
    print("=" * 55)
    print(f"Season    : {season}")
    print(f"Days back : {args.days_back}")

    init_db()

    # Step 1: Fetch recent game results
    print("\n── Step 1: Fetch recent game results ───────────────")
    recent_game_ids = fetch_recent_games(season, days_back=args.days_back)

    # Step 2: Update player box scores
    if not args.skip_players and recent_game_ids:
        print("\n── Step 2: Update player box scores ────────────────")
        update_player_box_scores(recent_game_ids)
    else:
        print("\n── Step 2: Skipping player box scores ──────────────")

    # Step 3: Resolve pending predictions
    print("\n── Step 3: Resolve pending predictions ─────────────")
    resolve_pending(recent_game_ids)

    # Step 4: Print summary
    print_accuracy_summary()


if __name__ == '__main__':
    main()