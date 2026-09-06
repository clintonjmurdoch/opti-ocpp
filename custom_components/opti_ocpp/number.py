from homeassistant.components.number import NumberEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OptiLimitSlider(hass, entry)])

class OptiLimitSlider(NumberEntity):
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry_id = entry.entry_id
        self.cid = entry.data["charger_id"]
        self._attr_name = f"Opti {self.cid} Limit"
        self._attr_unique_id = f"opti_{self.cid}_limit"
        self._attr_native_min_value = 6
        self._attr_native_max_value = 32
        self._attr_native_step = 1
        self._attr_native_value = entry.data["default_limit"]
        self._attr_icon = "mdi:current-ac"

    async def async_set_native_value(self, value):
        self._attr_native_value = value
        instance = self.hass.data[DOMAIN][self.entry_id].get_instance(self.cid)

        # We use TxProfile on Connector 1 as requested.
        # stackLevel 2 ensures it has priority over the default limit.
        if instance and instance.status == "Charging":
            await instance.set_profile("TxProfile", value, conn=1, stack=2)

        self.async_write_ha_state()
