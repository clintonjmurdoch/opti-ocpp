# SEVR Opti OCPP Home Assistant Integration

A high-performance, specialized Home Assistant integration for **SEVR Opti** EV chargers. This integration provides a robust implementation of the OCPP 1.6J protocol, specifically tuned for maximum stability and responsiveness.

## Why this integration?

Generic OCPP implementations often struggle with specific charger hardware quirks, particularly regarding handshake timing and firmware-level constraints. This integration addresses these issues by enforcing optimal configuration and prioritizing transaction-level control.

## Key Features

### 1. Auto-Stabilization on Connection
Every time the charger connects to the Home Assistant WebSocket server, the integration automatically enforces the following "Golden Configuration" to ensure a reliable handshake:

- **`TxBeforeAcceptedEnabled`**: Set to `true`. This enables "Speed Mode," allowing power to flow immediately after physical relay engagement.
- **`AuthorizeRemoteTxRequests`**: Set to `false`. Bypasses unnecessary remote authorization steps for faster session starts.
- **`UnlockConnectorOnEVSideDisconnect`**: Set to `false`.

Additionally, the integration proactively requests a **Status Notification** and **Meter Values** immediately upon connection to ensure Home Assistant reflects the charger's true state after a restart.

### 2. Intelligent Profile Management
The integration manages charging limits across multiple levels to ensure the car receives the correct amperage without conflicts:

- **Baseline Policy (`TxDefaultProfile`)**: On every connection, a default profile is pushed at **Stack Level 1** using your configured default limit. This acts as the fallback policy for the charger.
- **High-Priority Override (`TxProfile`)**: When a charging transaction commences, the integration automatically pushes a transaction-level profile at **Stack Level 20**. This "Highest Priority" slot ensures that the limit set in Home Assistant overrides any other internal charger settings.
- **Dynamic Phasing**: Automatically detects if the charger is a Single-Phase (7kW) or 3-Phase (22kW) model and adjusts the charging schedules (`numberPhases`) accordingly.

### 3. Smart Dashboard Entities
- **Charge Switch**: A robust toggle to start and stop sessions. It reflects the live `Charging` status and remains available even after Home Assistant restarts.
- **Limit Slider**: A numeric entity (6A - 32A) to control the active transaction limit.
    - **Debounced**: Amperage updates are delayed by 500ms while sliding to protect the charger firmware from command flooding.
    - **Auto-Reset**: The slider automatically snaps back to your configured default limit once a session is complete (`Available`, `Preparing`, or `Finishing`).

### 4. Full Telemetry & Diagnostics
Includes real-time sensors mapped from `MeterValues`:
- Total Energy (Wh)
- Active Power (W) - Total and per phase (L1, L2, L3).
- Voltage (V) - Per phase.
- Current (A) - Per phase.

## Installation

### Via HACS (Recommended)
1. Ensure [HACS](https://hacs.xyz/) is installed.
2. Go to HACS > Integrations.
3. Click the three dots (top right) > **Custom repositories**.
4. Paste the URL of this GitHub repository.
5. Select **Integration** as the category and click **Add**.
6. Find **SEVR Opti OCPP** in the HACS list and click **Download**.
7. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **SEVR Opti OCPP**.
3. Enter your:
   - **Charger ID**: Must match the ID in your charger's settings (e.g., `charger`).
   - **Port**: Usually `9000`.
   - **Default Limit**: The amperage to set automatically as the baseline policy (e.g., `6`).

### Charger Settings
Log into your SEVR Opti web interface and set the OCPP Central System URL to:
`ws://<YOUR_HOME_ASSISTANT_IP>:9000/<chargerid>`

## License
This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
