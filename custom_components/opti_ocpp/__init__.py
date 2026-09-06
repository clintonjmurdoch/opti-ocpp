import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN
from .central_system import OptiCentralSystem
from ocpp.v16 import call

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    server = OptiCentralSystem(hass, entry)
    await server.start()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = server

    cid = entry.data["charger_id"]

    async def handle_service(call_data):
        instance = server.get_instance(cid)
        if not instance: return
        op = call_data.service.split("_", 1)[1]

        if op == "initialise": await instance.initialise(entry.data["default_limit"])
        elif op == "charge": await instance.start_charge()
        elif op == "stop": await instance.stop_charge()
        elif op == "reset": await instance.soft_reset()
        elif op == "limit": await instance.set_profile("TxProfile", call_data.data.get("limit", 6), 1, 2)
        elif op == "get_configuration":
            res = await instance.call(call.GetConfiguration())
            _LOGGER.info(f"Opti Config: {res}")
        elif op == "set_configuration":
            await instance.call(call.ChangeConfiguration(key=call_data.data["key"], value=call_data.data["value"]))

    for op in ["initialise", "charge", "stop", "reset", "limit", "get_configuration", "set_configuration"]:
        hass.services.async_register(DOMAIN, f"{cid}_{op}", handle_service)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "number"])
    return True

async def async_unload_entry(hass, entry):
    server = hass.data[DOMAIN].pop(entry.entry_id)
    await server.stop()
    return True
