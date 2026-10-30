"""Constants for the Heatit WiFi integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "heatit_wifi"

SCAN_INTERVAL: Final = timedelta(seconds=30)

# Seconds to wait after a write before reading the status back, since the
# device can still report the old value right after a write.
REFRESH_AFTER_WRITE_DELAY: Final = 5

# The thermostat firmware reports exactly 100.0 for a disconnected or
# shorted floor/external NTC sensor; treat that reading as "no sensor".
NTC_FAULT_TEMPERATURE: Final = 100.0

# Older WiFi6 firmware has no "model" field.
FALLBACK_MODEL: Final = "WiFi6"

API_STATUS: Final = "/api/status"
API_PARAMETERS: Final = "/api/parameters"
