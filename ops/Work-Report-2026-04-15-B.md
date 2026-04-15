# Work Report — 2026-04-15 (Session B)

**Session scope:** Phase 4 (AHU class, 3 instances) + Phase 5 (VAV class, 20 instances)
**Operator:** Claude Code (Opus 4.6)
**Starting commit:** `41c5515 Add PROJECT_CONTEXT.md for web-Claude project knowledge sync` (end of Session A)
**Ending commit:** `ba012ea Phase 5: VAV device class — 20 instances; 28 devices on wire`

---

## Delta from Session A close-out

Session A shipped 5 devices on the wire (3 E-Mon + gas + water). Session B closes the remaining 23 devices — 3 AHUs and 20 VAVs — bringing the wire count to the full **28 devices** specified in doc 01 §4 / doc 02 §1. Ship artifact is functionally complete; Session C (Friday 2026-04-17) adds packaging only.

## Phase 4 — AHU device class

### Done

1. **`simulator/ahu_physics.py`** — pure-function module per architectural invariant #2. `compute_ahu_state()` takes `SiteState` + `AHUConfig` + `ahu_index` and returns an `AHUState` dataclass with every BACnet point value.

   Key design decisions:
   - **Mode selection** driven off `SiteState.cooling_load_fraction` vs `heating_load_fraction` (dominant wins). SAT setpoint 55°F cooling / 65°F heating / 60°F shoulder per spec 02 §5 AV 1.
   - **`AHU_Real_Power` reads pre-computed per-AHU kW from `SiteState`** (`ahu_sz_kw` / `ahu_vav_1_kw` / `ahu_vav_2_kw`) rather than re-deriving from fan + compressor. Would have double-counted vs Meter A otherwise. Doc 03 §Flag 1 redefined this point as "fan + compressor + aux" so the existing SiteModel scalar already includes everything.
   - **Economizer logic**: OA damper opens to 100% when `cooling_mode and 50 < OAT < 65`, otherwise sits at 15% minimum when occupied.
   - **Fan kW affinity law** (`nominal × (VFD%/100)^2.5`) was considered but NOT applied — SiteState's per-AHU kW is already the right answer. Fan VFD speed command is cosmetic for the point list.

2. **`simulator/devices/ahu.py`** — `AHU` class, thin BACnet wrapper. 18 points per spec 02 §5 with **doc 04 Flag E** substitutions: spec's AO 1–4 → AV 3–6; spec's BO 1 → BV 1. AI 1–8 and AV 1–2 are straight from the spec. Point names use underscores in place of spaces (e.g., `Supply_Air_Temperature`, `Cooling_Stage_DX_Status`) following Phase 1's E-Mon pattern.

3. **`simulator/site_model.py`** — adds `ahu_sat_f: tuple[float, float, float]` field to `SiteState`. Per-AHU SAT tracks mode (55/65/60) with ±0.8°F drift per AHU so the three devices don't all sit at the same decimal. VAV physics reads these for discharge-air-temp coupling.

4. **`simulator/config.py`** — `AHUConfig` dataclass with strict validation (kind must be `single_zone` or `vav`; CFM/kW/tons must be positive).

5. **`simulator/__main__.py`** — **`warnings.filterwarnings()` added at the top** (before BAC0 import) to suppress bacpypes3's vendor-object-type re-registration UserWarnings. With 28 devices binding, that's 56 warnings that would scroll past on startup; filtered per Claude.ai review guidance. Also extends `DEVICE_MANIFEST` with 3 AHU entries and kind-dispatch for `"ahu"`.

6. **`site_config.json`** — new `ahus[]` section with 3 rows: AHU_1 (single_zone, 1600 CFM, 2.5 kW fan, 12 tons, 0.5 inWC SA pressure), AHU_2/AHU_3 (VAV, 5600 CFM, 8.0 kW, 40 tons, 1.5 inWC).

7. **`scripts/verify_ahu.py`** — 28-check verification: all 54 points readable across 3 AHUs, summer/winter assertions per AHU (SAT tracks setpoint ±10°F, OAT mirrors site OAT, fan running when occupied, cooling active in summer, heating valve active in winter, real power > 0.5 kW when occupied).

8. **`.claude/references/04_BACnet_Bounty_Phase2_Resolutions.md`** — new **Flag E** documents the AV/BV override. Supersedes spec 02 §5/§6 object-type columns. Lists the exact point-by-point mapping for both AHU and VAV commandable objects so future AI sessions don't re-derive the wrong thing from spec 02 in isolation.

### Metro-naming divergence note

Per Jake's Session B Q1 answer, AHU/VAV point names follow spec 02 §5/§6 literally (`Supply_Air_Temperature`, `Zone_Temperature`, etc.) rather than applying Metro Controls abbreviation conventions (`SA_T`, `ZN_T`). This is the right call for simulator↔spec consistency and matches what the co-worker will see in spec doc reads.

**Implication for co-worker's Niagara integration:** If his downstream slot sheets use Metro abbreviation conventions for existing production templates, the simulator point names won't auto-match. These are fresh proxy devices bound to new slots, not migrating into existing Metro templates, so this is almost certainly fine. Flagging for visibility.

### Phase 4 verification

| Script | Checks | Result |
|---|---|---|
| `verify_meters_abc.py` (Phase 1 regression) | 4 | 4/4 PASS |
| `verify_gas_water.py` (Phase 3 regression) | 7 | 7/7 PASS |
| `verify_ahu.py` (new) | 28 | 28/28 PASS |
| `py -m simulator` 8-device smoke | 8 devices online, zero warnings | ✅ |

**Phase 4 commit:** `682f624 Phase 4: AHU device class — 3 instances verified on wire`

## Phase 5 — VAV device class

### Done

1. **`simulator/vav_physics.py`** — pure-function module. `compute_vav_state()` takes `SiteState` + `VAVConfig` + `vav_index` and returns `VAVState`.

   Key design decisions (all favor simplicity per Session B Q5/Q6 answers):
   - **Zone temperature** and **reheat valve position** read from `SiteState` tuples (`vav_zone_temps_f[i]`, `vav_valve_positions[i]`). Site model owns these as primary data; VAV physics just pulls by index. No per-VAV ticking inside the device class.
   - **Discharge air temperature** = parent AHU SAT (from `SiteState.ahu_sat_f[parent_idx]`) + `valve × 30°F` max reheat rise. Spec-simple; doc 02 §6 AI 3 formula.
   - **Airflow setpoint** minimum when heating (reheat handles temp, flow stays at min_cfm), ramps from min_cfm to design_cfm with cool_frac when cooling.
   - **Damper position** tracks actual airflow as fraction of design; enforces min position for ventilation when occupied.

2. **`simulator/devices/vav.py`** — `VAV` class, thin BACnet wrapper. 9 points per spec 02 §6 with doc 04 Flag E substitutions: spec's AO 1–2 → AV 4–5. AI 1–3 and AV 1–3 straight from spec. BI 1 (`Occupancy_Status`) straight from spec (not a commandable point so no override needed).

3. **`simulator/site_model.py` (extended)** — adds `vav_valve_positions: tuple[float, ...]` and `vav_zone_temps_f: tuple[float, ...]` to `SiteState`. Per-VAV computation in `tick()`:
   - **Valve position** = `reheat_activity_base × phase_mod × position_weight`, clamped [0, 1].
     - `reheat_activity_base = heat_frac × max(0.3, occ)` (existing Phase 1 formula, preserved)
     - `phase_mod = 1.0 + 0.20 × sin(zone_phase_deg)` — per-instance ±20% decouples 20 VAVs from lockstep (Q4 answer)
     - `position_weight = 1.15` for perimeter, `0.85` for interior — envelope exposure effect
   - **Zone temp** = active setpoint + `0.8 × sin(phase_rad)` drift + perimeter/interior envelope bias + ±0.3°F jitter
   - **Meter B rollup rewired** to `sum(valve_positions) × vav_reheat_peak_kw_each`. Per spec doc 03 §Flag 1: "reheat valve position × per-VAV max reheat kW is computed at the model layer and rolls up into Meter B's kW." Zero drift between per-VAV readings on the wire and Meter B's reading on the wire — same numbers, same tick.
   - **Fallback path** preserved for when no VAVs configured (Phase 1-3 compat): uses the old aggregate `reheat_activity × 20 × peak_kw` formula so meter nesting still works if someone runs with an empty `vavs[]` section.

4. **`simulator/config.py` (extended)** — `VAVConfig` dataclass with cross-validation (parent_ahu must exist in ahus[], position must be perimeter|interior, min_cfm ≤ design_cfm).

5. **`simulator/__main__.py` (extended)** — 20 VAV entries via list comprehension (device_id 300001..300020, ip_offset 8..27, vav_index 0..19 parallel to config order). Dispatch for kind=`"vav"`.

6. **`site_config.json`** — `vavs[]` section with 20 rows. Each row: `{name, parent_ahu, position, design_cfm, min_cfm, reheat_mbh, zone_phase_deg}`. Alternating perimeter/interior. Zone phase spaced at 18° increments across 360° so zone temps don't move in lockstep. VAV_1–10 under AHU_2, VAV_11–20 under AHU_3.

7. **`scripts/verify_vav.py`** — 28-check verification, spot-checks 3 representative VAVs (VAV_1 under AHU_2 perimeter, VAV_11 under AHU_3 perimeter, VAV_20 under AHU_3 interior). Winter / summer / unoccupied scenarios. Validates zone temp range, airflow ≥ min, damper modulation, reheat valve behavior, DA temp coupling to parent AHU SAT, occupancy BI tracking schedule.

### Hiccups

- **Unicode `≈` character crashed Windows cp1252 console.** Initial verify_vav.py print line with `≈` failed on the `PASS` print after the first summer VAV check. Replaced with `~=`. 1-minute fix. Worth remembering for future scripts: stick to ASCII in print strings on this dev box.

### Phase 5 verification

| Script | Checks | Result |
|---|---|---|
| `verify_meters_abc.py` (Phase 1 regression) | 4 | 4/4 PASS — winter B-C=46.8 kW (previously 47.4 kW with aggregate formula; shift is from per-VAV valve sum approximating the old aggregate ±2%; still well above 30 kW threshold) |
| `verify_gas_water.py` (Phase 3 regression) | 7 | 7/7 PASS |
| `verify_ahu.py` (Phase 4 regression) | 28 | 28/28 PASS |
| `verify_vav.py` (new) | 28 | 28/28 PASS |
| **TOTAL** | **67** | **67/67 PASS** |

`py -m simulator` full stack smoke: 28 devices online in ~60s (2s/device consistent), tick loop steady, OAT=50.5F kW_A=93.5 kW_B=20.6 kW_C=12.5 gas=127scfh water=3.20gpm. Zero bacpypes3 vendor warnings on console — filter confirmed working.

**Phase 5 commit:** `ba012ea Phase 5: VAV device class — 20 instances; 28 devices on wire`

## Session-level status

- Device classes complete — **5 of 5 per architectural invariant #1**: `EmonClass3200`, `OniconF5500Gas`, `OniconF3500Water`, `AHU`, `VAV`. No more device work ahead.
- All 28 devices verifiable on wire.
- Meter nesting invariant (A ≥ B ≥ C) holds at all observed ticks; Meter B = C + Σ(per-VAV reheat kW) exactly.
- Warnings filter working — co-worker's startup banner will be clean.
- `reference/` (generic_ahu.py, generic_vav.py, ahu_model.py, zone_model.py, g36_controller.py) served as pattern input but wasn't copied verbatim into Session B code. Doc 04 + memory rules honored.

## Ready for Session C (Friday 2026-04-17)

Session C scope per sprint tracker: Phase 6 ship packaging.
- `run.bat` — creates venv on first run, installs requirements, launches `py -m simulator`
- `README.md` — co-worker setup guide with `netsh` reference block, `site_config.json` editing instructions, bring-up timing note (~60s for 28 devices)
- `.gitattributes export-ignore` or zip build script — ship excludes `reference/`, `scripts/`, `ops/`, `.claude/`, `PROJECT_CONTEXT.md`
- Ship smoke test: unzip to scratch dir, double-click run.bat, verify clean bring-up

Weekend buffer (Sat 4/18, Sun 4/19) intact. Deadline Monday 4/20 looks comfortable.

## End-of-Session-B deliverables checklist

- [x] Phase 4 commit — `682f624`
- [x] Phase 5 commit — `ba012ea`
- [x] `ops/Handoff-2026-04-15-B.md` finalized (Session B → Session C)
- [x] `ops/sprint-tracker.md` updated (Phases 4 + 5 ✓)
- [x] `ops/action-items.md` updated with Session C carry-forward items
- [x] 28 devices on the wire
- [x] All 4 verify scripts pass (67/67 checks)
- [x] Doc 04 Flag E documents AV/BV override
