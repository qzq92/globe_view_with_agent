"""CLI entrypoint for consulate dataset validation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers.consulate_validation import main


if __name__ == "__main__":
    raise SystemExit(main())
