# BACnet Bounty — Architecture & Scope

**Version:** 1.0
**Date:** April 14, 2026
**Owner:** Jake Klein, Metro Controls
**Status:** Approved for Claude Code implementation

---

## 1. Purpose

BACnet Bounty produces a **portable BACnet/IP simulation bundle** that emulates a small commercial building's device network. The simulator is packaged as a zip and handed off to a co-worker, who runs it on his own Windows machine and integrates the simulated devices into a local Tridium Niagara JACE station. The JACE then drives Reflow-based analytical dashboards (Degree Days, Energy Usage over time, end-use breakdown, etc.) for a customer-facing demo.

The simulator's job ends at the BACnet wire. All dashboards, histories, and analytics live downstream in Niagara.

## 2. Product boundary

**In scope:**
- A Python-based BACnet/IP simulator that presents a plausible building's devices to the network
- Steady-state operation with realistic daily/seasonal value patterns on all points
- A single JSON config file driving all site parameters
- A zip-shipped run experience: unzip → edit config → run.bat → devices appear on BACnet
- Clear README targeted at a controls technician with Claude Code assistance available

**Out of scope (and will stay out of scope):**
- Scripted events, scenarios, demand-response storylines (different product)
- Dashboard rendering of any kind
- Level-2 or Level-3 physical coupling beyond what's needed for metering internal consistency
- Historical trend generation (Niagara extends histories from present-values)
- Installer (.exe, Inno Setup) — ship as zip
- Any GUI — config file + console output only

## 3. Target building

**32,000 sf suburban Michigan office building, single-story.**

- **AHU-1** — single-zone packaged RTU serving ~4,000 sf common area (lobby / training room / conference). DX cooling, gas HW coil heat.
- **AHU-2, AHU-3** — VAV rooftops, each serving ~14,000 sf of office space with 10 VAV zones. DX cooling, gas HW preheat and reheat.
- **VAV_1–VAV_10** fed from AHU-2. **VAV_11–VAV_20** fed from AHU-3.
- Gas-fired hot water boiler implied upstream (not modeled as a BACnet device per scope decision).
- Domestic water only — no irrigation, no cooling tower.
- Occupancy: M–F 7am–6pm, light Saturday 8am–2pm, closed Sunday.
- Design cooling load: ~100 tons total (~30 tons per AHU avg)
- Design heating load: ~1.5 MMBtu/h total
- Electrical service: 800A @ 208V / 3-phase (building-wide)

## 4. Device network

**26 BACnet/IP devices total:**

| Category | Count | Notes |
|---|---|---|
| Electrical meters (E-Mon D-Mon Class 3200) | 3 | Meter A / B / C, all 43 BACnet AIs each |
| Gas meter (ONICON F-5500) | 1 | Rate + totalizer |
| Water meter (ONICON F-3500) | 1 | Rate + totalizer |
| AHUs | 3 | AHU_1 (single-zone), AHU_2 + AHU_3 (VAV) |
| VAV boxes | 20 | VAV_1–VAV_20, each with reheat |

**Metering scope nesting (hard invariant):**
- `Electrical Meter A` (building-wide) ≥ `Electrical Meter B` (AHU_2 + AHU_3 + all VAVs) ≥ `Electrical Meter C` (AHU_2 + AHU_3 fans/equipment only)
- All three kW values computed bottom-up from device-level kW draws so nesting holds at every 10-second tick.
- All three kWh totalizers are independent integrals of their own kW.

## 5. Network architecture

**BACnet/IP with one IP address per device.** Shared ports on a single IP is not supported (hard rule — Niagara discovery breaks).

- Target deployment: **Microsoft KM-TEST Loopback adapter** with 10+ static IPs assigned.
- Config file specifies `base_ip` (e.g. `"192.168.100."`) and `start_octet` (e.g. `200`).
- Simulator binds device N to `{base_ip}{start_octet + N}`, port 47808, in device-instance order.
- **Co-worker responsibility:** ensure the loopback adapter has the required IP range assigned before starting the simulator, and that the JACE BACnet network is bound to the same adapter (or bridged appropriately).
- README will include the `netsh interface ipv4 add address` commands as a reference.

## 6. Simulation model (steady-state, Level 1)

**All points update every 10 seconds.**

- **OAT** is the spine — driven from a Michigan state-average monthly high/low table, sinusoidal diurnal interpolation, ±1–2°F random walk on top. Everything thermal hangs off OAT.
- **Occupancy schedule** drives lighting, plug loads, HVAC mode, VAV setpoints.
- **Space temps** track setpoint with bounded drift; VAV damper and reheat valve respond to the space-temp-vs-setpoint error with proportional logic (no PID tuning, no loop time constants).
- **Equipment kW** computed from fan/pump state + VFD speed + nominal kW rating, with small random noise.
- **Lighting kW** tracks lighting schedule with small noise.
- **Plug kW** tracks occupancy with small noise plus a small 24/7 baseline.
- **Electric meters** sum the underlying device kW into their nested scopes, plus kWh totalizers integrate.
- **Gas consumption** tracks heating load (AHU preheat + VAV reheat valve positions as a proxy).
- **Water consumption** tracks occupancy as a simple weekday/weekend pattern with noise.

**Level-2 couplings present** (by earlier decision):
- kWh = ∫kW dt for every electric meter (and per-phase kW where applicable)
- Therms = ∫(SCFH × heat content) dt for gas
- Gallons = ∫GPM dt for water
- Meter A ≥ Meter B ≥ Meter C at every tick

All other couplings are Level 1 (plausible-looking, not physically derived).

## 7. Magnitudes target

**±20% of realistic values for a 32,000 sf Michigan office**, sourced from ASHRAE 90.1 baseline EUIs, CBECS Midwest office data, and standard lighting power densities. Detailed target ranges in the companion Device & Points Reference document.

Tuning will happen in two passes:
1. **Ship pass** — magnitudes from reference tables, no plotted validation. Good enough for co-worker to begin Niagara integration.
2. **Tuning pass** — once 2–3 days of history exist in Niagara, adjust config constants to tighten realism. This is a follow-up session, not blocking for ship.

## 8. Packaging & runtime

**Ship format:** zip file, delivered to co-worker.

**Contents:**
```
bacnet_bounty/
├── run.bat                     # Entry point (double-click)
├── site_config.json            # All tunables
├── requirements.txt            # Pinned dependencies
├── README.md                   # Co-worker-facing setup guide
├── logs/                       # Created at runtime
└── simulator/                  # Python package
    ├── __main__.py
    ├── devices/
    ├── models/
    └── ...
```

**Runtime requirements (co-worker's machine):**
- Windows 10 or 11
- Python 3.12 installed (via `winget install Python.Python.3.12` if absent)
- Microsoft KM-TEST Loopback adapter installed with static IP range assigned
- JACE accessible on the same network (local or bridged)

**Startup flow:**
1. Co-worker unzips bundle
2. Edits `site_config.json` — sets `base_ip` and `start_octet` to match his loopback range
3. Double-clicks `run.bat`
4. `run.bat` creates venv if missing, installs requirements, runs `python -m simulator`
5. Console shows device-by-device startup, then tick heartbeat
6. Devices discoverable from JACE via Who-Is

## 9. Logging

- **Console output:** INFO level — startup banner, device list with IPs, one-line status ping every 60 seconds
- **File log:** `./logs/simulator.log`, DEBUG level, rotates daily, 7-day retention
- No config toggle — always on. If something breaks, co-worker zips the logs and sends them back.

## 10. Delivery plan

**Phase 1 (end of this week): Ship the zip.**
- Full device list on BACnet with all points discoverable
- Steady-state values on all points, magnitudes from reference tables
- Co-worker begins Niagara integration and dashboard build

**Phase 2 (parallel to Phase 1 integration work): Tuning.**
- Claude Code or Jake adjusts magnitudes based on plotted Reflow trends
- Config file changes only — no code rewrites
- Delivered as updated config, co-worker drops it in

## 11. Division of labor

- **Web Claude (design session):** produces this architecture doc + the Device & Points Reference. Source of truth for Claude Code.
- **Claude Code (implementation session):** implements simulator against the spec, runs locally, ships zip.
- **Jake:** spot-checks spec, spot-checks final zip runs clean, hands zip to co-worker.
- **Co-worker:** runs zip, does Niagara integration, builds dashboards. Out of scope for this project.

**Cross-AI handoff rule:** the two spec docs are the source of truth. Claude Code works from them directly. If ambiguity surfaces, Claude Code flags it back to Jake, Jake brings the question to web Claude with the spec as context. No copy-pasting of mid-stream artifacts between sessions.

## 12. Open items (none blocking)

- Tuning pass magnitudes — deferred to Phase 2.
- Co-worker's specific loopback IP range — set in config at deploy time.
- JACE network binding to loopback — co-worker's responsibility, noted in README.
