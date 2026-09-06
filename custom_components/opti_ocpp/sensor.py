import logging
from homeassistant.core import callback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfElectricCurrent, UnitOfElectricPotential
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, OPTI_DATA_UPDATE

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    cid = entry.data["charger_id"]
    sensors = [
        OptiGenericSensor(cid, "Status", "status", "mdi:ev-station"),
        OptiGenericSensor(cid, "Energy", "energy", "mdi:meter-electric", UnitOfEnergy.WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
        OptiGenericSensor(cid, "Energy Today", "energy_today", "mdi:calendar-today", UnitOfEnergy.WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
        OptiGenericSensor(cid, "Power", "power", "mdi:flash", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Power L1", "power_l1", "mdi:flash", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Power L2", "power_l2", "mdi:flash", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Power L3", "power_l3", "mdi:flash", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Current L1", "current_l1", "mdi:current-ac", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Current L2", "current_l2", "mdi:current-ac", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Current L3", "current_l3", "mdi:current-ac", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Voltage L1", "voltage_l1", "mdi:sine-wave", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Voltage L2", "voltage_l2", "mdi:sine-wave", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
        OptiGenericSensor(cid, "Voltage L3", "voltage_l3", "mdi:sine-wave", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
    ]
    async_add_entities(sensors)

class OptiGenericSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, cid, name, suffix, icon, unit=None, device_class=None, state_class=None):
        self.cid = cid
        self.suffix = suffix
        self._attr_name = f"Opti {cid} {name}"
        self._attr_unique_id = f"opti_{cid}_{suffix}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._value = "Disconnected" if suffix == "status" else None

        # Internal state for Energy Today tracking
        self._last_midnight_total = None

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                OPTI_DATA_UPDATE.format(self.cid),
                self._update_callback
            )
        )

    @callback
    def _update_callback(self, data):
        """Update the sensor's value."""
        if self.suffix == "energy_today":
            self._handle_daily_energy(data.get("energy"))
            return

        if self.suffix in data:
            new_val = data[self.suffix]
            if self._attr_native_unit_of_measurement:
                try: self._value = float(new_val)
                except (ValueError, TypeError): self._value = None
            else:
                self._value = new_val
            self.async_write_ha_state()

    def _handle_daily_energy(self, current_total_str):
        """Tracks the daily delta from the cumulative meter."""
        if current_total_str is None: return

        try:
            current_total = float(current_total_str)
            # On first run or restart, we assume today's start was the current total
            # In a full HA setup, utility_meter is better, but this provides a baseline.
            if self._last_midnight_total is None:
                self._last_midnight_total = current_total
                self._value = 0.0
            else:
                self._value = current_total - self._last_midnight_total

            self.async_write_ha_state()
        except Exception: pass

    @property
    def native_value(self):
        return self._value

    @property
    def available(self):
        if self.suffix == "status": return True
        return self._value is not None
