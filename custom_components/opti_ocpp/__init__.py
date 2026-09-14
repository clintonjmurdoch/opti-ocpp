import logging
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN
from .central_system import OptiCentralSystem
from ocpp.v16 import call
from ocpp.v16.enums import ResetType

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Opti OCPP from a config entry."""
    server = OptiCentralSystem(hass, entry)
    await server.start()

    hass.data.setdefault(DOMAIN, {})
    hass.data[entry.entry_id] = server

    cid = entry.data["charger_id"]

    async def handle_service(service_call) -> ServiceResponse:
        instance = server.get_instance(cid)
        if not instance:
            _LOGGER.warning(f"Service {service_call.service} called but charger {cid} is not connected.")
            return None

        op = service_call.service

        if op == "initialise":
            await instance.initialise(entry.data["default_limit"])
        elif op == "charge":
            await instance.start_charge()
        elif op == "stop":
            await instance.stop_charge()
        elif op == "reset":
            await instance.call(call.ResetPayload(type=ResetType.soft))
        elif op == "clear_profiles":
            await instance.clear_profiles()
        elif op == "limit":
            await instance.set_profile("TxProfile", service_call.data.get("limit", 6), 1, 20)
        elif op == "get_configuration":
            # Response-capable service
            res = await instance.call(call.GetConfigurationPayload())
            # Convert the dataclass response to a serializable dictionary
            return instance._to_dict(res)
        elif op == "set_configuration":
            await instance.call(call.ChangeConfigurationPayload(key=service_call.data["key"], value=service_call.data["value"]))

        return None

    services = ["initialise", "charge", "stop", "reset", "clear_profiles", "limit", "get_configuration", "set_configuration"]
    for service_name in services:
        # Enable response support for get_configuration
        support = SupportsResponse.ONLY if service_name == "get_configuration" else SupportsResponse.NONE
        hass.services.async_register(DOMAIN, service_name, handle_service, supports_response=support)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "number", "switch"])
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    server = hass.data[DOMAIN].pop(entry.entry_id)
    await server.stop()
    return True
