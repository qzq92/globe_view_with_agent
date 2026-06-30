"""CLI entrypoint for fetching/updating MFA mission data."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers.mfa import fetch_and_update


if __name__ == "__main__":
    result = fetch_and_update()
    if result:
        print(f"\n{'=' * 50}")
        print(f"Successfully updated {len(result)} missions")
        print(f"Countries: {sorted(result.keys())}")
    else:
        print("\nFailed to update missions")
        sys.exit(1)
