from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfElectricCurrent, UnitOfElectricPotential
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    cid = entry.data["charger_id"]
    sensors = [
        OptiGenericSensor(cid, "Status", "status", "mdi:ev-station"),
        OptiGenericSensor(cid, "Energy", "energy", "mdi:meter-electric", UnitOfEnergy.WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
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
    def __init__(self, cid, name, suffix, icon, unit=None, device_class=None, state_class=None):
        self._attr_name = f"Opti {cid} {name}"
        self._attr_unique_id = f"opti_{cid}_{suffix}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def native_value(self):
        state = self.hass.states.get(self.entity_id)
        return state.state if state else None
