import os
from flask import Flask, jsonify, request
from flask_cors import CORS

from backend.data.cache import (
    get_db_connection,
    init_db,
)
from backend.models.game_predictor import predict_game, predict_batch
from backend.models.player_predictor import predict_player_game, predict_team_players
from backend.models.trainer import retrain_all
from backend.models.accuracy import get_full_accuracy_summary, log_prediction

app = Flask(__name__)
CORS(app)

# Ensure the database and tables exist on startup
init_db()

# Simple admin token for the retrain endpoint — set via environment variable.
# Default is 'local-dev-only' so it works out of the box locally.
ADMIN_TOKEN = os.environ.get('NBA_ADMIN_TOKEN', 'local-dev-only')



@app.route('/api/health', methods=['GET'])
def health_check():
    """Confirms the API is running and the DB is reachable."""
    try:
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        db_status = 'connected'
    except Exception:
        db_status = 'unreachable'

    return jsonify({
        'status': 'healthy',
        'db': db_status,
        'message': 'NBA Prediction API is running.',
    })



@app.route('/api/games/upcoming', methods=['GET'])
def upcoming_games():
    """Returns all SCHEDULED games from the database cache."""
    try:
        conn = get_db_connection()
        rows = conn.execute(
            '''SELECT game_id, game_date, home_team, away_team
               FROM games
               WHERE status = 'SCHEDULED'
               ORDER BY game_date ASC'''
        ).fetchall()
        conn.close()

        games = [dict(row) for row in rows]
        return jsonify({'success': True, 'games': games})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/games/predict', methods=['POST'])
def predict_game_route():
    """
    Predicts the outcome of a matchup.

    Request body: { home_team, away_team, game_id (optional) }

    The caller must supply the engineered feature row — or this route builds
    it from the DB. For now we pull the latest cached features for the two teams.
    """
    data = request.get_json() or {}
    home_team = data.get('home_team')
    away_team = data.get('away_team')
    game_id   = data.get('game_id')

    if not home_team or not away_team:
        return jsonify({'success': False, 'error': 'Missing home_team or away_team'}), 400

    try:
        from backend.data.features import generate_training_datasets
        team_features_df, _ = generate_training_datasets()

        # Grab the most recent feature row for each team acting as home/away
        home_row = (
            team_features_df[team_features_df['team_home'] == home_team]
            .sort_values('game_date')
            .iloc[-1]
            .to_dict()
            if not team_features_df[team_features_df['team_home'] == home_team].empty
            else {}
        )

        if not home_row:
            return jsonify({'success': False,
                            'error': f'No feature data found for {home_team}'}), 404

        result = predict_game(home_team, away_team, home_row)

        if not result:
            return jsonify({'success': False,
                            'error': 'Model not loaded. Run retrain.py first.'}), 503

        # Log prediction if a game_id was supplied
        if game_id:
            log_prediction(
                game_id=game_id,
                game_date=home_row.get('game_date', ''),
                home_team=home_team,
                away_team=away_team,
                predicted_winner=result['predicted_winner'],
                home_win_prob=result['home_win_prob'],
            )

        return jsonify({'success': True, 'prediction': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/players/search', methods=['GET'])
def search_players():
    """
    Searches player names in the database.
    Query param: ?name=lebron
    Returns matching player_id + player_name pairs.
    """
    name_query = request.args.get('name', '').strip()
    if not name_query:
        return jsonify({'success': False, 'error': 'Missing name parameter'}), 400

    try:
        conn = get_db_connection()
        rows = conn.execute(
            '''SELECT DISTINCT player_id, player_name, team_abbreviation
               FROM player_stats
               WHERE LOWER(player_name) LIKE ?
               ORDER BY player_name ASC
               LIMIT 20''',
            (f'%{name_query.lower()}%',)
        ).fetchall()
        conn.close()

        players = [dict(row) for row in rows]
        return jsonify({'success': True, 'players': players})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/players/project', methods=['POST'])
def project_player():
    """
    Projects a player's stat line for an upcoming game.

    Request body: { player_id, opponent, is_home (0 or 1) }
    """
    data = request.get_json() or {}
    player_id = data.get('player_id')
    opponent  = data.get('opponent')
    is_home   = int(data.get('is_home', 1))

    if not player_id or not opponent:
        return jsonify({'success': False, 'error': 'Missing player_id or opponent'}), 400

    try:
        import pandas as pd
        from backend.data.features import build_player_features
        from backend.data.cache import get_db_connection as gdb

        conn = gdb()
        df_players = pd.read_sql_query(
            'SELECT * FROM player_stats ORDER BY game_date ASC', conn
        )
        conn.close()

        df_features = build_player_features(df_players)

        # Get the most recent feature row for this player
        player_rows = df_features[df_features['player_id'] == int(player_id)]
        if player_rows.empty:
            return jsonify({'success': False,
                            'error': f'No data found for player_id {player_id}'}), 404

        player_row = player_rows.sort_values('game_date').iloc[-1].to_dict()

        projection = predict_player_game(player_row, opponent, df_players, is_home)

        if not projection:
            return jsonify({'success': False,
                            'error': 'Player models not loaded. Run retrain.py first.'}), 503

        return jsonify({'success': True, 'data': projection})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/players/team', methods=['GET'])
def project_team():
    """
    Projects stat lines for all players on a team for a given opponent.
    Query params: ?team=BOS&opponent=MIA&is_home=1
    """
    team     = request.args.get('team')
    opponent = request.args.get('opponent')
    is_home  = int(request.args.get('is_home', 1))

    if not team or not opponent:
        return jsonify({'success': False, 'error': 'Missing team or opponent'}), 400

    try:
        import pandas as pd
        from backend.data.features import build_player_features

        conn = get_db_connection()
        df_players = pd.read_sql_query(
            'SELECT * FROM player_stats ORDER BY game_date ASC', conn
        )
        conn.close()

        df_features = build_player_features(df_players)

        # Get the latest row per player for this team
        team_players_df = (
            df_features[df_features['team_abbreviation'] == team]
            .sort_values('game_date')
            .groupby('player_id')
            .last()
            .reset_index()
        )

        if team_players_df.empty:
            return jsonify({'success': False,
                            'error': f'No player data found for team {team}'}), 404

        team_players = team_players_df.to_dict(orient='records')
        projections  = predict_team_players(team_players, opponent, df_players, is_home)

        return jsonify({'success': True, 'team': team, 'projections': projections})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/h2h', methods=['GET'])
def head_to_head():
    """
    Returns historical head-to-head record between two teams.
    Query params: ?team1=BOS&team2=MIA
    """
    team1 = request.args.get('team1')
    team2 = request.args.get('team2')

    if not team1 or not team2:
        return jsonify({'success': False, 'error': 'Missing team1 or team2'}), 400

    try:
        conn = get_db_connection()
        rows = conn.execute(
            '''SELECT game_date, home_team, away_team, home_pts, away_pts, wl_home
               FROM games
               WHERE status = 'FINAL'
                 AND ((home_team = ? AND away_team = ?)
                   OR (home_team = ? AND away_team = ?))
               ORDER BY game_date DESC
               LIMIT 20''',
            (team1, team2, team2, team1)
        ).fetchall()
        conn.close()

        games = [dict(row) for row in rows]

        # Compute win totals
        team1_wins = sum(
            1 for g in games
            if (g['home_team'] == team1 and g['wl_home'] == 'W') or
               (g['away_team'] == team1 and g['wl_home'] == 'L')
        )
        team2_wins = len(games) - team1_wins

        return jsonify({
            'success': True,
            'h2h': {
                'summary': {team1: team1_wins, team2: team2_wins},
                'games': games,
            },
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/accuracy', methods=['GET'])
def model_accuracy():
    """
    Returns the full accuracy summary for the dashboard.
    Shape matches get_full_accuracy_summary() from accuracy.py:
      { overall, by_team, rolling, calibration }
    """
    try:
        summary = get_full_accuracy_summary()
        return jsonify({'success': True, 'metrics': summary})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/admin/retrain', methods=['POST'])
def trigger_retrain():
    """
    Kicks off a full model retrain using all data currently in the database.
    Requires the X-Admin-Token header to match NBA_ADMIN_TOKEN env variable.
    """
    token = request.headers.get('X-Admin-Token', '')
    if token != ADMIN_TOKEN:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        summary = retrain_all(verbose=False)
        return jsonify({
            'success': True,
            'message': 'Retrain complete.',
            'summary': summary,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)