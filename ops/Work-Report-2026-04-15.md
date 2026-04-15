# Work Report — 2026-04-15 (Session A)

**Session scope:** Phase 2 (consolidation) + Phase 3 (ONICON gas + water meters)
**Operator:** Claude Code (Opus 4.6)
**Starting commit:** `e7564b3 Phase 1 vertical slice: 3 EMON meters verified on BACnet wire`

---

## Phase 2 — Consolidation

### Done

1. **Legacy cleanup.** Moved to `reference/` (kept as pattern material for AHU/VAV implementation in Session B):
   - `devices/ahu.py` → `reference/generic_ahu.py`
   - `devices/vav_reheat.py` → `reference/generic_vav.py`
   - `simulation/ahu_model.py` → `reference/ahu_model.py`
   - `simulation/zone_model.py` → `reference/zone_model.py`
   - `simulation/g36_controller.py` → `reference/g36_controller.py`

   Deleted outright (vendor-specific, not reusable under the 5-class invariant):
   - `devices/aaon_rtu.py`, `devices/aaon_vccx_ip_full.py`, `devices/alc_vav_electric_rh.py`, `devices/distech_ecb_vav.py`, `devices/jace8000.py`, `devices/jb_unit_vent.py`, `devices/jci_fec_misc.py`, `devices/jci_fec_vav.py`, `devices/chiller_plant.py`, `devices/exhaust_fans.py`, `devices/__init__.py`
   - `simulation/plant_model.py`, `simulation/faults.py`, `simulation/__init__.py`
   - `device-data/` (entire directory — 5 CSV/JSON vendor reference files)
   - `scenarios/` (entire directory — 12 old scenario runners)
   - Root: `run_simulator.py`, `test_client.py`, `generate_trends.py`

   Empty directories `devices/` and `simulation/` removed. Tree is now flat and minimal.

2. **`requirements.txt`.** Replaced `bacpypes3>=0.0.106` (stale from spec drafts — was never what the code imported) with `BAC0==2025.9.15` (pinned to what Phase 1 actually shipped and what `py -m pip show BAC0` reports as installed).

3. **`site_config.json`.** `start_octet: 1 → 200`. Aligns to spec 02 §1. Devices now bind `.200`–`.227`; low octets (`.1`–`.199`) reserved for infrastructure.

4. **`.claude/CLAUDE.md`.** Full rewrite from the Controls-Suite-inherited template:
   - Real tree layout (root-level `simulator/`, not `tools/simulator/`)
   - Source-of-truth pointer to the four spec docs in `.claude/references/`
   - Architectural invariants verbatim from the Session A prompt
   - Quality bar language ("plausible enough that nobody says 'that number's wrong'")
   - 6-digit instance ID scheme documented
   - No vendorName callout
   - Kept the kill-and-restart and detached-launch conventions

5. **`.claude/references/04_BACnet_Bounty_Phase2_Resolutions.md`.** New doc-03-style resolution note covering:
   - **Flag A** — BAC0 authoritative over bacpypes3 (supersedes specs 01/02 §9, spec 03 ownership split)
   - **Flag B** — 6-digit category-prefixed instance IDs (supersedes spec 02 §1 table)
   - **Flag C** — `start_octet=200` (aligns to spec 02 §1, corrects Phase 1 drift)
   - **Flag D** — "26 devices" in spec 01 §4 is a typo; real count is 28

6. **`ops/` scaffold.** Created `sprint-tracker.md`, `action-items.md`, this work report, and a handoff doc (finalized at session end).

### Flagged / not silently decided

- **`scripts/verify_meter_a.py`** — Phase 1 single-meter precursor to `verify_meters_abc.py`. Not on the Phase 2 cleanup list. Retained per the "flag, do not silently delete" rule. Logged to `ops/action-items.md` for Session C disposition decision.
- **Python 3.14 on dev box** — ship target is 3.12 per spec 01 §8. BAC0 works on both. No action unless compatibility surfaces. Logged to action items.
- **Gas peak magnitude conflict** — Jake's Session A prompt cited spec 02 §3's `3000 SCFH` peak, but doc 03 §Flag 1 explicitly supersedes that to `500 SCFH` because VAV reheat is electric. Jake confirmed: keep 500 (doc 03 wins). No code change — `site_config.json` already had `500/50` from Phase 1.

### Bind test

7. **Venv round-trip smoke test.** Fresh `.venv-verify`, `py -m pip install -r requirements.txt` (clean, single package: BAC0==2025.9.15 with its transitive deps — aiosqlite, BACpypes3, colorama, python-dotenv, pytz). Import-and-tick smoke: `from simulator.config import load_config; from simulator.site_model import SiteModel`; loads `site_config.json`, ticks once, produces plausible values (OAT=48.3F, kW_A=98.2). Torn down after success.

8. **Loopback adapter IPs.** Discovered the KM-TEST adapter is actually named `Bacnet Simulator` on this dev box (old CLAUDE.md said "Ethernet 11 KM-TEST Loopback" — stale from Controls-Suite; corrected in rewrite). Wrote `scripts/add_loopback_ips.bat` to idempotently add `192.168.100.200`–`.228` to the `Bacnet Simulator` adapter; Jake ran it elevated. Range now covers Phase 2/3 verify (`.200`–`.205`) plus Session B ship range (`.200`–`.228`).

   Old Phase 1 range (`.1`–`.11`) still present on the adapter but unused after `start_octet: 1 → 200` swap. No harm, no action for this session — flagged in `ops/action-items.md` for Session C cleanup decision.

9. **`scripts/verify_meters_abc.py` on new `.200` range.** PASS 4/4:
   - Winter (Jan 21 13:00): A=134.2, B=60.1, C=12.7 kW; nesting ✓; B-C=47.4 kW (> 30 threshold for electric-reheat-active) ✓
   - Summer (Jul 21 15:00): A=163.7, B=79.1, C=79.1 kW; nesting ✓; B-C=0.0 kW (< 5 threshold for reheat-dormant) ✓

   Two non-fatal `bacpypes3.vendor` UserWarnings surfaced ("object type 56 for vendor identifier 224 already registered" and "object type 8 for vendor identifier 224 already registered"). These are library-internal noise about re-registering vendor 224's NetworkPortObject and DeviceObject classes across multiple BAC0.lite instances in the same process. Known pattern when multiple devices share a Python process. Not blocking; log entry in action-items.md if it becomes user-visible in Session B's larger device count.

---

## Phase 3 — ONICON gas + water meters

*Status: pending Phase 2 completion. This section fills in during execution.*

---

## End-of-session deliverables checklist

- [ ] Phase 2 commit pushed
- [ ] Phase 3 commit pushed
- [ ] `ops/Handoff-2026-04-15.md` finalized with state + Session B readiness
- [ ] `ops/sprint-tracker.md` updated (Phase 2 ✓, Phase 3 ✓)
- [ ] 5 devices on the wire (3 E-Mon + gas + water)
- [ ] Both verify scripts pass
