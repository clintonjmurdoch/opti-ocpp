# SEVR Opti OCPP Home Assistant Integration

This custom integration provides a robust OCPP 1.6J interface specifically optimized for the **SEVR Opti** EV charger and the **Jaecoo J5 EV** (and other Chery-platform EVs like the Omoda E5).

## Why this integration exists

The standard Home Assistant OCPP integration often struggles with the SEVR Opti / Jaecoo J5 combination because:
1. **Handshake Timing**: The Jaecoo J5 is sensitive to the delay between physical relay engagement and power flow. 
2. **SuspendedEV Status**: The car often reports `SuspendedEV` for a split second during handshake, which many servers interpret as a failure.
3. **Phasing Requirements**: The Opti charger and Jaecoo J5 require explicit 3-phase declarations in charging profiles that standard integrations may omit.

## Key Features

- **Auto-Handshake**: Automatically configures the charger for "Speed Mode" (`TxBeforeAcceptedEnabled`) and "Relaxed Rules" (`AuthorizeRemoteTxRequests: false`) on every connection.
- **Persistent Transactions**: Saves the active Transaction ID to disk. If Home Assistant restarts or your server sleeps, you still maintain control over the current charge session.
- **Smart Suspension Handling**: Gracefully waits for up to 30 seconds if the car enters `SuspendedEV` state before auto-cancelling.
- **3-Phase Limit Control**: The included slider entity correctly pushes 3-phase `TxProfile` updates to the car in real-time.
- **Headless Operation**: Designed to be the "set and forget" gateway for your garage.

## Installation

### Via HACS (Recommended)
1. Ensure [HACS](https://hacs.xyz/) is installed.
2. Go to HACS > Integrations.
3. Click the three dots (top right) > **Custom repositories**.
4. Paste the URL of this GitHub repository.
5. Select **Integration** as the category and click **Add**.
6. Find "SEVR Opti OCPP" in the HACS list and click **Download**.
7. Restart Home Assistant.

### Manual
1. Copy the `custom_components/opti_ocpp` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for **SEVR Opti OCPP**.
3. Enter your:
   - **Charger ID**: Must match the ID in your charger's settings (e.g., `charger`).
   - **Port**: Usually `9000`.
   - **Default Limit**: The amperage to set automatically when the charger connects (e.g., `6`).

### Charger Settings
Log into your SEVR Opti web interface and set the OCPP URL to:
`ws://<YOUR_HOME_ASSISTANT_IP>:9000/<chargerid>`

## License
This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
