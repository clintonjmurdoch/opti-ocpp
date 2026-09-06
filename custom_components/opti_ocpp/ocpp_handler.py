import asyncio
import logging
from datetime import datetime, timezone
import random
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, RegistrationStatus, AuthorizationStatus, ResetType

_LOGGER = logging.getLogger(__name__)

# --- Library Case Normalization ---
if not hasattr(Action, 'meter_values'): Action.meter_values = Action.MeterValues
if not hasattr(Action, 'status_notification'): Action.status_notification = Action.StatusNotification
if not hasattr(Action, 'boot_notification'): Action.boot_notification = Action.BootNotification
if not hasattr(Action, 'heartbeat'): Action.heartbeat = Action.Heartbeat
if not hasattr(Action, 'authorize'): Action.authorize = Action.Authorize
if not hasattr(Action, 'start_transaction'): Action.start_transaction = Action.StartTransaction
if not hasattr(Action, 'stop_transaction'): Action.stop_transaction = Action.StopTransaction
if not hasattr(Action, 'trigger_message'): Action.trigger_message = Action.TriggerMessage

class OptiOcppHandler(cp):
    def __init__(self, id, connection, on_status_change=None, on_transaction_start=None, on_meter_values=None, initial_tid=None):
        super().__init__(id, connection)
        self.status = "Disconnected"
        self.active_transaction_id = initial_tid
        self.phase_count = 3
        self._on_status_change = on_status_change
        self._on_transaction_start = on_transaction_start
        self._on_meter_values = on_meter_values

    @on(Action.BootNotification)
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        if "7" in charge_point_model and "22" not in charge_point_model: self.phase_count = 1
        return call_result.BootNotificationPayload(current_time=datetime.now(timezone.utc).isoformat(), interval=30, status=RegistrationStatus.accepted)

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
        return call_result.StatusNotificationPayload()

    @on(Action.StartTransaction)
    async def on_start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        tid = 1234
        self.active_transaction_id = tid
        if self._on_transaction_start:
            await self._on_transaction_start(self.id, tid)
        return call_result.StartTransactionPayload(transaction_id=tid, id_tag_info={'status': AuthorizationStatus.accepted})

    @on(Action.StopTransaction)
    async def on_stop_transaction(self, meter_stop, timestamp, transaction_id, **kwargs):
        self.active_transaction_id = None
        if self._on_transaction_start:
            await self._on_transaction_start(self.id, None)
        return call_result.StopTransactionPayload()

    @on(Action.MeterValues)
    async def on_meter_values(self, connector_id, meter_value, transaction_id=None, **kwargs):
        try:
            if transaction_id and self.active_transaction_id != transaction_id:
                self.active_transaction_id = transaction_id
                if self._on_transaction_start: await self._on_transaction_start(self.id, transaction_id)

            if self._on_meter_values:
                data = {}
                for mv in meter_value:
                    # Robust attribute access
                    sv_list = getattr(mv, 'sampled_value', []) if not isinstance(mv, dict) else mv.get('sampledValue', [])
                    for sv in sv_list:
                        meas = getattr(sv, 'measurand', 'Energy.Active.Import.Register') if not isinstance(sv, dict) else sv.get('measurand')
                        phase = getattr(sv, 'phase', None) if not isinstance(sv, dict) else sv.get('phase')
                        val = getattr(sv, 'value', None) if not isinstance(sv, dict) else sv.get('value')
                        if val is not None:
                            key = f"{meas}_{phase}" if phase else meas
                            data[key] = val
                if data: await self._on_meter_values(self.id, data)
        except Exception as e:
            _LOGGER.error(f"MeterValues parsing error: {e}")
        return call_result.MeterValuesPayload()

    async def initialise(self, limit):
        opts = {'TxBeforeAcceptedEnabled': 'true', 'AuthorizeRemoteTxRequests': 'false', 'StopTransactionOnInvalidId': 'false', 'UnlockConnectorOnEVSideDisconnect': 'false'}
        for k, v in opts.items():
            try: await self.call(call.ChangeConfigurationPayload(key=k, value=v))
            except Exception: pass
        await self.set_profile("TxDefaultProfile", limit, 1, 1)
        try:
            await self.call(call.TriggerMessagePayload(requested_message='StatusNotification', connector_id=1))
            await self.call(call.TriggerMessagePayload(requested_message='MeterValues', connector_id=1))
        except Exception: pass

    async def set_profile(self, purpose, amps, conn=1, stack=20):
        id_map = {'ChargePointMaxProfile': 100, 'TxDefaultProfile': 200, 'TxProfile': 300}
        prof = {
            'chargingProfileId': id_map.get(purpose, 999),
            'stackLevel': stack,
            'chargingProfilePurpose': purpose,
            'chargingProfileKind': 'Relative',
            'chargingSchedule': {'chargingRateUnit': 'A', 'chargingSchedulePeriod': [{'startPeriod':0, 'limit':float(amps), 'numberPhases':self.phase_count}]}
        }
        if purpose == "TxProfile" and self.active_transaction_id: prof['transactionId'] = self.active_transaction_id
        return await self.call(call.SetChargingProfilePayload(connector_id=conn, cs_charging_profiles=prof))

    async def start_charge(self):
        return await self.call(call.RemoteStartTransactionPayload(id_tag='PLUG_PLAY_IDTAG', connector_id=1))

    async def stop_charge(self):
        return await self.call(call.RemoteStopTransactionPayload(transaction_id=self.active_transaction_id or 1234))
