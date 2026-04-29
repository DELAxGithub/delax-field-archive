"""Pytest fixtures: add scripts/ to sys.path so tests can import target modules.

Run with:
    uv run --with pytest pytest tests/
or:
    pytest tests/   (if pytest is already in your env)
"""
from __future__ import annotations
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
