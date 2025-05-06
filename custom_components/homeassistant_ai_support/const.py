"""Constants for the Home Assistant AI Support integration."""
from homeassistant.helpers.storage import Store
from homeassistant.const import UnitOfTime

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

# Anomaly detection configuration
CONF_ENTITY_COUNT = "entity_count"
CONF_STANDARD_CHECK_INTERVAL = "standard_check_interval"
CONF_PRIORITY_CHECK_INTERVAL = "priority_check_interval"
CONF_ANOMALY_CHECK_INTERVAL = "anomaly_check_interval"
CONF_BASELINE_REFRESH_INTERVAL = "baseline_refresh_interval"
CONF_LEARNING_MODE = "learning_mode"

# Wartości domyślne
DEFAULT_SCAN_INTERVAL = 24
DEFAULT_COST_OPTIMIZATION = False
DEFAULT_MAX_REPORTS = "10"
DEFAULT_DIAGNOSTIC_INTEGRATION = True
DEFAULT_LOG_LEVELS = ["CRITICAL", "ERROR", "WARNING"]
DEFAULT_ENTITY_COUNT = 20
DEFAULT_STANDARD_CHECK_INTERVAL = 60  # minutes
DEFAULT_PRIORITY_CHECK_INTERVAL = 15  # minutes
DEFAULT_ANOMALY_CHECK_INTERVAL = 60  # minutes
DEFAULT_BASELINE_REFRESH_INTERVAL = "14_days"
DEFAULT_LEARNING_MODE = False

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
    SCAN_INTERVAL_DAILY: 1,
    SCAN_INTERVAL_2_DAYS: 2,
    SCAN_INTERVAL_7_DAYS: 7,
    SCAN_INTERVAL_30_DAYS: 30,
}

DEFAULT_SCAN_INTERVAL = SCAN_INTERVAL_7_DAYS  # Domyślnie co 7 dni

# Godzina generowania raportu (23:50)
REPORT_GENERATION_HOUR = 23
REPORT_GENERATION_MINUTE = 50

# Baseline refresh options
BASELINE_REFRESH_OPTIONS = {
    "3_days": "Co 3 dni",
    "7_days": "Co 7 dni",
    "14_days": "Co 14 dni",
    "30_days": "Co 30 dni",
}

# Logging constants
ANOMALY_LOG_DIR = "ai_anomaly_logs"
FALSE_ALARM_LOG_FILE = "false_alarms.json"
REJECTED_ANOMALIES_FILE = "rejected_anomalies.json"

STANDARD_CHECK_INTERVAL_OPTIONS = {
    "30": "Co 30 min",
    "60": "Co 60 min",
    "120": "Co 2 godziny",
    "240": "Co 4 godziny",
}
PRIORITY_CHECK_INTERVAL_OPTIONS = {
    "1": "Co 1 min",
    "5": "Co 5 min",
    "15": "Co 15 min",
    "30": "Co 30 min",
}
DEFAULT_STANDARD_CHECK_INTERVAL = "60" 
DEFAULT_PRIORITY_CHECK_INTERVAL = "15"

# Sensor attributes
ATTR_LAST_ANOMALY = "last_anomaly"
ATTR_FALSE_ALARMS = "false_alarms"
ATTR_SENSITIVITY = "current_sensitivity"