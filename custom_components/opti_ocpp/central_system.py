import asyncio
import logging
import websockets
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .ocpp_handler import OptiOcppHandler
from .const import DOMAIN, OPTI_DATA_UPDATE

_LOGGER = logging.getLogger(__name__)

class OptiCentralSystem:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.charger_id = entry.data["charger_id"]
        self.port = entry.data["port"]
        self.instances = {}
        self._server = None
        self._store = Store(hass, 1, f"{DOMAIN}_{self.charger_id}_data")
        self._cached_tid = None

    async def start(self):
        data = await self._store.async_load()
        if data:
            self._cached_tid = data.get("active_transaction_id")

        self._server = await websockets.serve(self._on_connect, "0.0.0.0", self.port, subprotocols=["ocpp1.6"])

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _on_connect(self, websocket):
        path = websocket.request.path.strip('/')
        if path != self.charger_id: return

        handler = OptiOcppHandler(
            id=path,
            connection=websocket,
            on_status_change=self._update_status,
            on_transaction_start=self._handle_tid_update,
            on_meter_values=self._handle_meter_values,
            initial_tid=self._cached_tid
        )
        self.instances[path] = handler
        await handler.initialise(self.entry.data["default_limit"])
        try: await handler.start()
        finally:
            self.instances.pop(path, None)
            async_dispatcher_send(self.hass, OPTI_DATA_UPDATE.format(path), {"status": "Disconnected"})

    async def _update_status(self, cid, status):
        # Notify entities via dispatcher
        async_dispatcher_send(self.hass, OPTI_DATA_UPDATE.format(cid), {"status": status})

        if status == "Charging":
            await self._apply_limit(cid)

    async def _handle_tid_update(self, cid, tid):
        self._cached_tid = tid
        await self._store.async_save({"active_transaction_id": tid})

    async def _handle_meter_values(self, cid, data):
        """Maps incoming raw meter measurands to HA sensor suffixes"""
        mapping = {
            "Energy.Active.Import.Register": "energy",
            "Power.Active.Import": "power",
            "Power.Active.Import_L1-N": "power_l1",
            "Power.Active.Import_L2-N": "power_l2",
            "Power.Active.Import_L3-N": "power_l3",
            "Current.Import_L1-N": "current_l1",
            "Current.Import_L2-N": "current_l2",
            "Current.Import_L3-N": "current_l3",
            "Voltage_L1-N": "voltage_l1",
            "Voltage_L2-N": "voltage_l2",
            "Voltage_L3-N": "voltage_l3"
        }
        update_payload = {}
        for ocpp_key, ha_suffix in mapping.items():
            if ocpp_key in data:
                update_payload[ha_suffix] = data[ocpp_key]

        if update_payload:
            async_dispatcher_send(self.hass, OPTI_DATA_UPDATE.format(cid), update_payload)

    async def _apply_limit(self, cid):
        state = self.hass.states.get(f"number.opti_{cid}_limit")
        if state and cid in self.instances:
            await self.instances[cid].set_profile("TxProfile", float(state.state), conn=1, stack=2)

    def get_instance(self, cid): return self.instances.get(cid)
