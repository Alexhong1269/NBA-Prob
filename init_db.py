"""
init_db.py — Run this once when setting up the project for the first time.
Creates the SQLite database and all required tables inside database/nba.db.

Usage:
    python init_db.py
"""

from backend.data.cache import init_db

if __name__ == '__main__':
    print("Initializing NBA prediction database...")
    init_db()
    print("\nDone. You can now run: python scripts/seed_data.py")