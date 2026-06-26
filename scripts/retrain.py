"""
retrain.py — Triggers a full model retrain using all data currently in SQLite.

Run this after update_results.py has resolved new game outcomes.
The expanded dataset (including recent results) is what drives the feedback loop.

Usage:
    python scripts/retrain.py
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from backend.models.trainer import retrain_all

if __name__ == '__main__':
    print("=" * 55)
    print("  CourtIQ — Model Retrain Script")
    print("=" * 55)

    summary = retrain_all(verbose=True)

    print("\nModels saved to backend/models/saved/")
    print("Restart Flask (python backend/app.py) to load the updated models.")