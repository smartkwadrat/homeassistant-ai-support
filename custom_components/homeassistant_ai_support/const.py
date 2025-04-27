"""Constants for the Home Assistant AI Support integration."""
from homeassistant.helpers.storage import Store

DOMAIN = "homeassistant_ai_support"

# Konfiguracja
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_COST_OPTIMIZATION = "cost_optimization"
CONF_SYSTEM_PROMPT = "system_prompt"
CONF_LOG_LEVELS = "log_levels"
CONF_MAX_REPORTS = "max_reports"
CONF_DIAGNOSTIC_INTEGRATION = "diagnostic_integration"

# Wartości domyślne
DEFAULT_SCAN_INTERVAL = 24
DEFAULT_COST_OPTIMIZATION = False
DEFAULT_MAX_REPORTS = 10
DEFAULT_DIAGNOSTIC_INTEGRATION = True
DEFAULT_LOG_LEVELS = ["ERROR", "WARNING"]

# Mapowanie modeli
MODEL_MAPPING = {
    "GPT-4.1": "gpt-4.1",
    "GPT-4.1 mini": "gpt-4.1-mini",
    "GPT-4.1 nano": "gpt-4.1-nano",
    "GPT-4o": "gpt-4o",
    "GPT-4o mini": "gpt-4o-mini"
}

MODEL_LIST = list(MODEL_MAPPING.keys())
DEFAULT_MODEL = "GPT-4.1 mini"

# Prompt systemowy
DEFAULT_SYSTEM_PROMPT = (
    "Jesteś ekspertem od analizy logów systemowych Home Assistant. "
    "Przeanalizuj poniższe logi i przygotuj zwięzły raport, "
    "wskazując potencjalne problemy i sugerując rozwiązania."
)

# Dodaj nowe stałe dla interwałów analizy
SCAN_INTERVAL_DAILY = "daily"
SCAN_INTERVAL_2_DAYS = "2_days"
SCAN_INTERVAL_7_DAYS = "7_days"
SCAN_INTERVAL_30_DAYS = "30_days"

SCAN_INTERVAL_OPTIONS = {
    SCAN_INTERVAL_DAILY: 1,  # 1 dzień
    SCAN_INTERVAL_2_DAYS: 2,  # 2 dni
    SCAN_INTERVAL_7_DAYS: 7,  # 7 dni
    SCAN_INTERVAL_30_DAYS: 30,  # 30 dni
}

DEFAULT_SCAN_INTERVAL = SCAN_INTERVAL_7_DAYS  # Domyślnie co 7 dni

# Godzina generowania raportu (23:50)
REPORT_GENERATION_HOUR = 23
REPORT_GENERATION_MINUTE = 50
