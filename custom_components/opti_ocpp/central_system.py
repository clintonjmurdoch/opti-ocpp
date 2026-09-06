import asyncio
import logging
import websockets
from homeassistant.core import callback
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

        try:
            self._server = await websockets.serve(
                self._on_connect, "0.0.0.0", self.port, subprotocols=["ocpp1.6"]
            )
            _LOGGER.info(f"OCPP Server listening on port {self.port}")
        except Exception as e:
            _LOGGER.error(f"Failed to start server: {e}")

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

        # Start listener and initialise in background
        loop_task = asyncio.create_task(handler.start())
        self.hass.add_job(self._safe_initialise(handler))

        try: await loop_task
        finally:
            self.instances.pop(path, None)
            self._safe_dispatch(path, {"status": "Disconnected"})

    async def _safe_initialise(self, handler):
        await handler.initialise(self.entry.data["default_limit"])

    def _update_status(self, cid, status):
        self._safe_dispatch(cid, {"status": status})
        if status == "Charging":
            self.hass.add_job(self._apply_limit(cid))

    def _handle_tid_update(self, cid, tid):
        self._cached_tid = tid
        self.hass.add_job(self._store.async_save({"active_transaction_id": tid}))

    def _handle_meter_values(self, cid, data):
        """Bridges raw measurands to HA sensors (Thread-Safe)"""
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
            if ocpp_key in data: update_payload[ha_suffix] = data[ocpp_key]

        if update_payload:
            self._safe_dispatch(cid, update_payload)

    def _safe_dispatch(self, cid, payload):
        """Official HA pattern to bridge external threads to the event loop."""
        self.hass.add_job(
            async_dispatcher_send, self.hass, OPTI_DATA_UPDATE.format(cid), payload
        )

    async def _apply_limit(self, cid):
        state = self.hass.states.get(f"number.opti_{cid}_limit")
        if state and cid in self.instances:
            await self.instances[cid].set_profile("TxProfile", float(state.state), conn=1, stack=20)

    def get_instance(self, cid): return self.instances.get(cid)
