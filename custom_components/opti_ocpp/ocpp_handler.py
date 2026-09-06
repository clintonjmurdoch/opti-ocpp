import asyncio
import logging
from datetime import datetime, timezone
import random
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, RegistrationStatus, AuthorizationStatus, ResetType

_LOGGER = logging.getLogger(__name__)

class OptiOcppHandler(cp):
    def __init__(self, id, connection, on_status_change=None, on_transaction_start=None, on_meter_values=None, initial_tid=None):
        super().__init__(id, connection)
        self.status = "Disconnected"
        self.active_transaction_id = initial_tid
        self.phase_count = 3
        self._on_status_change = on_status_change
        self._on_transaction_start = on_transaction_start
        self._on_meter_values = on_meter_values
        self._suspended_timer = None

    @on(Action.BootNotification)
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        _LOGGER.info(f"Received Boot from {charge_point_vendor} ({charge_point_model})")
        if "7" in charge_point_model and "22" not in charge_point_model:
            self.phase_count = 1
        else:
            self.phase_count = 3
        return call_result.BootNotificationPayload(
            current_time=datetime.now(timezone.utc).isoformat(),
            interval=30,
            status=RegistrationStatus.accepted
        )

    @on(Action.Heartbeat)
    async def on_heartbeat(self, **kwargs):
        return call_result.HeartbeatPayload(current_time=datetime.now(timezone.utc).isoformat())

    @on(Action.Authorize)
    async def on_authorize(self, id_tag, **kwargs):
        return call_result.AuthorizePayload(id_tag_info={'status': AuthorizationStatus.accepted})

    @on(Action.StatusNotification)
    async def on_status_notification(self, connector_id, error_code, status, **kwargs):
        self.status = status
        if self._on_status_change:
            await self._on_status_change(self.id, status)

        if status == "SuspendedEV":
            self._start_timer()
        else:
            self._stop_timer()
        return call_result.StatusNotificationPayload()

    @on(Action.StartTransaction)
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        tid = 1234
        self.active_transaction_id = tid
        _LOGGER.info(f"Transaction {tid} started.")
        if self._on_transaction_start:
            await self._on_transaction_start(self.id, tid)
        return call_result.StartTransactionPayload(transaction_id=tid, id_tag_info={'status': AuthorizationStatus.accepted})

    @on(Action.StopTransaction)
    async def on_stop_transaction(self, meter_stop, timestamp, transaction_id, **kwargs):
        _LOGGER.info(f"Transaction {transaction_id} stopped.")
        self.active_transaction_id = None
        if self._on_transaction_start:
            await self._on_transaction_start(self.id, None)
        self._stop_timer()
        return call_result.StopTransactionPayload()

    @on(Action.MeterValues)
    async def on_meter_values(self, connector_id, meter_value, transaction_id=None, **kwargs):
        if transaction_id and self.active_transaction_id != transaction_id:
            self.active_transaction_id = transaction_id
            if self._on_transaction_start:
                await self._on_transaction_start(self.id, transaction_id)

        if self._on_meter_values:
            data = {}
            for mv in meter_value:
                sv_list = getattr(mv, 'sampled_value', []) if not isinstance(mv, dict) else mv.get('sampledValue', [])
                for sv in sv_list:
                    measurand = getattr(sv, 'measurand', 'Energy.Active.Import.Register') if not isinstance(sv, dict) else sv.get('measurand')
                    phase = getattr(sv, 'phase', None) if not isinstance(sv, dict) else sv.get('phase')
                    val = getattr(sv, 'value', None) if not isinstance(sv, dict) else sv.get('value')

                    if val is not None:
                        key = measurand
                        if phase: key = f"{measurand}_{phase}"
                        data[key] = val
            if data:
                await self._on_meter_values(self.id, data)
        return call_result.MeterValuesPayload()

    # --- Actions ---

    async def initialise(self, limit):
        opts = {
            'TxBeforeAcceptedEnabled': 'true',
            'AuthorizeRemoteTxRequests': 'false',
            'StopTransactionOnInvalidId': 'false',
            'UnlockConnectorOnEVSideDisconnect': 'false'
        }
        for k, v in opts.items():
            try:
                res = await self.call(call.ChangeConfigurationPayload(key=k, value=v))
                _LOGGER.info(f"Configuration change {k} to {v}: {res.status}")
            except Exception as e:
                _LOGGER.error(f"Failed to set {k}: {e}")
        await self.set_profile("TxDefaultProfile", limit, 1, 1)

    async def set_profile(self, purpose, amps, conn=1, stack=1):
        id_map = {'ChargePointMaxProfile': 100, 'TxDefaultProfile': 200, 'TxProfile': 300}
        profile_id = id_map.get(purpose, 999)
        prof = {
            'chargingProfileId': profile_id,
            'stackLevel': stack,
            'chargingProfilePurpose': purpose,
            'chargingProfileKind': 'Relative',
            'chargingSchedule': {
                'chargingRateUnit': 'A',
                'chargingSchedulePeriod': [{'startPeriod':0, 'limit':float(amps), 'numberPhases':self.phase_count}]
            }
        }
        if purpose == "TxProfile" and self.active_transaction_id:
            prof['transactionId'] = self.active_transaction_id

        try:
            res = await self.call(call.SetChargingProfilePayload(connector_id=conn, cs_charging_profiles=prof))
            _LOGGER.info(f"Profile {purpose} ({amps}A) result: {res.status}")
        except Exception as e:
            _LOGGER.error(f"Failed to set profile {purpose}: {e}")

    async def start_charge(self):
        res = await self.call(call.RemoteStartTransactionPayload(id_tag='PLUG_PLAY_IDTAG', connector_id=1))
        _LOGGER.info(f"RemoteStart result: {res.status}")
        return res

    async def stop_charge(self):
        tid = self.active_transaction_id or 1234
        res = await self.call(call.RemoteStopTransactionPayload(transaction_id=tid))
        _LOGGER.info(f"RemoteStop result for TID {tid}: {res.status}")
        return res

    def _start_timer(self):
        self._stop_timer()
        async def kill():
            await asyncio.sleep(30)
            if self.status == "SuspendedEV":
                _LOGGER.warning("SuspendedEV timeout reached. Killing transaction.")
                await self.stop_charge()
        self._suspended_timer = asyncio.create_task(kill())

    def _stop_timer(self):
        if self._suspended_timer: self._suspended_timer.cancel()
        self._suspended_timer = None
