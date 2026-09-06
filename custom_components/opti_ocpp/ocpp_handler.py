import asyncio
import logging
from datetime import datetime, timezone
import random
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call, call_result
from ocpp.v16.enums import RegistrationStatus, AuthorizationStatus, ResetType

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

    @on('BootNotification')
    async def on_boot_notification(self, charge_point_vendor, charge_point_model, **kwargs):
        if "7" in charge_point_model and "22" not in charge_point_model:
            self.phase_count = 1
        else:
            self.phase_count = 3
        return call_result.BootNotification(current_time=datetime.now(timezone.utc).isoformat(), interval=30, status=RegistrationStatus.accepted)

    @on('Heartbeat')
    async def on_heartbeat(self):
        return call_result.Heartbeat(current_time=datetime.now(timezone.utc).isoformat())

    @on('Authorize')
    async def on_authorize(self, id_tag, **kwargs):
        return call_result.Authorize(id_tag_info={'status': AuthorizationStatus.accepted})

    @on('StatusNotification')
    async def on_status_notification(self, connector_id, status, **kwargs):
        self.status = status
        if self._on_status_change: await self._on_status_change(self.id, status)
        if status == "SuspendedEV": self._start_timer()
        else: self._stop_timer()
        return call_result.StatusNotification()

    @on('StartTransaction')
    async def on_start_transaction(self, **kwargs):
        tid = 1234
        self.active_transaction_id = tid
        if self._on_transaction_start: await self._on_transaction_start(self.id, tid)
        return call_result.StartTransaction(transaction_id=tid, id_tag_info={'status': AuthorizationStatus.accepted})

    @on('StopTransaction')
    async def on_stop_transaction(self, **kwargs):
        self.active_transaction_id = None
        if self._on_transaction_start: await self._on_transaction_start(self.id, None)
        self._stop_timer()
        return call_result.StopTransaction()

    @on('MeterValues')
    async def on_meter_values(self, connector_id, meter_value, transaction_id=None, **kwargs):
        if transaction_id and self.active_transaction_id != transaction_id:
            self.active_transaction_id = transaction_id
            if self._on_transaction_start: await self._on_transaction_start(self.id, transaction_id)

        if self._on_meter_values:
            data = {}
            for mv in meter_value:
                for sv in mv.get('sampled_value', []):
                    measurand = sv.get('measurand', 'Energy.Active.Import.Register')
                    phase = sv.get('phase')
                    val = sv.get('value')

                    key = measurand
                    if phase:
                        key = f"{measurand}_{phase}"

                    data[key] = val
            await self._on_meter_values(self.id, data)

        return call_result.MeterValues()

    # --- Actions ---

    async def initialise(self, limit):
        opts = {'TxBeforeAcceptedEnabled':'true', 'AuthorizeRemoteTxRequests':'false', 'StopTransactionOnInvalidId':'false', 'UnlockConnectorOnEVSideDisconnect':'false'}
        for k, v in opts.items():
            try: await self.call(call.ChangeConfiguration(key=k, value=v))
            except Exception: pass
        await self.set_profile("TxDefaultProfile", limit, 1, 1)

    async def set_profile(self, purpose, amps, conn=1, stack=1):
        id_map = {'ChargePointMaxProfile': 100, 'TxDefaultProfile': 200, 'TxProfile': 300}
        profile_id = id_map.get(purpose, random.randint(1, 9999))

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
        return await self.call(call.SetChargingProfile(connector_id=conn, cs_charging_profiles=prof))

    async def start_charge(self):
        return await self.call(call.RemoteStartTransaction(id_tag='PLUG_PLAY_IDTAG', connector_id=1))

    async def stop_charge(self):
        return await self.call(call.RemoteStopTransaction(transaction_id=self.active_transaction_id or 1234))

    def _start_timer(self):
        self._stop_timer()
        async def kill():
            await asyncio.sleep(30)
            if self.status == "SuspendedEV": await self.stop_charge()
        self._suspended_timer = asyncio.create_task(kill())

    def _stop_timer(self):
        if self._suspended_timer: self._suspended_timer.cancel()
        self._suspended_timer = None
