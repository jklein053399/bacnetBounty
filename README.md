# BACnet Bounty

Portable BACnet/IP simulator for the 32K sf Michigan office demo. Stands up 28 simulated BACnet devices on a Windows loopback adapter so Niagara can discover them and Reflow dashboards can consume the present-values. No physical hardware required.

Ships as a zip. Unzip, set up your loopback IPs, edit one JSON file, double-click `run.bat`. Runs indefinitely until you press Ctrl+C.

---

## What it simulates

28 BACnet/IP devices representing a 32,000 sf suburban Michigan office:

| Device | Count | Role |
|---|---|---|
| E-Mon Class 3200 electrical meter | 3 | Meters A (building), B (HVAC + VAVs), C (HVAC only) |
| ONICON F-5500 gas meter | 1 | AHU preheat gas flow |
| ONICON F-3500 water meter | 1 | Domestic cold water flow |
| AHU (Metro AHU-Sim) | 3 | AHU_1 single-zone, AHU_2/AHU_3 VAV rooftops |
| VAV (Metro VAV-Sim) | 20 | VAV_1–10 under AHU_2, VAV_11–20 under AHU_3 |

All devices present on port 47808 with realistic daily/seasonal patterns. Meter A ≥ Meter B ≥ Meter C is preserved at every tick (10-second intervals). kWh totalizers, gas SCF totalizer, and water gallons totalizer all accumulate from their kW/flow integrals.

---

## Prerequisites

Before you run anything:

1. **Windows 10 or 11** — tested on Windows 11.
2. **Python 3.12 or later** on your PATH. Install from https://www.python.org/downloads/ if missing. Check the "Add Python to PATH" box in the installer.
3. **Microsoft KM-TEST Loopback adapter** installed and enabled. If you don't have one:
   - Open Device Manager → Action menu → **Add legacy hardware** → Next → **Install manually** → Next → **Network adapters** → Next → Manufacturer: **Microsoft** / Model: **Microsoft KM-TEST Loopback Adapter** → Next.
   - In Network Connections, rename the new adapter to something memorable (Jake calls his `Bacnet Simulator`). Use whatever name you like — you'll refer to it by exact name below.
4. **29 contiguous IPs** assigned to that adapter. See "Loopback IP setup" below.

---

## Loopback IP setup (one-time, run as Administrator)

Open an **elevated** Command Prompt (Start → type "cmd" → right-click → Run as administrator), then paste (substitute your adapter name where shown — Jake's test box uses `Bacnet Simulator`):

```cmd
set ADAPTER=Bacnet Simulator
for /l %i in (200,1,228) do netsh interface ipv4 add address name="%ADAPTER%" 192.168.100.%i 255.255.255.0
```

This assigns `192.168.100.200` through `.228` to the adapter. The simulator uses `.200`–`.227` for the 28 devices; `.228` is reserved for your Niagara Workbench / JACE binding — **do not bind the simulator or another BACnet device on `.228`**.

To verify:
```cmd
netsh interface ipv4 show addresses name="Bacnet Simulator"
```

You should see all 29 IPs listed.

**Different network range?** If `192.168.100.x` conflicts with your LAN, edit `site_config.json` `network.base_ip` and `network.start_octet` before running. See "Config" below.

---

## Run

Double-click **`run.bat`**.

On first run:
- It creates a local virtual environment (`.venv/`) next to `run.bat`.
- Installs the single dependency: `BAC0==2025.9.15`.
- Launches the simulator.

Startup takes roughly **one minute** for 28 devices (each device takes ~2 seconds to register with BACnet). You'll see each device print as it comes online. That's normal — **don't close the window during this phase**. The banner will conclude with `28 devices online.` followed by a tick heartbeat every 60 seconds.

Subsequent runs: skips the venv/install step (idempotent), goes straight to launching. Takes ~1 second before device bring-up starts.

---

## Config (`site_config.json`)

Edit this one file to adapt the simulator to your network and site.

- `network.base_ip` — subnet prefix, must end with `.` (e.g. `"192.168.100."`)
- `network.start_octet` — first device IP (e.g. `200` → `.200`)
- `network.bacnet_port` — always `47808`, don't change (Niagara discovery requires it)
- `site.*`, `simulation.*`, `schedule.*`, `weather.*`, `magnitudes.*` — simulation tuning. Safe defaults for a 32K sf Detroit office. Tuning pass (Phase 7) revisits these after Niagara trend data is available.
- `ahus[]`, `vavs[]` — per-device config rows. Edit only if you're adding or removing devices (requires matching changes in `simulator/__main__.py` manifest).

**Changes take effect on next startup.** There's no hot-reload — Ctrl+C to stop, edit, relaunch.

---

## Stop

Press **Ctrl+C** in the console window. Expected sequence:

```
Stop signal received.
Shutting down devices...
Shutdown complete.
Simulator stopped. Press any key to close this window.
```

Takes about 1 second for all 28 devices to disconnect and release their IPs. If you need to verify IPs were released, run:

```cmd
netstat -ano -p udp | findstr :47808
```

Should return no matches after a clean shutdown.

**If Ctrl+C doesn't respond** (shouldn't happen — flag to Jake if it does):
- First try Ctrl+Break (also handled).
- Last resort: close the console window. Windows gives Python ~5 seconds to clean up before hard-terminating. Devices will disconnect but the shutdown log may be truncated.
- If ports stay bound after a hard kill, `taskkill /F /PID <pid>` then wait 30 seconds before restarting.

---

## Long-running operation

The simulator is designed to run indefinitely — days, weeks.

**Expected behavior during soak:**
- **Memory footprint**: steady-state around 100–120 MB after the first hour. If you see it growing past 200 MB after a day, flag to Jake.
- **Log file**: `logs/simulator.log`. Rotates daily at midnight (local time), keeps 7 days of history as `logs/simulator.log.YYYY-MM-DD`. Self-manages — no cleanup needed.
- **Tick heartbeat**: one INFO line per 60 seconds showing OAT, occupancy, Meter A/B/C kW, gas SCFH, water GPM. If you stop seeing these, the process is stuck or crashed.
- **Midnight rollover**: log file rotates seamlessly. Numbers keep ticking. kWh/SCF/gallon totalizers do NOT reset — they accumulate forever (or until Ctrl+C).

**"Is it still working?" quick check** without Jake's help:
1. Tail the log file for a fresh heartbeat: `powershell -command "Get-Content logs\simulator.log -Tail 20"`
2. Confirm you see a recent `tick#N` line timestamped within the last 2 minutes.
3. If you want to poke the wire directly, run a BACnet client (Yabe, bacnet-stack's `readprop`, your JACE) to read `192.168.100.200` device 100001 analogInput 5 presentValue — should return a number between roughly 10 and 200 (kW).

---

## Troubleshooting

**"Port 47808 already in use" / bind errors on startup**
- Another BACnet application is running — close Yabe, Niagara, or whatever.
- Or a previous simulator run didn't exit cleanly. `taskkill /F /IM python.exe`, wait 30 seconds, retry.

**"The requested operation requires elevation" when adding IPs**
- `netsh interface ipv4 add address` requires Administrator. Reopen Command Prompt as Administrator.

**Devices don't appear in Niagara's discovery**
- Confirm Niagara's BACnet network is bound to your loopback adapter's IP range. The adapter must be the network interface the Niagara station is listening on.
- Your Workbench / JACE should bind to `192.168.100.228`. If you're running Soft Station locally, configure its BACnet port to bind to that IP.
- Try a Who-Is broadcast from Niagara — should see all 28 devices reply.

**Log file grows large during soak**
- Rotation fires at midnight. If for some reason it doesn't (clock skew, etc.), delete older `simulator.log.*` files manually.

**Weird non-ASCII characters in console output**
- Cosmetic. The banner uses em-dashes which may render as `?` or `�` on your console code page. Doesn't affect simulation.

**Simulator ran fine, now it won't start**
- 90% of the time: previous Ctrl+C didn't complete cleanly and ports are still bound. `taskkill /F /IM python.exe`, wait 30 seconds, retry.

---

## File layout

```
bacnet-bounty/
├── run.bat                 Double-click to launch
├── README.md               This file
├── site_config.json        All tunables
├── requirements.txt        Single Python dep (BAC0)
├── simulator/              Python package — do not edit unless you're Jake
└── logs/                   Runtime output (created on first run)
```

---

## Getting help

If anything surprising happens, zip up the `logs/` directory and send it to Jake with a description of what you were doing. The `DEBUG`-level file log has the full BAC0 and bacpypes3 trace, which usually tells us what went sideways.

For general BACnet / Niagara questions, ask Jake — the simulator's job ends at the BACnet wire; everything on the JACE side is outside what I built.
