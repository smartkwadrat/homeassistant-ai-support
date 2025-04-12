"""Constants for the Home Assistant AI Support integration."""

# Domenę integracji musi być zgodna z nazwą folderu
DOMAIN = "homeassistant_ai_support"

# Klucze konfiguracji
CONF_API_KEY = "api_key"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MODEL = "model"

# Wartości domyślne
DEFAULT_MODEL = "gpt-4"
DEFAULT_SCAN_INTERVAL = 24  # w godzinach

# Usługi
SERVICE_ANALYZE_NOW = "analyze_now"

# Atrybuty encji
ATTR_LAST_ANALYSIS = "last_analysis"
ATTR_ANALYSIS_REPORT = "analysis_report"
