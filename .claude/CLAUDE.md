# CLAUDE.md — BACnet Bounty

## What this is
Portable BACnet/IP building simulator. Ships as a zip to a co-worker who stands it up on a Windows machine and integrates the simulated devices into a Tridium Niagara JACE station for a customer-facing Reflow dashboard demo. 32K sf suburban Michigan office building model; 28 BACnet/IP devices (3 electric meters + 1 gas + 1 water + 3 AHUs + 20 VAVs); steady-state with realistic daily/seasonal patterns. The simulator's job ends at the BACnet wire.

## Source of truth
Three spec docs live in `.claude/references/`, read in order:
1. `01_BACnet_Bounty_Architecture_and_Scope.md` — product boundary, device network, simulation model
2. `02_BACnet_Bounty_Device_and_Points_Reference.md` — device metadata, point lists, magnitudes
3. `03_BACnet_Bounty_Phase1_Handoff_Resolutions.md` — **supersedes** 01/02 where they conflict

Phase 2 session added a supplementary resolution at `.claude/references/04_BACnet_Bounty_Phase2_Resolutions.md` covering the stack choice (BAC0, not bacpypes3) and instance-ID scheme (6-digit category-prefixed, not 3-digit). Treat 04 as an extension of 03.

## Architectural invariants — do not violate
1. **Five device classes total**: `EmonClass3200`, `OniconF5500Gas`, `OniconF3500Water`, `AHU`, `VAV`. Don't add more. Don't split existing ones.
2. **Physics lives in pure functions** (`simulator/site_model.py` and future `ahu_physics` / `vav_physics` modules). Device classes are thin BACnet wrappers that call physics each tick and ship the resulting point values. No physics inside device classes.
3. **Per-instance uniqueness is config-driven** — offsets, phase shifts, position tags ("perimeter" / "interior"). Never copy-paste a device class to vary behavior.
4. **Config lives in `site_config.json`** (single file). The 20 VAV rows will look long and that's fine — Jake is the only person who reads them.
5. **One process, one `simulator/__main__.py` entry.** No multi-process fallbacks.
6. **Port 47808 only. One IP per device. Sequential IPs on the loopback.**

## Current tree layout (root-level, not `tools/simulator/`)
```
bacnet-bounty/
├── simulator/                   Python package (the shipping artifact)
│   ├── __main__.py              entry: `py -m simulator`
│   ├── config.py                strict loader for site_config.json
│   ├── logging_config.py        console INFO + rotating file DEBUG
│   ├── site_model.py            pure-function physics; tick-driven
│   └── devices/                 thin BACnet wrappers (one class per device kind)
│       └── emon.py              E-Mon Class 3200 (3 instances: A/B/C)
├── scripts/                     verification scripts (dev-time only, not shipped)
├── reference/                   kept legacy code as pattern reference for AHU/VAV work
├── ops/                         session logs, sprint tracker, action items
├── logs/                        runtime output (gitignored)
├── site_config.json             all tunables
├── requirements.txt             pinned BAC0
└── README.md
```

## Quality bar
"Plausible enough that nobody at the demo says 'that number's wrong.'" Do not chase the ±20% spec target. Rough realism is enough. If stakeholders ask for tighter trends later, that's a follow-up tuning session (Phase 7, post-ship).

## Dependencies
- **BAC0** (pinned `==2025.9.15`) — BACnet/IP stack. Wraps BACpypes3 under the hood.
- **Python 3.12+** (dev box currently 3.14; ship target 3.12 per spec 01 §8).
- No numpy, no pandas. Keep the zip small.

## Key conventions

### Port 47808 only
Niagara discovery only works on 47808. Use sequential IPs via the KM-TEST Loopback adapter for multiple simulated devices.

### Loopback adapter (KM-TEST)
Ship config uses `base_ip=192.168.100.`, `start_octet=200`. Devices bind to `.200`–`.227`. One additional IP above the top (`.228`) is the Workbench / verification-client reservation — simulator must NOT bind there.

Jake adds IPs to the loopback manually before launch:
```
netsh interface ipv4 add address "Ethernet 11" 192.168.100.200 255.255.255.0
... (repeat for each IP in range)
```

### Instance ID scheme (6-digit, category-prefixed)
Per resolution doc 04:
- `1xxxxx` — electric meters (`100001`/`100002`/`100003` = A/B/C)
- `11xxxx` — gas (`110001`)
- `12xxxx` — water (`120001`)
- `2xxxxx` — AHUs (`200001`/`200002`/`200003`)
- `3xxxxx` — VAVs (`300001`–`300020`)

Rationale: realistic for production JACE-discovered networks; partitioning by prefix gives co-worker clean category visibility in Niagara's discovery list. Supersedes spec 02's 3-digit example.

### Always kill and restart after code changes
No need to ask — kill existing simulator process, restart fresh. Exception: user explicitly says keep it running.

### Launch detached
```bash
nohup py -m simulator > logs/simulator.log 2>&1 &
```
Don't use `run_in_background` — causes stale task notifications. Use timeout instead.

## Verification pattern
Verification scripts live under `scripts/`, one per phase slice. Each script:
1. Binds all devices in the slice to their loopback IPs
2. Spins up a BAC0 client on the Workbench-reserved IP
3. Forces the SiteModel to known timestamps (winter-noon, summer-afternoon, etc.)
4. Reads present-values off the wire and asserts them against hard invariants
5. Exits `0` on all-pass, `1` on any-fail

Reference: `scripts/verify_meters_abc.py`.
