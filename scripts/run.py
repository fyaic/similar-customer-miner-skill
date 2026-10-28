#!/usr/bin/env python3
"""Portable entrypoint: works from any working directory after unpacking the skill."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cli import main
if __name__ == '__main__':
    raise SystemExit(main())
