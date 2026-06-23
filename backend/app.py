import os
from flask import Flask, jsonify, request
from flask_cors import CORS

# We'll import these as we build them out in the next steps
# from database.cache import get_upcoming_games, get_h2h_history, get_accuracy_metrics
# from models.game_predictor import predict_game_outcome
# from models.player_predictor import project_player_stats
# from models.trainer import run_retraining_pipeline

app = Flask(__name__)
CORS(app)  # Allows our frontend to talk to the backend without cross-origin issues

# Quick health check route
@app.route('/api/health', College=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "NBA Prediction API is running!"})

### --- GAME PREDICTIONS --- ###

@app.route('/api/games/upcoming', methods=['GET'])
def upcoming_games():
    """Fetches upcoming scheduled games for the user to select from."""
    try:
        # TODO: Pull these from our SQLite database cache once Phase 1 is done
        # games = get_upcoming_games()
        mock_games = [
            {"game_id": "0022500001", "home_team": "BOS", "away_team": "NYK", "game_date": "2026-10-24"},
            {"game_id": "0022500002", "home_team": "LAL", "away_team": "GSW", "game_date": "2026-10-24"}
        ]
        return jsonify({"success": True, "games": mock_games})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/games/predict', methods=['POST'])
def predict_game():
    """Predicts a matchup outcome based on home_team and away_team codes."""
    data = request.get_json() or {}
    home_team = data.get('home_team')
    away_team = data.get('away_team')

    if not home_team or not away_team:
        return jsonify({"success": False, "error": "Missing home_team or away_team"}), 400

    try:
        # TODO: Pass this to our XGBoost game model in Phase 2
        # prediction = predict_game_outcome(home_team, away_team)
        mock_prediction = {
            "home_team": home_team,
            "away_team": away_team,
            "home_win_probability": 58.4,
            "away_win_probability": 41.6,
            "key_factors": [
                {"factor": "Rest Advantage", "impact": "Home (+4.2%)"},
                {"factor": "Recent Form (Last 5)", "impact": "Home (+2.1%)"}
            ]
        }
        return jsonify({"success": True, "prediction": mock_prediction})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


### --- PLAYER PROJECTIONS --- ###

@app.route('/api/players/project', methods=['POST'])
def project_player():
    """Projects points, rebounds, assists, blocks, and steals for a player."""
    data = request.get_json() or {}
    player_name = data.get('player_name')
    opponent = data.get('opponent')

    if not player_name or not opponent:
        return jsonify({"success": False, "error": "Missing player_name or opponent"}), 400

    try:
        # TODO: Pass this to our multi-output or multi-model script in Phase 3
        # projection = project_player_stats(player_name, opponent)
        mock_projection = {
            "player_name": player_name,
            "opponent": opponent,
            "projections": {"pts": 24.5, "reb": 6.2, "ast": 7.1, "stl": 1.2, "blk": 0.4},
            "season_averages": {"pts": 26.1, "reb": 5.8, "ast": 6.4, "stl": 1.0, "blk": 0.5},
            "h2h_historical_avg": {"pts": 22.1, "reb": 6.0, "ast": 7.5, "stl": 1.5, "blk": 0.2}
        }
        return jsonify({"success": True, "data": mock_projection})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


### --- HEAD-TO-HEAD AND ACCURACY DASHBOARD --- ###

@app.route('/api/h2h', methods=['GET'])
def head_to_head():
    """Gets historical matchup history between two specific teams."""
    team1 = request.args.get('team1')
    team2 = request.args.get('team2')

    if not team1 or not team2:
        return jsonify({"success": False, "error": "Missing team1 or team2 parameter"}), 400

    try:
        # TODO: Pull historical head-to-head records from SQLite
        # h2h_data = get_h2h_history(team1, team2)
        mock_h2h = {
            "summary": {"team1_wins": 6, "team2_wins": 4},
            "last_5_games": [
                {"date": "2025-03-12", "winner": team1, "score": "112-105"},
                {"date": "2025-01-20", "winner": team2, "score": "98-104"}
            ]
        }
        return jsonify({"success": True, "h2h": mock_h2h})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/accuracy', methods=['GET'])
def model_accuracy():
    """Returns calibration and accuracy metrics over time for Chart.js."""
    try:
        # TODO: Query prediction logs vs real outcomes from SQLite in Phase 6
        # metrics = get_accuracy_metrics()
        mock_metrics = {
            "overall_accuracy": 64.2,
            "timeline": [
                {"week": "Week 1", "accuracy": 60.0},
                {"week": "Week 2", "accuracy": 62.5},
                {"week": "Week 3", "accuracy": 64.2}
            ],
            "calibration": {
                "bin_60_70": {"predicted_avg": 65.0, "actual_win_rate": 63.8},
                "bin_70_80": {"predicted_avg": 74.2, "actual_win_rate": 76.1}
            }
        }
        return jsonify({"success": True, "metrics": mock_metrics})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


### --- RETRAINING TRIGGER --- ###

@app.route('/api/admin/retrain', methods=['POST'])
def trigger_retrain():
    """Manually kicks off the pipeline to update models with newly logged real data."""
    try:
        # TODO: Run the manual retrain logic from Phase 5
        # run_retraining_pipeline()
        return jsonify({"success": True, "message": "Model retraining pipeline executed successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    # Running on local network port 5000
    app.run(host='127.0.0.1', port=5000, debug=True)