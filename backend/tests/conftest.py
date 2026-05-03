"""Pytest plumbing — adds python-backend/ to sys.path so `backend.app...` etc. resolve."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
