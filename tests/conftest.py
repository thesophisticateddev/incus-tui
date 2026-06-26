"""Pytest setup: make incus_tui importable when running from the repo root."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
