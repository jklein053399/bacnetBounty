# Project Context — BACnet Bounty

*Syncs with web-side Claude.ai project knowledge base. Keep accurate.*

---

## Project Identity

- **Name:** BACnet Bounty
- **Type:** Portable BACnet/IP building simulator (zip bundle)
- **Extracted from:** `C:/Programs/Controls-Suite/tools/simulator/` on 2026-04-14
- **Repo:** `C:/Programs/Bacnet-Bounty` (GitHub: `jklein053399/bacnetBounty`)
- **Created:** 2026-04-14
- **Ship target:** 2026-04-20 (Monday)

## Project Status

- **Phase:** 3 of 7 complete as of 2026-04-15
- **Priority:** Critical path to Monday ship
- **Product version:** Pre-1.0 (Phase 1 spec = "ship pass"; Phase 7 = tuning pass post-ship)

## Current Goal

Build a zip-shipped BACnet/IP simulator that a co-worker can unzip on Windows, double-click `run.bat`, and have 28 BACnet devices discoverable by a Tridium Niagara JACE. Downstream Reflow dashboards consume the BACnet present-values. Simulator's job ends at the BACnet wire.

**Target building:** 32K sf Michigan office. **Device manifest:** 3× E-Mon Class 3200 electric meters (A/B/C nested scopes), 1× ONICON F-5500 gas, 1× ONICON F-3500 water, 3× generic AHUs, 20× generic VAVs.

## Architectural Invariants (non-negotiable)

1. Five device classes total: `EmonClass3200`, `OniconF5500Gas`, `OniconF3500Water`, `AHU`, `VAV`
2. Physics lives in pure-function modules (`site_model.py`, future `ahu_physics.py`, future `vav_physics.py`); device classes are thin BACnet wrappers
3. Per-instance uniqueness is config-driven (offsets, phase shifts, position tags) — no copy-pasted classes
4. Single `site_config.json` for all tunables
5. One `simulator/__main__.py` entry; no multi-process fallbacks
6. Port 47808 only; one IP per device; sequential IPs on loopback

## Stack

- **BAC0** (pinned `==2025.9.15`) — wraps bacpypes3 internally
- **Python 3.12** target; 3.14 works on dev box
- No numpy, no pandas. Zero external deps beyond BAC0 + its transitive

## Source-of-Truth Docs (in `.claude/references/`)

Precedence rule: higher-numbered doc wins when they conflict.

1. `01_BACnet_Bounty_Architecture_and_Scope.md` — product boundary, device network, simulation model
2. `02_BACnet_Bounty_Device_and_Points_Reference.md` — point lists, magnitudes, config schema
3. `03_BACnet_Bounty_Phase1_Handoff_Resolutions.md` — pre-Phase-1 flag resolutions (electric reheat, peak demand fixed windows, energy-hog calibration)
4. `04_BACnet_Bounty_Phase2_Resolutions.md` — BAC0 authoritative, 6-digit device IDs, start_octet=200, device count typo

## Session History Summary

- **2026-04-14 S1** — extraction from Controls-Suite via `git subtree split`; simulator decoupled from parent
- **2026-04-14 S2** — Phase 1 vertical slice: scaffold + 3 E-Mon meters verified on wire (commit `e7564b3`)
- **2026-04-15 S3 (A)** — Phase 2 consolidation + Phase 3 ONICON gas/water verified on wire (commits `1056763` + `691daf0` + `f645a00`). 5 devices on wire, 11/11 verify checks green.

## Decision Log

- 2026-04-14: Simulator extracted as standalone product; Controls-Suite flags parent `tools/simulator/` as DEPRECATED but retains code
- 2026-04-14: Use case pivoted to portable zip bundle for co-worker + Niagara JACE dashboard demo (not generic BMS tool testing)
- 2026-04-14: Electric reheat (not HW reheat) on VAVs — makes Meter B vs C meaningfully different; drops gas peak from 3000 to 500 SCFH; doc 03
- 2026-04-14: 6-digit category-prefixed device IDs (100001+, 110001, 120001, 200001+, 300001+) over spec 02's 3-digit example
- 2026-04-15: **BAC0 authoritative over bacpypes3.** Specs 01/02 §9 stale. BAC0 wraps bacpypes3 so protocol is the same; API is BAC0's. Doc 04 Flag A.
- 2026-04-15: `start_octet=200` confirmed; Phase 1 drift to `1` corrected. Doc 04 Flag C.
- 2026-04-15: Legacy cleanup authorized — vendor devices, scenarios/, device-data/, old runners deleted. `reference/` keeps generic AHU/VAV/zone/G36 as pattern input. Supersedes earlier preservation-mode rule.

## Current Tree

```
bacnet-bounty/
├── simulator/              Python package (ship artifact)
├── scripts/                verify_meters_abc.py, verify_gas_water.py, add_loopback_ips.bat
├── reference/              legacy AHU/VAV/zone/G36 physics (Session B pattern input)
├── ops/                    sprint-tracker, action-items, handoffs, work reports
├── .claude/references/     spec docs 01-04 + E-Mon PDF
├── site_config.json        all tunables
├── requirements.txt        BAC0==2025.9.15
└── PROJECT_CONTEXT.md      this file
```

## Notes

- Ship zip excludes: `reference/`, `scripts/`, `ops/`, `.claude/`, `PROJECT_CONTEXT.md`
- Co-worker's adapter name will differ from Jake's dev box (`Bacnet Simulator`) — README must make it a placeholder
- Spec v1.1 consolidation is a post-ship task (see memory `project_post_ship_tasks.md`) — don't pull focus from ship
