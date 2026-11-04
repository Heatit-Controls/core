"""Constants for the Heatit WiFi integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "heatit_wifi"

PLATFORMS: Final = [Platform.CLIMATE, Platform.SWITCH]

SCAN_INTERVAL: Final = timedelta(seconds=30)

# The device can still report the old value right after a write.
REFRESH_AFTER_WRITE_DELAY: Final = 5

FALLBACK_MODEL: Final = "WiFi6"

MODE_OFF: Final = 0
MODE_HEAT: Final = 1
MODE_COOL: Final = 2
MODE_ECO: Final = 3

SETPOINT_PARAMETERS: Final = {
    MODE_OFF: "heatingSetpoint",
    MODE_HEAT: "heatingSetpoint",
    MODE_COOL: "coolingSetpoint",
    MODE_ECO: "ecoSetpoint",
}

# sensorMode values regulating on the floor / external sensor (F, A2, A2F).
SENSOR_MODES_FLOOR: Final = (0,)
SENSOR_MODES_EXTERNAL: Final = (3, 4)
