import os
import sqlite3
import pandas as pd
from datetime import datetime
from backend.data.cache import get_db_connection



def log_prediction(game_id: str, game_date: str, home_team: str, away_team: str,
                   predicted_winner: str, home_win_prob: float) -> None:
    """
    Saves a model prediction to prediction_logs before a game is played.
    actual_winner and is_correct are NULL until results come in.

    Called by: scripts/update_results.py or app.py when predictions are served.

    Args:
        game_id: NBA game ID string
        game_date: Date string (YYYY-MM-DD)
        home_team: Home team abbreviation
        away_team: Away team abbreviation
        predicted_winner: Team abbreviation the model picked
        home_win_prob: Model's confidence (0.0 - 1.0) that home team wins
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO prediction_logs
            (game_id, game_date, home_team, away_team,
             predicted_winner, predicted_home_win_prob,
             actual_winner, is_correct)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
    ''', (game_id, game_date, home_team, away_team, predicted_winner, home_win_prob))
    conn.commit()
    conn.close()


def log_predictions_batch(predictions_df: pd.DataFrame) -> int:
    """
    Logs a batch of pre-game predictions from a DataFrame.
    Skips rows that already have a logged prediction (INSERT OR IGNORE).

    Args:
        predictions_df: Must contain columns:
            game_id, game_date, home_team, away_team,
            predicted_winner, home_win_prob

    Returns:
        Number of new predictions inserted
    """
    required = {'game_id', 'game_date', 'home_team', 'away_team',
                'predicted_winner', 'home_win_prob'}
    missing = required - set(predictions_df.columns)
    if missing:
        raise ValueError(f"predictions_df is missing columns: {missing}")

    conn = get_db_connection()
    cursor = conn.cursor()
    inserted = 0

    for _, row in predictions_df.iterrows():
        cursor.execute('''
            INSERT OR IGNORE INTO prediction_logs
                (game_id, game_date, home_team, away_team,
                 predicted_winner, predicted_home_win_prob,
                 actual_winner, is_correct)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
        ''', (
            row['game_id'], row['game_date'], row['home_team'], row['away_team'],
            row['predicted_winner'], row['home_win_prob']
        ))
        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()
    conn.close()
    return inserted



def resolve_game_results(results_df: pd.DataFrame) -> dict:
    """
    Matches actual game results against pending predictions and marks them
    correct or incorrect. This is the core of the feedback loop.

    Call this after fetching fresh results from nba_api (update_results.py).

    Args:
        results_df: DataFrame with columns: game_id, home_pts, away_pts, wl_home
                    (same structure returned by fetcher.fetch_season_games)

    Returns:
        Dict with counts: { resolved, correct, incorrect, skipped }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    counts = {'resolved': 0, 'correct': 0, 'incorrect': 0, 'skipped': 0}

    for _, row in results_df.iterrows():
        game_id = str(row['game_id'])

        # Determine actual winner from final score
        if row['home_pts'] > row['away_pts']:
            actual_winner = row['home_team'] if 'home_team' in row else None
        else:
            actual_winner = row['away_team'] if 'away_team' in row else None

        # Fall back to wl_home if pts columns are missing
        if actual_winner is None:
            wl = row.get('wl_home', '')
            # We need team names — fetch from prediction_logs
            cursor.execute(
                'SELECT home_team, away_team FROM prediction_logs WHERE game_id = ?',
                (game_id,)
            )
            existing = cursor.fetchone()
            if not existing:
                counts['skipped'] += 1
                continue
            actual_winner = existing['home_team'] if wl == 'W' else existing['away_team']

        # Fetch the pending prediction for this game
        cursor.execute(
            '''SELECT predicted_winner FROM prediction_logs
               WHERE game_id = ? AND is_correct IS NULL''',
            (game_id,)
        )
        pending = cursor.fetchone()

        if not pending:
            counts['skipped'] += 1
            continue

        is_correct = 1 if pending['predicted_winner'] == actual_winner else 0

        cursor.execute(
            '''UPDATE prediction_logs
               SET actual_winner = ?, is_correct = ?
               WHERE game_id = ?''',
            (actual_winner, is_correct, game_id)
        )

        counts['resolved'] += 1
        counts['correct'] += is_correct
        counts['incorrect'] += (1 - is_correct)

    conn.commit()
    conn.close()

    if counts['resolved'] > 0:
        rate = round(counts['correct'] / counts['resolved'] * 100, 1)
        print(f"Resolved {counts['resolved']} games — {counts['correct']} correct ({rate}%)")

    return counts



def get_overall_accuracy() -> dict:
    """
    Returns overall prediction accuracy across all resolved games.

    Returns:
        Dict with total, correct, accuracy_pct, and pending count
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            COUNT(*)                                        AS total,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN is_correct IS NULL THEN 1 ELSE 0 END) AS pending
        FROM prediction_logs
    ''')
    row = cursor.fetchone()
    conn.close()

    total   = row['total'] or 0
    correct = row['correct'] or 0
    pending = row['pending'] or 0
    resolved = total - pending

    return {
        'total_predictions': total,
        'resolved': resolved,
        'correct': correct,
        'incorrect': resolved - correct,
        'pending': pending,
        'accuracy_pct': round(correct / resolved * 100, 1) if resolved > 0 else None,
    }


def get_accuracy_by_team() -> list[dict]:
    """
    Breaks down accuracy for each team the model has predicted on —
    both as home and away. Useful for spotting which teams the model
    struggles to predict correctly.

    Returns:
        List of dicts sorted by accuracy descending:
        [{ team, predicted_count, correct, accuracy_pct }, ...]
    """
    conn = get_db_connection()
    df = pd.read_sql_query('''
        SELECT predicted_winner AS team,
               COUNT(*)         AS predicted_count,
               SUM(is_correct)  AS correct
        FROM prediction_logs
        WHERE is_correct IS NOT NULL
        GROUP BY predicted_winner
        ORDER BY correct DESC
    ''', conn)
    conn.close()

    if df.empty:
        return []

    df['accuracy_pct'] = (df['correct'] / df['predicted_count'] * 100).round(1)
    return df.to_dict(orient='records')


def get_rolling_accuracy(window: int = 20) -> list[dict]:
    """
    Computes a rolling accuracy over the last N resolved predictions,
    ordered chronologically. Powers the accuracy trend chart on the dashboard.

    Args:
        window: Number of games per rolling window (default 20)

    Returns:
        List of dicts: [{ game_date, rolling_accuracy_pct }, ...]
    """
    conn = get_db_connection()
    df = pd.read_sql_query('''
        SELECT game_date, is_correct
        FROM prediction_logs
        WHERE is_correct IS NOT NULL
        ORDER BY game_date ASC
    ''', conn)
    conn.close()

    if df.empty:
        return []

    df['rolling_accuracy_pct'] = (
        df['is_correct']
        .rolling(window=window, min_periods=1)
        .mean()
        .mul(100)
        .round(1)
    )

    return df[['game_date', 'rolling_accuracy_pct']].to_dict(orient='records')


def get_confidence_calibration(buckets: int = 10) -> list[dict]:
    """
    Checks whether predicted win probabilities match real-world outcomes —
    e.g. do games predicted at 70% confidence actually result in wins ~70% of the time?

    Splits predictions into probability buckets and computes the actual win rate per bucket.
    A well-calibrated model's line should closely follow the diagonal.

    Args:
        buckets: Number of probability buckets to split into (default 10 = 10% increments)

    Returns:
        List of dicts: [{ bucket_label, predicted_prob, actual_win_rate, count }, ...]
    """
    conn = get_db_connection()
    df = pd.read_sql_query('''
        SELECT predicted_home_win_prob, is_correct
        FROM prediction_logs
        WHERE is_correct IS NOT NULL
    ''', conn)
    conn.close()

    if df.empty:
        return []

    df['bucket'] = pd.cut(
        df['predicted_home_win_prob'],
        bins=buckets,
        labels=[f"{int(i * 100 / buckets)}-{int((i + 1) * 100 / buckets)}%"
                for i in range(buckets)]
    )

    calibration = (
        df.groupby('bucket', observed=True)
        .agg(
            count=('is_correct', 'count'),
            actual_win_rate=('is_correct', 'mean'),
            predicted_prob=('predicted_home_win_prob', 'mean')
        )
        .reset_index()
    )

    calibration['actual_win_rate'] = (calibration['actual_win_rate'] * 100).round(1)
    calibration['predicted_prob']  = (calibration['predicted_prob']  * 100).round(1)

    return calibration.rename(columns={'bucket': 'bucket_label'}).to_dict(orient='records')


def get_pending_predictions() -> list[dict]:
    """
    Returns all predictions that have been logged but not yet resolved.
    Used by update_results.py to know which game IDs to fetch results for.

    Returns:
        List of dicts: [{ game_id, game_date, home_team, away_team, predicted_winner }, ...]
    """
    conn = get_db_connection()
    df = pd.read_sql_query('''
        SELECT game_id, game_date, home_team, away_team, predicted_winner
        FROM prediction_logs
        WHERE is_correct IS NULL
        ORDER BY game_date ASC
    ''', conn)
    conn.close()
    return df.to_dict(orient='records')



def get_full_accuracy_summary() -> dict:
    """
    Bundles all accuracy data into one payload for the dashboard API route.

    Returns:
        Dict with overall, by_team, rolling, and calibration data
    """
    return {
        'overall':     get_overall_accuracy(),
        'by_team':     get_accuracy_by_team(),
        'rolling':     get_rolling_accuracy(),
        'calibration': get_confidence_calibration(),
    }