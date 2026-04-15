# BACnet Bounty — Phase 2 Consolidation Resolutions

**Version:** 1.0
**Date:** April 15, 2026
**Supersedes:** conflicting guidance in `01_BACnet_Bounty_Architecture_and_Scope.md` and `02_BACnet_Bounty_Device_and_Points_Reference.md` per the items below. Both spec docs remain source of truth for everything not addressed here. Extends `03_BACnet_Bounty_Phase1_Handoff_Resolutions.md`.
**Status:** Greenlit for Claude Code implementation

---

## Context

Claude Code's pre-execution review of the Phase 2/3 plan flagged three conflicts between the current repo state (which ships Phase 1 code) and the spec docs. Jake reviewed with web Claude. All three resolved. This doc is the companion to the Phase 2 "consolidation" commit.

## Resolutions

### Flag A — Stack: BAC0, not bacpypes3 (RESOLVED)

**Specs 01 §9 and 02 §9 prescribe `bacpypes3` as the BACnet stack.** Doc 03 ownership split reinforces this ("bacpypes3 API decisions..."). Phase 1 shipped with **BAC0** (version `2025.9.15`). BAC0 wraps BACpypes3 internally, so the underlying protocol is the same, but the public API used by `simulator/devices/emon.py` and the verify scripts is BAC0-specific.

**Resolution:** BAC0 is authoritative. Specs 01/02 §9 are stale and should be read as "BAC0 (which wraps bacpypes3) — pinned to `2025.9.15`". Migrating to bare bacpypes3 would require rewriting the device classes and verify scripts; Phase 1 works, ship deadline does not budge.

**Implementation:**
- `requirements.txt` pins `BAC0==2025.9.15`.
- Device classes continue to use `BAC0.lite(...)` and `ObjectFactory` from `BAC0.core.devices.local.factory`.
- Downstream acceptance bullets in spec 02 §10 that reference "bacpypes3 responds to Who-Is" should be read as "BAC0-bound devices respond to Who-Is" — same outcome on the wire.

### Flag B — Instance ID scheme: 6-digit category-prefixed, not 3-digit (RESOLVED)

**Spec 02 §1 manifest table uses 3-digit instance IDs (100, 101, 102, 110, 120, 200–202, 301–320).** Phase 1 shipped with **6-digit category-prefixed IDs** (100001/100002/100003 for E-Mon A/B/C). This drift was flagged during Phase 2 review.

**Resolution:** The 6-digit scheme is correct. Keep it. Amend the specs, not the code.

**Rationale:** Real JACE-discovered BACnet networks in production routinely live in the 6-digit range and partition by category prefix — it matches what the co-worker will see when integrating real gear at future sites. The 3-digit example in spec 02 was a clean-table choice, not a correctness one. Phase 1's drift toward 6-digit was the right instinct. It also gives the dashboard nicer storytelling — co-worker can see device categories at a glance in Niagara's discovery list.

**Canonical instance ID scheme (supersedes spec 02 §1):**

| Device | Instance ID | IP Offset | Type |
|---|---|---|---|
| Electrical Meter A | `100001` | 0 | E-Mon Class 3200 |
| Electrical Meter B | `100002` | 1 | E-Mon Class 3200 |
| Electrical Meter C | `100003` | 2 | E-Mon Class 3200 |
| Gas Meter | `110001` | 3 | ONICON F-5500 |
| Water Meter | `120001` | 4 | ONICON F-3500 |
| AHU_1 | `200001` | 5 | single-zone RTU |
| AHU_2 | `200002` | 6 | VAV RTU |
| AHU_3 | `200003` | 7 | VAV RTU |
| VAV_1 … VAV_10 | `300001` … `300010` | 8 … 17 | VAV w/ reheat (under AHU_2) |
| VAV_11 … VAV_20 | `300011` … `300020` | 18 … 27 | VAV w/ reheat (under AHU_3) |

Prefix conventions:
- `1xxxxx` — electric meters
- `11xxxx` — gas meter(s)
- `12xxxx` — water meter(s)
- `2xxxxx` — AHUs
- `3xxxxx` — VAVs

### Flag C — `start_octet`: 200, not 1 (RESOLVED)

**Spec 02 §1 prescribes `start_octet=200`.** `site_config.json` shipped Phase 1 with `start_octet=1`, putting devices at `.1`–`.4` of the `192.168.100.` subnet. This drift was flagged during Phase 2 review.

**Resolution:** Align to spec. Updated `site_config.json` sets `start_octet: 200`. Devices now bind `.200`–`.227`, leaving low octets (`.1`–`.199`) free for infrastructure (router, JACE, workstation, etc.). Verify scripts use `start_octet + offset` dynamically and follow automatically.

**Jake's action:** add `192.168.100.200` through `192.168.100.206` to the KM-TEST Loopback adapter before any verify script runs. (That's enough for Phase 3: 3 EMon + gas + water + verify client with one spare.) Ship target needs `.200`–`.228` full range.

### Flag D — Device count typo (minor, RESOLVED)

Spec 01 §4 prose says "26 BACnet/IP devices total." Spec 02 §1 table sums to 28 (3+1+1+3+20). The number in spec 01 §4 is a typo and should read "28." No code impact.

## Open Phase 2 items tracked in `ops/action-items.md`

- Spec 01 and spec 02 need in-place amendment to reflect Flags A–D. Not blocking code work.
- Phase 6 (ship packaging: `run.bat`, `README.md`, zip artifact, venv bootstrap) must happen before deadline 2026-04-20. Slated for Session C, Friday 2026-04-17.
- `scripts/verify_meter_a.py` is a Phase 1 single-meter precursor superseded by `verify_meters_abc.py`. Not on the Phase 2 cleanup list, so retained and flagged — decide at Session C whether to delete or keep as historical artifact.
- Dev box runs Python 3.14.3; ship target is 3.12. BAC0 `2025.9.15` works on both. No action unless compatibility issue surfaces in the venv round-trip test.
