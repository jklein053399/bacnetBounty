# BACnet Bounty — Device & Points Reference

**Version:** 1.0
**Date:** April 14, 2026
**Companion to:** `01_BACnet_Bounty_Architecture_and_Scope.md`
**Audience:** Claude Code (implementation), Jake (review)

---

## 1. Device manifest

26 BACnet/IP devices total. Each device gets its own IP on port 47808.

| Device Name | Device Instance | IP Offset | Type | Vendor / Model |
|---|---|---|---|---|
| Electrical Meter A | 100 | 0 | Electric meter (building-wide) | E-Mon / Class 3200 |
| Electrical Meter B | 101 | 1 | Electric meter (AHU_2+3 + VAVs) | E-Mon / Class 3200 |
| Electrical Meter C | 102 | 2 | Electric meter (AHU_2+3 only) | E-Mon / Class 3200 |
| Gas Meter | 110 | 3 | Gas meter | ONICON / F-5500 |
| Water Meter | 120 | 4 | Water meter | ONICON / F-3500 |
| AHU_1 | 200 | 5 | Single-zone RTU | (generic) |
| AHU_2 | 201 | 6 | VAV RTU | (generic) |
| AHU_3 | 202 | 7 | VAV RTU | (generic) |
| VAV_1 | 301 | 8 | VAV w/ reheat (under AHU_2) | (generic) |
| VAV_2 | 302 | 9 | VAV w/ reheat (under AHU_2) | (generic) |
| ... | ... | ... | ... | ... |
| VAV_10 | 310 | 17 | VAV w/ reheat (under AHU_2) | (generic) |
| VAV_11 | 311 | 18 | VAV w/ reheat (under AHU_3) | (generic) |
| ... | ... | ... | ... | ... |
| VAV_20 | 320 | 27 | VAV w/ reheat (under AHU_3) | (generic) |

IP assignment: `{base_ip}{start_octet + IP Offset}`.
Example with `base_ip="192.168.100."` and `start_octet=200`: Electrical Meter A = 192.168.100.200, VAV_20 = 192.168.100.227.

Loopback adapter must have at least 28 IPs assigned in that contiguous range.

## 2. E-Mon Class 3200 electrical meters (x3)

All three meters expose the **full 43 BACnet Analog Input objects** per the Class 3200 BACnet Protocol Definitions (PDF Section 12). This matches what a real E-Mon Class 3200 exposes on BACnet/IP, so Niagara discovery sees an authentic device.

### Device object metadata

| Property | Value |
|---|---|
| Vendor Name | `E-Mon` |
| Vendor Identifier | `224` *(E-Mon's registered BACnet vendor ID — verify with BACnet Vendor ID list at implementation)* |
| Model Name | `Class 3200` |
| Firmware Revision | `4.11` |
| Application Software Version | `4.11` |
| Protocol Version | `1` |
| Protocol Revision | `14` |
| Segmentation Supported | `segmented-both` |

### Point list (43 Analog Inputs per meter)

Object IDs follow the PDF Section 12 table (AI 1 through AI 43). Descriptions and units taken directly from E-Mon documentation.

| AI # | Name | Units | Simulated? |
|---|---|---|---|
| 1 | Energy delivered | kWh | **Primary** (∫kW) |
| 2 | Energy received | kWh | Stub (hold 0) |
| 3 | Reactive energy delivered | kVARh | Derived (∫kVAR) |
| 4 | Reactive energy received | kVARh | Stub (hold 0) |
| 5 | Real power | kW | **Primary** |
| 6 | Reactive power | kVAR | Derived (kW × tan(acos(PF))) |
| 7 | Apparent power | kVA | Derived (kW / PF) |
| 8 | Power factor | % | **Primary** (~0.92 ± 0.02 jitter) |
| 9 | Peak demand | kW | Running 15-min max of real power |
| 10 | Current average | Amps | Derived (kW / (V × √3 × PF × 1000)) |
| 11 | Voltage L-N | Volts | **Primary** (~120 ± 1) |
| 12 | Voltage L-L | Volts | Derived (V_LN × √3) |
| 13 | Frequency | Hz | Constant 60.0 ± 0.02 jitter |
| 14 | Phase angle | Degrees | Constant 0 ± 0.5 jitter |
| 15–17 | Real power phase A/B/C | kW | Primary kW / 3 ± 3% imbalance jitter |
| 18–20 | Reactive power phase A/B/C | kVAR | Derived from per-phase kW & PF |
| 21–23 | Apparent power phase A/B/C | kVA | Derived from per-phase kW & PF |
| 24–26 | Power factor phase A/B/C | % | Building PF ± small jitter |
| 27–29 | Current phase A/B/C | Amps | Derived per phase |
| 30–32 | Voltage L-N phase A-N/B-N/C-N | Volts | 120 ± small jitter each |
| 33–35 | Voltage L-L phase A-B/B-C/C-A | Volts | Derived |
| 36–38 | Phase angle A/B/C | Degrees | 0 / -120 / +120 ± 0.5 jitter |
| 39–41 | Reserve A/B/C | — | Stub (hold 0) |
| 42 | External Input 1 | Pulse | Stub (hold 0) |
| 43 | External Input 2 | Pulse | Stub (hold 0) |

**"Primary"** = value is directly computed from the building model.
**"Derived"** = value falls out of a primary via known relationship.
**"Stub"** = hold a constant, for discovery completeness only.

### Meter scope & magnitudes

| Meter | Scope | Peak kW (summer design) | Baseline kW (unoccupied night) | Annual kWh (ballpark) |
|---|---|---|---|---|
| A | Building-wide | 110 kW | 15 kW | ~350,000 |
| B | AHU_2+3 + VAV_1–20 | 55 kW | 3 kW | ~130,000 |
| C | AHU_2+3 only | 35 kW | 2 kW | ~85,000 |

Source: ASHRAE 90.1 baseline EUI ~55 kBtu/sf/yr × 32,000 sf × electric-only fraction ~60% = ~300 MWh/yr; HVAC fraction ~40% of building electric = ~130 MWh/yr. Matches CBECS Midwest small office.

**Invariant check (every 10-sec tick):**
```
kW_A >= kW_B >= kW_C
```
Implementation: compute C bottom-up from AHU_2 + AHU_3 fan/equipment kW. Compute B as C + Σ(VAV fan + reheat energy proxy). Compute A as B + AHU_1 kW + lighting kW + plug kW.

## 3. ONICON F-5500 gas meter

### Device object metadata

| Property | Value |
|---|---|
| Vendor Name | `ONICON Incorporated` |
| Vendor Identifier | `194` *(ONICON's registered BACnet vendor ID — verify at implementation)* |
| Model Name | `F-5500` |
| Firmware Revision | `2.10` |

### Point list (3 Analog Inputs)

| AI # | Name | Units | Notes |
|---|---|---|---|
| 1 | Flow Rate | SCFH | **Primary** — driven by heating load proxy |
| 2 | Totalizer | SCF | ∫(SCFH) dt |
| 3 | Gas Temperature | °F | OAT ± small offset (pipe reads near ambient) |

### Magnitudes

- **Peak winter SCFH**: ~3,000 SCFH (design heating day, boiler firing hard)
- **Summer SCFH**: ~100 SCFH (pilot + DHW only — but DHW not separately modeled, so just pilot baseline)
- **Annual consumption**: ~5,000 therms (~500,000 SCF) for 32,000 sf Michigan office
- **Model**: heating_load_fraction × peak_SCFH + baseline, where heating_load_fraction derives from (1 - OAT/60°F) clamped to [0, 1] during occupied hours + VAV reheat valve position average.

Therms conversion (for Reflow dashboard math): 1 therm = 100,000 BTU ≈ 97 SCF at standard heat content. Niagara will typically compute this from SCFH, but if Jake wants a pre-computed therms/hr point, flag for Phase 2.

## 4. ONICON F-3500 water meter

### Device object metadata

| Property | Value |
|---|---|
| Vendor Name | `ONICON Incorporated` |
| Vendor Identifier | `194` |
| Model Name | `F-3500` |
| Firmware Revision | `3.05` |

### Point list (3 Analog Inputs)

| AI # | Name | Units | Notes |
|---|---|---|---|
| 1 | Flow Rate | GPM | **Primary** — driven by occupancy |
| 2 | Totalizer | Gallons | ∫(GPM) dt |
| 3 | Water Temperature | °F | Constant ~55°F (domestic cold) ± small jitter |

### Magnitudes

- **Peak occupied GPM**: ~8 GPM (lunch hour, restrooms active)
- **Average occupied GPM**: ~2 GPM
- **Unoccupied GPM**: ~0.05 GPM (leak-level trickle)
- **Annual consumption**: ~80,000 gallons for 32,000 sf office
- **Model**: occupancy_fraction × peak_GPM + unoccupied_baseline, with Poisson-style bursts every few minutes during occupied hours to simulate flush events.

## 5. AHU devices (x3)

All three AHUs share a common point list. AHU_1 is single-zone (no VAV downstream); AHU_2 and AHU_3 are VAV with 10 boxes each.

### Device object metadata (all AHUs)

| Property | Value |
|---|---|
| Vendor Name | `Metro Controls` |
| Model Name | `AHU-Sim` |
| Firmware Revision | `1.0` |

### Point list per AHU (~18 points)

| Obj Type | Obj ID | Name | Units | Notes |
|---|---|---|---|---|
| AI | 1 | Supply Air Temperature | °F | Setpoint ± drift |
| AI | 2 | Return Air Temperature | °F | Mixed from zone avg |
| AI | 3 | Mixed Air Temperature | °F | Blend of RA and OA by damper pos |
| AI | 4 | Outside Air Temperature | °F | Mirror of site OAT |
| AI | 5 | Supply Air Static Pressure | in WC | ~1.5 (VAV), 0.5 (SZ) ± drift |
| AI | 6 | Supply Air Flow | CFM | Σ VAV CFM (VAV units) or design CFM (SZ) |
| AI | 7 | Filter Differential Pressure | in WC | 0.3 ± slow seasonal drift |
| AI | 8 | AHU Real Power | kW | **Primary** — fan + aux equipment draw |
| AV | 1 | Supply Air Temp Setpoint | °F | 55°F cooling / 65°F heating schedule |
| AV | 2 | Supply Static Pressure Setpoint | in WC | 1.5 VAV / 0.5 SZ |
| BI | 1 | Fan Status | — | Follows fan command with 3-sec delay |
| BI | 2 | Filter Alarm | — | 0 (stub; flip if filter DP > threshold) |
| BO | 1 | Fan Start/Stop | — | Occupancy schedule |
| AO | 1 | Fan VFD Speed Command | % | PI-like tracking to static pressure (VAV) / 100% (SZ) |
| AO | 2 | OA Damper Position | % | Min position when occupied, economizer when OAT allows |
| AO | 3 | Heating Valve Position | % | Tracks SA temp vs setpoint in heating mode |
| AO | 4 | Cooling Stage / DX Status | % or stages | Tracks SA temp vs setpoint in cooling mode |

### Magnitudes

| Point | AHU_1 (SZ, ~4000 sf) | AHU_2 / AHU_3 (VAV, ~14000 sf each) |
|---|---|---|
| Fan motor nominal | 3 HP (~2.5 kW at 100%) | 10 HP (~8 kW at 100%) |
| Design CFM | 1,600 | 5,600 |
| Cooling capacity | ~12 tons DX | ~40 tons DX |
| Typical occupied kW | 2–4 kW | 5–12 kW |
| Unoccupied kW | 0 (fan off) | 0.5 kW (standby) |

Fan kW model: `fan_kW = nominal_kW × (VFD_speed/100)^2.5` (affinity-law approximation). Good enough for Level 1.

## 6. VAV devices (x20)

VAV_1–VAV_10 fed from AHU_2. VAV_11–VAV_20 fed from AHU_3.

### Device object metadata

| Property | Value |
|---|---|
| Vendor Name | `Metro Controls` |
| Model Name | `VAV-Sim` |
| Firmware Revision | `1.0` |

### Point list per VAV (~8 points)

| Obj Type | Obj ID | Name | Units | Notes |
|---|---|---|---|---|
| AI | 1 | Zone Temperature | °F | **Primary** — drifts around setpoint |
| AI | 2 | Supply Airflow | CFM | Tracks airflow setpoint via damper |
| AI | 3 | Discharge Air Temperature | °F | SA temp + reheat delta (when reheat active) |
| AV | 1 | Occupied Cooling Setpoint | °F | 74°F default |
| AV | 2 | Occupied Heating Setpoint | °F | 70°F default |
| AV | 3 | Airflow Setpoint | CFM | Varies with zone cooling/heating demand |
| AO | 1 | Damper Position | % | Tracks airflow SP |
| AO | 2 | Reheat Valve Position | % | Tracks zone temp below heating SP |
| BI | 1 | Occupancy Status | — | From site occupancy schedule |

### Magnitudes per VAV

- **Design airflow**: 500 CFM (office zone avg)
- **Min airflow**: 150 CFM (30% of design, typical VAV min)
- **Reheat coil capacity**: 15 MBH each

## 7. Site-level simulation inputs

These aren't BACnet points but drive everything on the BACnet network. Defined in `site_config.json`.

### OAT model

Michigan monthly averages (Detroit metro, NOAA normals):

| Month | Avg High °F | Avg Low °F |
|---|---|---|
| Jan | 32 | 19 |
| Feb | 35 | 21 |
| Mar | 45 | 28 |
| Apr | 58 | 38 |
| May | 70 | 48 |
| Jun | 79 | 58 |
| Jul | 83 | 63 |
| Aug | 81 | 62 |
| Sep | 74 | 54 |
| Oct | 61 | 42 |
| Nov | 49 | 33 |
| Dec | 36 | 24 |

Interpolate between months over day-of-year. Diurnal: sinusoid with low at 5 AM local, high at 3 PM local. Random walk: ±1.5°F bounded.

### Occupancy schedule

| Day | Occupied | Fraction of peak |
|---|---|---|
| Mon–Fri | 7:00 AM – 6:00 PM | Ramp 0→1 over 7–9 AM; 1.0 flat 9 AM–5 PM; ramp 1→0 over 5–6 PM |
| Saturday | 8:00 AM – 2:00 PM | 0.3 peak |
| Sunday | Closed | 0.05 baseline (security, always-on loads) |

### Lighting and plug loads

- **Lighting density**: 0.9 W/sf × 32,000 sf = ~29 kW at 100% lit.
- **Lighting schedule**: on at 6 AM, off at 10 PM weekdays; Saturday 7 AM–3 PM; Sunday off (security only, ~2 kW baseline).
- **Plug load density**: 0.75 W/sf × 32,000 sf = ~24 kW at full occupancy.
- **Plug load profile**: follows occupancy fraction × peak, plus always-on baseline of 3 kW (servers, printers, phantom loads).

## 8. Config file schema (`site_config.json`)

```json
{
  "site": {
    "name": "32K Michigan Office Demo",
    "square_feet": 32000,
    "location": "Detroit, MI",
    "timezone": "America/Detroit"
  },
  "network": {
    "base_ip": "192.168.100.",
    "start_octet": 200,
    "bacnet_port": 47808
  },
  "simulation": {
    "tick_interval_seconds": 10,
    "noise_scale": 1.0
  },
  "magnitudes": {
    "building_peak_kw": 110,
    "building_baseline_kw": 15,
    "ahu_vav_peak_kw_each": 12,
    "ahu_sz_peak_kw": 4,
    "lighting_peak_kw": 29,
    "plug_peak_kw": 24,
    "plug_baseline_kw": 3,
    "gas_peak_scfh": 3000,
    "gas_baseline_scfh": 100,
    "water_peak_gpm": 8,
    "water_baseline_gpm": 0.05,
    "voltage_nominal": 208,
    "voltage_phase_nominal": 120,
    "power_factor_nominal": 0.92
  },
  "schedule": {
    "occupied_weekday_start": "07:00",
    "occupied_weekday_end": "18:00",
    "ramp_up_hours": 2,
    "ramp_down_hours": 1,
    "saturday_peak_fraction": 0.3,
    "sunday_baseline_fraction": 0.05,
    "cooling_setpoint_occupied": 74,
    "heating_setpoint_occupied": 70,
    "cooling_setpoint_unoccupied": 82,
    "heating_setpoint_unoccupied": 60
  },
  "weather": {
    "location": "Detroit_MI",
    "monthly_high_low_f": [
      [32, 19], [35, 21], [45, 28], [58, 38], [70, 48], [79, 58],
      [83, 63], [81, 62], [74, 54], [61, 42], [49, 33], [36, 24]
    ],
    "diurnal_peak_hour": 15,
    "diurnal_trough_hour": 5,
    "random_walk_bound_f": 1.5
  },
  "logging": {
    "console_level": "INFO",
    "file_level": "DEBUG",
    "log_dir": "./logs",
    "rotate_daily": true,
    "retention_days": 7
  }
}
```

## 9. Dependencies

Pinned in `requirements.txt`. Target Python 3.12.

| Package | Version | Purpose |
|---|---|---|
| `bacpypes3` | latest stable as of implementation | BACnet/IP stack |
| (stdlib) `json`, `logging`, `asyncio`, `math`, `datetime`, `random` | — | Core logic |

No numpy, no pandas, no external deps beyond bacpypes3. Keep the zip small and the install fast.

## 10. Acceptance checklist (Phase 1 ship)

- [ ] Zip unzips cleanly to any folder
- [ ] `run.bat` creates venv, installs deps, starts simulator on first run
- [ ] Console shows all 26 devices binding to their IPs on startup
- [ ] `bacpypes3` responds to Who-Is with I-Am for all 26 devices
- [ ] All 43 AIs on each E-Mon readable via BACnet ReadProperty
- [ ] All AHU, VAV, gas, water points readable
- [ ] Values update every 10 seconds (observable on repeated reads)
- [ ] Meter nesting invariant holds: kW_A ≥ kW_B ≥ kW_C at all observed ticks
- [ ] kWh totalizers increase monotonically and match ∫kW over a 10-minute observation
- [ ] Log file created at `./logs/simulator.log`
- [ ] README allows a controls tech with Claude Code to run the sim without asking Jake

## 11. Known deferred items

- Vendor IDs for E-Mon and ONICON — verify against ASHRAE BACnet Vendor ID list at implementation. Placeholders in this doc.
- Phase 2 tuning — after co-worker has 2–3 days of history, revisit magnitudes config.
- Boiler device — not modeled. Heating visible only through gas meter and VAV reheat valve positions. If co-worker needs a boiler device for the dashboard story, add in Phase 2.
- Historical backfill — not in scope. Niagara extends histories from present-values going forward.
