import logging
from homeassistant.core import callback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, OPTI_DATA_UPDATE

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    cid = entry.data["charger_id"]
    async_add_entities([OptiChargeSwitch(hass, entry)])

class OptiChargeSwitch(SwitchEntity):
    _attr_should_poll = False

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry_id = entry.entry_id
        self.cid = entry.data["charger_id"]
        self._attr_name = f"Opti {self.cid} Charge Switch"
        self._attr_unique_id = f"opti_{self.cid}_charge_switch"
        self._attr_icon = "mdi:ev-station"
        self._is_on = False
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
        """Update switch state based on charger status."""
        self._available = True
        if "status" in data:
            self._is_on = (data["status"] == "Charging")
        self.async_write_ha_state()

    @property
    def is_on(self):
        return self._is_on

    @property
    def available(self):
        return self._available

    async def async_turn_on(self, **kwargs):
        server = self.hass.data[DOMAIN][self.entry_id]
        instance = server.get_instance(self.cid)
        if instance:
            await instance.start_charge()

    async def async_turn_off(self, **kwargs):
        server = self.hass.data[DOMAIN][self.entry_id]
        instance = server.get_instance(self.cid)
        if instance:
            await instance.stop_charge()
