# BACnet Bounty — Sprint Tracker

**Deadline:** Monday 2026-04-20 (co-worker ship). Weekend is buffer only.

---

## Phase 1 — Vertical slice (scaffold + 3 E-Mon meters on wire) ✅
**Completed:** 2026-04-14
**Commit:** `e7564b3 Phase 1 vertical slice: 3 EMON meters verified on BACnet wire`

Deliverables:
- `simulator/` package scaffold (`__main__`, `config`, `site_model`, `logging_config`, `devices/emon`)
- Three E-Mon Class 3200 devices bound on loopback, all 43 AIs readable
- `scripts/verify_meters_abc.py` passes 4 checks (bind, winter A≥B≥C nesting, winter B-C > 30 kW reheat delta, summer B-C < 5 kW)
- Resolution doc `03_BACnet_Bounty_Phase1_Handoff_Resolutions.md`

## Phase 2 — Consolidation ✅
**Completed:** 2026-04-15

Deliverables:
- [x] Legacy cleanup (vendor devices, scenarios, device-data, legacy runners deleted; `reference/` seeded)
- [x] `requirements.txt` pinned to `BAC0==2025.9.15`
- [x] `site_config.json` `start_octet: 1 → 200`
- [x] `.claude/CLAUDE.md` rewritten (real tree, architectural invariants, quality bar)
- [x] Resolution doc `04_BACnet_Bounty_Phase2_Resolutions.md` seeded
- [x] `ops/` scaffold (this file, work report, handoff, action items)
- [x] Venv round-trip smoke test (fresh `.venv-verify`, `pip install`, import + tick validated)
- [x] `scripts/verify_meters_abc.py` passes 4/4 on new `.200`–`.202` IPs
- [x] Loopback script `scripts/add_loopback_ips.bat` seeded (`.200`–`.228`)

## Phase 3 — ONICON gas + water meters ✅
**Completed:** 2026-04-15

Deliverables:
- [x] `simulator/devices/onicon_gas.py` (F-5500, vendor 194, 3 AIs)
- [x] `simulator/devices/onicon_water.py` (F-3500, vendor 194, 3 AIs)
- [x] `simulator/site_model.py` extended: `gas_heating_fraction`, `gas_temp_f`, `water_temp_f` added to `SiteState`; gas physics rewired to spec formula
- [x] Gas + water registered in `DEVICE_MANIFEST` (`110001` @ offset 3, `120001` @ offset 4)
- [x] `scripts/verify_gas_water.py` — 7/7 PASS
- [x] Both `verify_meters_abc.py` (4/4) AND `verify_gas_water.py` (7/7) pass
- [x] Full runtime smoke: `py -m simulator` brings up all 5 devices cleanly

## Phase 4 — AHU device class (3 instances) ✅
**Completed:** 2026-04-15 (Session B)
**Commit:** `682f624 Phase 4: AHU device class — 3 instances verified on wire`

Deliverables:
- [x] `simulator/ahu_physics.py` — pure-function physics
- [x] `simulator/devices/ahu.py` — 18-point BACnet wrapper with AV/BV (doc 04 Flag E)
- [x] 3 instances: AHU_1 (single-zone, 200001), AHU_2/AHU_3 (VAV, 200002/200003)
- [x] `scripts/verify_ahu.py` — 28/28 PASS
- [x] Warnings filter in `__main__.py` for bacpypes3 vendor UserWarnings

## Phase 5 — VAV device class (20 instances) ✅
**Completed:** 2026-04-15 (Session B)
**Commit:** `ba012ea Phase 5: VAV device class — 20 instances; 28 devices on wire`

Deliverables:
- [x] `simulator/vav_physics.py` — pure-function physics
- [x] `simulator/devices/vav.py` — 9-point BACnet wrapper with AV/BV (doc 04 Flag E)
- [x] 20 instances 300001–300020, fed from AHU_2 (1–10) and AHU_3 (11–20)
- [x] Config rows in `site_config.json vavs[]` (position tags, zone_phase_deg spread)
- [x] `scripts/verify_vav.py` — 28/28 PASS
- [x] Meter B rewired to sum per-VAV valve positions (zero drift, spec doc 03 Flag 1)
- [x] All 4 verify scripts pass — 67/67 total checks

## Phase 6 — Ship packaging ✅
**Completed:** 2026-04-15 (Session C, pulled forward from 4/17 because Session B ran ~30 min vs estimated 3h)
**Commit:** (see git log — one commit covering run.bat + README + signal fix + utf-8 stdout + zip staging)

Deliverables:
- [x] `run.bat` — idempotent venv bootstrap, PYTHONIOENCODING=utf-8:replace, pause-on-exit
- [x] `README.md` — full co-worker guide (prereqs, netsh block, soak-friendliness, troubleshooting)
- [x] Ship zip at `dist/bacnet_bounty.zip` (38 KB, 17 files, self-contained)
- [x] Scratch-dir smoke: unzip → venv → 28 devices → clean Ctrl+C → ports released
- [x] Signal-handler bug fix for Windows Ctrl+C (was silent-fail; now verified with CTRL_BREAK_EVENT)
- [x] UTF-8 stdout reconfigure in all 4 verify scripts (portable unicode fix)
- [x] Soak running on dev box (PID 33672, started 2026-04-15 13:33 EDT)

## Phase 7 — Tuning pass ⏳
**Target:** post-ship (after co-worker has 2–3 days of Niagara Reflow history)
**Status:** planned, not blocking

- Config-file-only magnitude adjustments based on plotted trend data
- No code rewrites
- Delivered as updated `site_config.json` drop-in

---

## Critical dates
- **2026-04-15** (today, Wed): Sessions A (Phase 2 + 3). 5 devices on wire.
- **2026-04-16** (Thu): Session B (Phase 4 + 5). 28 devices on wire.
- **2026-04-17** (Fri): Session C (Phase 6). Zip ready to hand off.
- **2026-04-18 – 04-19** (Sat–Sun): buffer. Slip absorption only — no planned work.
- **2026-04-20** (Mon): co-worker receives zip.
