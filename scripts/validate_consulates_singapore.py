"""CLI entrypoint for consulate dataset validation.

Run from the project root with::

    uv run python -m scripts.validate_consulates_singapore
    uv run python -m scripts.validate_consulates_singapore --offline
"""

from __future__ import annotations

from helpers.consulate_validation import main


if __name__ == "__main__":
    raise SystemExit(main())
