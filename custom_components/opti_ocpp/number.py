import asyncio
import logging
from homeassistant.core import callback
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, OPTI_DATA_UPDATE, OPTI_RESET_LIMIT

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OptiLimitSlider(hass, entry)])

class OptiLimitSlider(NumberEntity):
    _attr_should_poll = False

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry_id = entry.entry_id
        self.cid = entry.data["charger_id"]
        self.default_limit = entry.data["default_limit"]
        self._attr_name = f"Opti {self.cid} Limit"
        self._attr_unique_id = f"opti_{self.cid}_limit"
        self._attr_native_min_value = 6 # Strict minimum as requested
        self._attr_native_max_value = 32
        self._attr_native_step = 1
        self._attr_native_value = self.default_limit
        self._attr_icon = "mdi:current-ac"
        self._available = False
        self._debounce_task = None

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                OPTI_DATA_UPDATE.format(self.cid),
                self._update_callback
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                OPTI_RESET_LIMIT.format(self.cid),
                self._reset_limit_callback
            )
        )

    @callback
    def _update_callback(self, data):
        """Update availability when charger connects."""
        self._available = True
        self.async_write_ha_state()

    @callback
    def _reset_limit_callback(self):
        """Reset the slider to the configured default limit."""
        _LOGGER.info(f"Resetting {self.cid} limit to default: {self.default_limit}A")
        self._attr_native_value = self.default_limit
        self.async_write_ha_state()

    @property
    def available(self):
        return self._available

    async def async_set_native_value(self, value):
        """Update the value with 500ms debounce."""
        self._attr_native_value = value
        self.async_write_ha_state()

        if self._debounce_task:
            self._debounce_task.cancel()

        async def _debounced_set():
            await asyncio.sleep(0.5) # 500ms debounce
            server = self.hass.data[DOMAIN][self.entry_id]
            instance = server.get_instance(self.cid)
            if instance and instance.status == "Charging":
                _LOGGER.info(f"Debounce complete. Pushing limit {value}A to {self.cid}")
                await instance.set_profile("TxProfile", value, conn=1, stack=20)
            self._debounce_task = None

        self._debounce_task = self.hass.async_create_task(_debounced_set())
