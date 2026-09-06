import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_CHARGER_ID, CONF_DEFAULT_LIMIT, CONF_PORT, DEFAULT_PORT, DEFAULT_LIMIT

class OptiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=f"SEVR Opti ({user_input[CONF_CHARGER_ID]})", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_CHARGER_ID, default="charger"): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_DEFAULT_LIMIT, default=DEFAULT_LIMIT): int,
            })
        )
