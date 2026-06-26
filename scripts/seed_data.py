"""
seed_data.py — Run once to populate the SQLite database with historical NBA data.

Pulls 3 seasons of team game logs and individual player box scores from nba_api,
then writes everything into the local SQLite cache.

Usage:
    python scripts/seed_data.py

Expected runtime: 15–30 minutes depending on connection speed.
nba_api rate limits are respected via built-in sleep delays.
"""

import sys
import os
import time

# Allow imports from the project root
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from backend.data.fetcher import fetch_season_games, fetch_player_box_scores
from backend.data.cache import init_db, save_games_to_db, save_player_stats_to_db, get_db_connection

# ── Configuration ─────────────────────────────────────────────────────────────
# Adjust seasons here — more seasons = better model, longer seed time.
SEASONS = ['2022-23', '2023-24', '2024-25']

# How many games to process per batch before printing progress
BATCH_SIZE = 25


def get_already_seeded_game_ids() -> set:
    """
    Returns the set of game_ids already in the player_stats table.
    Lets us resume a partial seed without re-fetching box scores we already have.
    """
    conn = get_db_connection()
    rows = conn.execute('SELECT DISTINCT game_id FROM player_stats').fetchall()
    conn.close()
    return {row['game_id'] for row in rows}


def seed_games(seasons: list[str]) -> list[dict]:
    """
    Fetches team game logs for each season and saves them to SQLite.
    Returns a flat list of all game dicts for the box score pass.
    """
    all_games = []

    for season in seasons:
        print(f"\n── Season {season} ──────────────────────────────")
        df = fetch_season_games(season)

        if df.empty:
            print(f"  No data returned for {season}, skipping.")
            continue

        save_games_to_db(df)
        games_list = df[['game_id', 'game_date', 'home_team', 'away_team']].to_dict(orient='records')
        all_games.extend(games_list)
        print(f"  Saved {len(df)} games for {season}.")

        # Pause between seasons to be polite to the API
        time.sleep(2)

    return all_games


def seed_player_box_scores(all_games: list[dict]) -> None:
    """
    Fetches individual player box scores for every game.
    Skips games already present in player_stats (safe to resume).
    """
    already_seeded = get_already_seeded_game_ids()
    pending        = [g for g in all_games if str(g['game_id']) not in already_seeded]
    total          = len(pending)

    if not total:
        print("\nAll box scores already seeded — nothing to fetch.")
        return

    print(f"\nFetching box scores for {total} games (skipping {len(already_seeded)} already cached)...")

    for i, game in enumerate(pending, start=1):
        game_id   = str(game['game_id'])
        game_date = game['game_date']

        df_players = fetch_player_box_scores(game_id, game_date)

        if not df_players.empty:
            save_player_stats_to_db(df_players)

        # Progress report every BATCH_SIZE games
        if i % BATCH_SIZE == 0 or i == total:
            pct = round(i / total * 100, 1)
            print(f"  [{i}/{total}]  {pct}% complete")

    print("\nBox score seeding complete.")


def main():
    print("=" * 55)
    print("  CourtIQ — Database Seed Script")
    print("=" * 55)
    print(f"Seasons to seed: {', '.join(SEASONS)}")
    print("Initializing database...")

    init_db()

    # Pass 1: team game logs (fast — one call per season)
    print("\nPass 1: Team game logs")
    all_games = seed_games(SEASONS)

    if not all_games:
        print("\nNo games fetched. Check your nba_api connection and try again.")
        sys.exit(1)

    print(f"\nTotal games across all seasons: {len(all_games)}")

    # Pass 2: player box scores (slow — one call per game)
    print("\nPass 2: Player box scores")
    print("This will take a while. You can safely Ctrl+C and re-run —")
    print("already-fetched box scores will be skipped on resume.\n")

    seed_player_box_scores(all_games)

    # Final summary
    conn = get_db_connection()
    game_count   = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    player_count = conn.execute("SELECT COUNT(*) FROM player_stats").fetchone()[0]
    conn.close()

    print("\n" + "=" * 55)
    print("  Seed complete.")
    print(f"  Games in DB      : {game_count:,}")
    print(f"  Player rows in DB: {player_count:,}")
    print("=" * 55)
    print("\nNext step: python scripts/retrain.py")


if __name__ == '__main__':
    main()