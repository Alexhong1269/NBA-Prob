# backend/__init__.py
# Top-level backend package for the CourtIQ NBA Prediction App.
# Exposes the database initializer so callers can do:
#   from backend import init_db

from backend.data.cache import init_db

__all__ = ['init_db']