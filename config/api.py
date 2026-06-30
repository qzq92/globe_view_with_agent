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

# Singapore MFA settings
MFA_REPRESENTATIVES_URL = (
    "https://www.mfa.gov.sg/visiting-singapore/foreign-representatives-to-singapore/"
)

# Auto-refresh consulate data from MFA on app startup
AUTO_REFRESH_CONSULATES = True

# CountriesNow API (free, no key required)
COUNTRIESNOW_BASE = "https://countriesnow.space/api/v0.1/countries"

# Maximum cities to display per country
MAX_CITIES_DISPLAY = 5

# UN Protocol and Liaison Services public list (free, no key required)
UN_PROTOCOL_PDF_URL = (
    "https://www.un.org/dgacm/sites/www.un.org.dgacm/files/"
    "Documents_Protocol/hspmfmlist.pdf"
)
