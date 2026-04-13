"""Compatibility entrypoint.

Prefer running with: `uvicorn app.main:app --reload --port 8557`
This module is kept for backward compatibility with existing scripts.
"""

from app.main import app as fastapi_app

app = fastapi_app

__all__ = ["app"]
