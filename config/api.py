"""External API endpoints and request settings."""

REST_COUNTRIES_BASE = "https://api.restcountries.com/countries/v5"
REST_COUNTRIES_API_KEY_ENV = "REST_COUNTRIES_API_KEY"

WORLD_BANK_BASE = "https://api.worldbank.org/v2"
POPULATION_INDICATOR = "SP.POP.TOTL"
AREA_INDICATOR = "AG.LND.TOTL.K2"

PAGE_LIMIT = 100
REQUEST_TIMEOUT = 60

# Re-use cached API responses for this many seconds before refreshing.
CACHE_TTL_SECONDS = 86_400  # 24 hours
