"""CLI entrypoint for fetching/updating MFA mission data.

Run from the project root with::

    uv run python -m scripts.fetch_mfa_representatives
"""

from __future__ import annotations

import sys

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
