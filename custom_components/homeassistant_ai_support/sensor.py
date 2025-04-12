from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

class LogAnalysisSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:clipboard-text-search"
    _attr_name = "AI Log Analysis"

    @property
    def native_value(self):
        return "Active" if self.coordinator.data else "Inactive"

    @property
    def extra_state_attributes(self):
        return {
            "last_analysis": self.coordinator.last_update_success,
            "report": self.coordinator.data.get("analysis", "")
        }