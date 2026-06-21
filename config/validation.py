"""Consulate validation script settings."""

import re

REQUIRED_FIELDS = ("mission_name", "address", "official_link", "note")
ISO3_RE = re.compile(r"^[A-Z]{3}$")
SINGAPORE_HINTS = ("singapore", "singapur", "singapour", "sg")
BOT_BLOCK_HINTS = ("RemoteDisconnected", "Connection aborted")
