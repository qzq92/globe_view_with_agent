"""Filesystem paths used across the project."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CONSULATES_FILE = DATA_DIR / "consulates_singapore.json"
RESTCOUNTRIES_CACHE_FILE = CACHE_DIR / "restcountries_v5.json"
WORLDBANK_CACHE_FILE = CACHE_DIR / "worldbank.json"
ENV_FILE = BASE_DIR / ".env"
