import logging
from homeassistant.core import callback
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, OPTI_DATA_UPDATE

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OptiLimitSlider(hass, entry)])

class OptiLimitSlider(NumberEntity):
    _attr_should_poll = False

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry_id = entry.entry_id
        self.cid = entry.data["charger_id"]
        self._attr_name = f"Opti {self.cid} Limit"
        self._attr_unique_id = f"opti_{self.cid}_limit"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 32
        self._attr_native_step = 1
        self._attr_native_value = entry.data["default_limit"]
        self._attr_icon = "mdi:current-ac"
        self._available = False

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
        """Update availability when charger connects."""
        self._available = True
        self.async_write_ha_state()

    @property
    def available(self):
        return self._available

    async def async_set_native_value(self, value):
        self._attr_native_value = value
        server = self.hass.data[DOMAIN][self.entry_id]
        instance = server.get_instance(self.cid)

        # Increased stack to 20 to override any previous test harness values
        if instance and instance.status == "Charging":
            await instance.set_profile("TxProfile", value, conn=1, stack=20)

        self.async_write_ha_state()
