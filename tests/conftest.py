"""Pytest configuration."""

import os
import sys

# Ensure repo root is on path when running `pytest` from project root.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
