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
        self._refresh_tasks = {} # Track periodic refresh tasks per charger

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
        for task in self._refresh_tasks.values():
            task.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _on_connect(self, websocket):
        path = websocket.request.path.strip('/')
        if path != self.charger_id: return

        handler = OptiOcppHandler(
            id=path,
            connection=websocket,
            on_status_change=self._handle_status_update,
            on_transaction_start=self._handle_tid_update,
            on_meter_values=self._handle_meter_values,
            initial_tid=self._cached_tid
        )
        self.instances[path] = handler

        loop_task = asyncio.create_task(handler.start())
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(handler.initialise(self.entry.data["default_limit"]))
        )

        try: await loop_task
        finally:
            self._stop_periodic_refresh(path)
            self.instances.pop(path, None)
            self._safe_dispatch(path, {"status": "Disconnected"})

    def _handle_status_update(self, cid, status):
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(self._async_update_status(cid, status))
        )

    async def _async_update_status(self, cid, status):
        self._safe_dispatch(cid, {"status": status})

        if status == "Charging":
            # Start periodic 30s refresh loop
            self._start_periodic_refresh(cid)
            await self._apply_limit(cid)
        else:
            # Session ended: Stop refresh loop and reset sensors to 0
            self._stop_periodic_refresh(cid)
            self._safe_dispatch(cid, {
                "power": 0, "power_l1": 0, "power_l2": 0, "power_l3": 0,
                "current_l1": 0, "current_l2": 0, "current_l3": 0,
                "current_offered": 0, "power_reactive": 0
            })

    def _start_periodic_refresh(self, cid):
        if cid in self._refresh_tasks: return

        async def _refresh_loop():
            try:
                while True:
                    instance = self.instances.get(cid)
                    if instance:
                        await instance.trigger_meter_values()
                    await asyncio.sleep(30)
            except asyncio.CancelledError: pass

        self._refresh_tasks[cid] = self.hass.async_create_task(_refresh_loop())

    def _stop_periodic_refresh(self, cid):
        task = self._refresh_tasks.pop(cid, None)
        if task: task.cancel()

    def _handle_tid_update(self, cid, tid):
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(self._async_save_tid(tid))
        )

    async def _async_save_tid(self, tid):
        self._cached_tid = tid
        await self._store.async_save({"active_transaction_id": tid})

    def _handle_meter_values(self, cid, data):
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(self._async_update_meter_data(cid, data))
        )

    async def _async_update_meter_data(self, cid, data):
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
            "Voltage_L3-N": "voltage_l3",
            "Current.Offered": "current_offered",
            "Power.Reactive.Import": "power_reactive",
            "Power.Factor": "power_factor",
            "Frequency": "frequency",
            "Temperature": "temperature"
        }
        update_payload = {}
        for ocpp_key, ha_suffix in mapping.items():
            if ocpp_key in data: update_payload[ha_suffix] = data[ocpp_key]

        if update_payload:
            self._safe_dispatch(cid, update_payload)

    def _safe_dispatch(self, cid, payload):
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send, self.hass, OPTI_DATA_UPDATE.format(cid), payload
        )

    async def _apply_limit(self, cid):
        state = self.hass.states.get(f"number.opti_{cid}_limit")
        if state and cid in self.instances:
            limit = float(state.state)
            instance = self.instances[cid]
            await instance.set_profile("TxProfile", limit, conn=1, stack=20)
            # Refresh meter values immediately after limit change
            await instance.trigger_meter_values()

    def get_instance(self, cid): return self.instances.get(cid)
