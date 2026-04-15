# BACnet Bounty — Action Items

Running punch list. Flagged items live here until resolved or intentionally deferred.

---

## Open

### [Spec docs] Amend 01 and 02 per Phase 2 resolutions
**Owner:** Jake (brings web Claude)
**Blocker for:** nothing urgent; clean-up task
**Detail:** `.claude/references/04_BACnet_Bounty_Phase2_Resolutions.md` documents four corrections (stack, instance IDs, start_octet, device count typo). Propagate into the source docs so future sessions read cleanly without needing 03 + 04 reconciliation.

### [Phase 6] Ship packaging — Session C
**Owner:** Claude Code (Session C), Jake (smoke test)
**Target:** Friday 2026-04-17
**Detail:** `run.bat`, `README.md`, `.gitattributes export-ignore` or zip build script, final zip smoke test on a scratch directory. See `ops/sprint-tracker.md` Phase 6 for full checklist.

### [Legacy] `scripts/verify_meter_a.py` disposition
**Owner:** Jake (decide during Session C)
**Detail:** Phase 1 single-meter precursor. Superseded by `verify_meters_abc.py`. Not on the Phase 2 cleanup list, so retained and flagged per the "do not silently delete" rule. Decide at Session C whether to delete or keep as historical artifact.

### [Dev box] Python 3.14 vs ship-target 3.12
**Owner:** Claude Code (monitor)
**Detail:** Dev box is 3.14.3; ship target per spec 01 §8 is 3.12. BAC0 `2025.9.15` works on both per install metadata. If any 3.14-only feature sneaks in or a behavioral difference shows up, flag here. Not a blocker.

### [Loopback] Old Phase 1 IPs (`.1`–`.11`) still on adapter
**Owner:** Jake (Session C cleanup decision)
**Detail:** After `start_octet: 1 → 200` swap, the old Phase 1 IPs `192.168.100.1` through `.11` are still assigned to the `Bacnet Simulator` loopback adapter. Unused by current config. No harm leaving them, but Session C README should either (a) instruct co-worker to clear them before adding the ship range, or (b) document that stale IPs on the adapter don't interfere. Simpler to remove on dev box and keep README clean.

### [bacpypes3] Vendor 224 re-registration warnings
**Owner:** Claude Code (monitor in Session B)
**Detail:** `verify_meters_abc.py` surfaces two `UserWarning`s from `bacpypes3/vendor.py:109` — "object type 56 for vendor identifier 224 already registered" and "object type 8 for vendor identifier 224 already registered". Cosmetic — library noise when multiple BAC0.lite instances register against the same vendor ID in one process. Not blocking. If Session B's 28-device bring-up starts flooding the console with these, consider a `warnings.filterwarnings` shim in `simulator/__main__.py` or `EmonClass3200.__init__`.

### [Adapter name] Corrected in CLAUDE.md
Note: actual adapter name on dev box is `Bacnet Simulator` (index 11), not "Ethernet 11 KM-TEST Loopback" as the inherited Controls-Suite CLAUDE.md implied. Fixed in rewrite. Co-worker's adapter name will differ — README must make that a configurable placeholder.

### [Metro naming] AHU/VAV point names follow spec (not Metro abbreviations)
**Owner:** Jake + co-worker (review at integration)
**Detail:** Per Session B Q1, AHU/VAV points use spec 02 §5/§6 literal names (`Supply_Air_Temperature`, `Zone_Temperature`, etc.) rather than Metro abbreviations (`SA_T`, `ZN_T`). If co-worker's Niagara slot sheets expect Metro-style naming for existing templates, there's no auto-match. Simulator devices are fresh proxy points bound to new slots so this is almost certainly a non-issue, but flagged per the visibility note from Claude.ai review.

### [Bring-up time] 28 devices take ~60 seconds to initialize
**Owner:** Claude Code (Session C README)
**Detail:** 2 seconds per device × 28 devices = ~60s bring-up time. README must set co-worker expectation so they don't kill the process prematurely thinking it's hung. Banner prints IP plan before device bring-up loop starts, so there's nothing user-visible for the first minute beyond "binding N devices..." messages scrolling.

### [Phase 7] Tuning pass triggers
**Owner:** Jake
**Target:** post-ship, after co-worker has 2–3 days of Niagara Reflow history
**Detail:** Config-only magnitude adjustments. Non-blocking for ship. Known candidates for review:
- Gas peak/baseline realism vs. actual Michigan office gas bill data
- VAV reheat total kW vs. B-C meter delta observed on cold days
- Water flush-burst frequency vs. observed water trend

## Resolved (during Phase 2)

### [Flag A] Stack: BAC0 vs bacpypes3
Resolved in doc 04. BAC0 is authoritative. Pinned `BAC0==2025.9.15` in `requirements.txt`.

### [Flag B] Instance IDs: 6-digit vs 3-digit
Resolved in doc 04. Keep 6-digit category-prefixed (per Phase 1 implementation). Amend spec 02 §1, not code.

### [Flag C] `start_octet`: 200 vs 1
Resolved in doc 04. `site_config.json` updated to `start_octet: 200`.

### [Flag D] Device count typo (spec 01 §4: "26" should be "28")
Resolved in doc 04. Noted; propagate to source doc at Jake's convenience.

### [Filename mismatch] Cleanup list vs actual filenames
Resolved per Jake's confirmation: move `devices/ahu.py` → `reference/generic_ahu.py`, `devices/vav_reheat.py` → `reference/generic_vav.py`. Delete `devices/chiller_plant.py`, `devices/exhaust_fans.py`.
