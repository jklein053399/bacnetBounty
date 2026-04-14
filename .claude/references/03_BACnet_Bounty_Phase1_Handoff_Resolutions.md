# BACnet Bounty — Phase 1 Config Resolution & Scaffold Greenlight

**Version:** 1.0
**Date:** April 14, 2026
**Supersedes:** conflicting magnitudes in `01_BACnet_Bounty_Architecture_and_Scope.md` and `02_BACnet_Bounty_Device_and_Points_Reference.md`. Both spec docs remain source of truth for everything not addressed here.
**Status:** Greenlit for Claude Code implementation

---

## Context

Web Claude and Jake reviewed Claude Code's pushback on the two spec docs. All five flags resolved. Vertical slice (config → site_model → one E-Mon → BACnet bring-up) greenlit.

## Resolutions

### Flag 1 — kW magnitude inconsistency (RESOLVED with corrections + calibration)

Per-AHU real power now includes compressor + condenser fans + supply fan + aux. Use ~1.2 kW/ton rule of thumb for packaged DX.

**Corrected base magnitudes (before energy-hog calibration):**
- AHU_1 (single-zone, ~12 tons): ~14 kW peak
- AHU_2, AHU_3 (VAV, ~40 tons each): ~45 kW peak each

**Design decision (not a fix):** VAVs use **electric reheat**, not hot water reheat. Jake picked electric reheat so Meters B and C would have meaningfully different kW.
- Each VAV has up to ~3 kW electric reheat at 100% valve position. 20 VAVs × 3 kW = up to 60 kW additional electric load when cold.
- Gas meter scope shrinks to AHU preheat only. Gas peak drops from ~3,000 SCFH to ~500 SCFH. Annual consumption drops from ~5,000 therms to ~1,000 therms.
- No explicit "Electric Reheat kW" AI per VAV. Reheat valve position (existing AO) × per-VAV max reheat kW is computed at the model layer and rolls up into Meter B's kW.

**Energy-hog calibration:** +20% on everything electric. Final magnitudes for `site_config.json`:

```json
"magnitudes": {
  "building_peak_kw": 200,
  "building_baseline_kw": 22,
  "ahu_vav_peak_kw_each": 55,
  "ahu_sz_peak_kw": 17,
  "vav_reheat_peak_kw_each": 3.6,
  "lighting_peak_kw": 35,
  "plug_peak_kw": 29,
  "plug_baseline_kw": 4,
  "gas_peak_scfh": 500,
  "gas_baseline_scfh": 50,
  "water_peak_gpm": 8,
  "water_baseline_gpm": 0.05,
  "voltage_nominal": 208,
  "voltage_phase_nominal": 120,
  "power_factor_nominal": 0.92
}
```

**Meter scope nesting after calibration (hard invariant):**
- Meter A peak: ~200 kW (building total)
- Meter B peak: ~170 kW (AHU_2+3 + 20 VAVs including electric reheat)
- Meter C peak: ~110 kW (AHU_2+3 fans/compressors only, no VAVs)

B and C meaningfully different by ~60 kW on a cold day with reheat active. On a mild/warm day with no reheat, B ≈ C. Correct and expected.

**AHU Real Power point** (Points Ref §5, AHU AI 8) now represents fan + compressor + aux together, not fan only. Update the point description accordingly in the AHU device template.

### Flag 2 — Peak demand window (RESOLVED)

Fixed calendar-aligned 15-minute intervals, reset at `:00/:15/:30/:45`. Implementation: maintain running max of real power within the current quarter-hour; commit to AI 9 ("Peak demand") at the quarter-hour boundary; reset running max for the next interval. Matches utility billing convention and what a real E-Mon Class 3200 does.

### Flag 3 — Vendor IDs (RESOLVED)

Verify at implementation against the ASHRAE BACnet Vendor ID list. No placeholders or TODOs in code. Spec's `224` (E-Mon) and `194` (ONICON) are placeholders — confirm or correct when implementing device object metadata, drop a code comment with the authoritative source.

### Flag 4 — IP range gap (RESOLVED, deferred to deploy)

Not blocking for code. Co-worker's loopback adapter must have at least 28 contiguous IPs assigned before running. README includes `netsh interface ipv4 add address` commands as reference.

### Flag 5 — Coexistence of old tree (RESOLVED)

**Ship artifact contains only:** `simulator/`, `run.bat`, `site_config.json`, `requirements.txt`, `README.md`. Existing `devices/`, `scenarios/`, `simulation/` flat tree stays in dev repo as reference, excluded from ship zip. Use `.gitattributes export-ignore` or a build script copying only ship paths into the zip staging dir. Vendor templates (AAON, JCI, Distech, ALC, JB) are dev-time reference only.

## Scaffold order (greenlit)

1. `simulator/__main__.py` — entry point, asyncio event loop, load config, instantiate site_model + devices, run forever on 10-sec tick.
2. `simulator/config.py` — load and validate `site_config.json`. Fail fast with clear errors if required fields missing.
3. `simulator/site_model.py` — OAT generator, occupancy schedule, lighting driver, plug driver. No BACnet awareness. Pure tick-driven model.
4. **One E-Mon Class 3200 device** — full 43 AIs bound to single IP, responds to Who-Is with I-Am, all points readable. Use Meter A (building-wide) first.
5. **Verify end-to-end on one IP** — Who-Is/I-Am works; all 43 AIs readable; kWh totalizer increases monotonically and matches ∫kW over a 10-minute observation.

Once vertical slice is clean, replication to the other 25 devices is mechanical. Fix bacpypes3 async quirks, multi-IP binding on Windows, BACnet object registration ordering on device 1, not device 26.

## Ownership split

**Claude Code owns:**
- bacpypes3 API decisions (use current docs at implementation, not memory)
- Code structure, package layout within `simulator/`, async patterns, error handling
- Vendor ID verification
- `netsh` command syntax in README
- Logging implementation (console INFO, file DEBUG, daily rotate, 7-day retention)
- `requirements.txt` pinning

**Escalate to Jake (brings web Claude in if needed):**
- Spec ambiguity that can't be resolved from context
- Any magnitude that, during implementation, seems off by >2x of what's expected for a Michigan office
- Any decision that changes ship artifact contents or device manifest

## Acceptance for Phase 1 ship (end of this week)

- [ ] Zip unzips cleanly to any folder
- [ ] `run.bat` creates venv, installs deps, starts simulator on first run
- [ ] Console shows all 26 devices binding to their IPs on startup
- [ ] `bacpypes3` responds to Who-Is with I-Am for all 26 devices
- [ ] All 43 AIs on each E-Mon readable via BACnet ReadProperty
- [ ] All AHU, VAV, gas, water points readable
- [ ] Values update every 10 seconds
- [ ] Meter nesting holds: `kW_A ≥ kW_B ≥ kW_C` at all observed ticks
- [ ] kWh totalizers increase monotonically and match ∫kW over 10-minute observation
- [ ] Peak demand (AI 9) resets at quarter-hour boundaries
- [ ] Log file created at `./logs/simulator.log`, rotates daily
- [ ] README allows a controls tech with Claude Code assistance to run the sim without asking Jake

Tuning pass (Phase 2) is config-file-only, after co-worker has 2–3 days of Niagara history.
