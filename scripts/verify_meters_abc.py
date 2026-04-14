"""Verify all three E-Mon meters on the wire, with nesting + reheat-delta check.

Launches Meter A, B, C simultaneously on their own IPs. Forces the SiteModel
to a winter weekday afternoon (Jan 21, 1 PM) and a summer weekday afternoon
(Jul 21, 3 PM), and reads Real_power from each meter via BACnet each time.

Validates:
  - All three devices bind and are readable
  - Nesting holds on the wire at both datetimes: kW_A >= kW_B >= kW_C
  - Winter: B - C > 30 kW  (electric reheat active)
  - Summer: B - C < 5 kW   (reheat dormant, B approx equal C)

Matches handoff Flag-1 resolution: "B and C meaningfully different by ~60 kW
on a cold day with reheat active. On a mild/warm day with no reheat, B = C."

Run from repo root:
    py scripts/verify_meters_abc.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import BAC0

from simulator.config import load_config
from simulator.site_model import SiteModel
from simulator.devices.emon import EmonClass3200

BAC0.log_level("silence")

METER_SPECS = [
    {"device_id": 100001, "name": "ELECTRICAL_METER_A", "ip_offset": 0, "scope": "A"},
    {"device_id": 100002, "name": "ELECTRICAL_METER_B", "ip_offset": 1, "scope": "B"},
    {"device_id": 100003, "name": "ELECTRICAL_METER_C", "ip_offset": 2, "scope": "C"},
]


async def read_kw(client, device_ip: str, port: int, device_id: int) -> float:
    return float(await client.read(
        f"{device_ip}:{port} analogInput 5 presentValue"
    ))


async def main() -> int:
    cfg = load_config("site_config.json")
    fails = 0
    passes = 0

    def OK(msg: str) -> None:
        nonlocal passes; passes += 1
        print(f"  PASS  {msg}")

    def FAIL(msg: str, detail: str = "") -> None:
        nonlocal fails; fails += 1
        print(f"  FAIL  {msg}{('  -- ' + detail) if detail else ''}")

    site = SiteModel(cfg)
    site.tick(datetime.now())

    # ----- Build all 3 meters -----
    meters: list = []
    for spec in METER_SPECS:
        ip = f"{cfg.network.base_ip}{cfg.network.start_octet + spec['ip_offset']}"
        m = EmonClass3200(
            device_id=spec["device_id"],
            device_name=spec["name"],
            local_ip=ip,
            subnet_mask_prefix=cfg.network.subnet_mask_prefix,
            bacnet_port=cfg.network.bacnet_port,
            scope=spec["scope"],
            site_model=site,
        )
        m.update()
        meters.append((m, ip, spec))
        print(f"  bound {spec['name']} @ {ip}:{cfg.network.bacnet_port}")

    # ----- Start client on Workbench reservation (top of block) -----
    client_ip_offset = len(METER_SPECS)  # top of range
    client_ip = f"{cfg.network.base_ip}{cfg.network.start_octet + client_ip_offset}"
    print(f"  client on {client_ip}")
    client = BAC0.lite(
        ip=f"{client_ip}/{cfg.network.subnet_mask_prefix}",
        port=cfg.network.bacnet_port,
        deviceId=999999,
        localObjName="VerifyClient",
    )
    await asyncio.sleep(1.5)

    # ----- Winter check: Jan 21, 1 PM weekday -----
    print()
    print("=" * 66)
    print("Winter check: Jan 21 2026, 13:00 (occupied, heating active)")
    print("=" * 66)
    winter = datetime(2026, 1, 21, 13, 0, 0)
    # Advance the model a few steps at this datetime so state is stable and
    # the totalizers have some accumulation
    for _ in range(5):
        site.tick(winter)
        for m, _ip, _spec in meters:
            m.update()
    # Print the model-internal values (ground truth)
    s = site.state
    print(f"  Model state: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f} "
          f"heat_frac={s.heating_load_fraction:.2f}")
    print(f"  Model kW:    A={s.meter_a_kw:.1f}  B={s.meter_b_kw:.1f}  C={s.meter_c_kw:.1f}  "
          f"B-C={s.meter_b_kw - s.meter_c_kw:.1f}")
    await asyncio.sleep(0.5)

    winter_wire: dict[str, float] = {}
    for m, ip, spec in meters:
        kw = await read_kw(client, ip, cfg.network.bacnet_port, spec["device_id"])
        winter_wire[spec["scope"]] = kw
        print(f"  Wire {spec['name']}: Real_power = {kw:.2f} kW")

    a, b, c = winter_wire["A"], winter_wire["B"], winter_wire["C"]
    if a >= b >= c:
        OK(f"Nesting A>=B>=C holds ({a:.1f} >= {b:.1f} >= {c:.1f})")
    else:
        FAIL(f"Nesting broken: A={a:.1f} B={b:.1f} C={c:.1f}")

    bc_delta = b - c
    if bc_delta > 30.0:
        OK(f"Winter B-C = {bc_delta:.1f} kW (reheat active, expected > 30)")
    else:
        FAIL(f"Winter B-C = {bc_delta:.1f} kW (expected > 30 kW of electric reheat)")

    # ----- Summer check: Jul 21, 3 PM weekday -----
    print()
    print("=" * 66)
    print("Summer check: Jul 21 2026, 15:00 (occupied, cooling active, no reheat)")
    print("=" * 66)
    summer = datetime(2026, 7, 21, 15, 0, 0)
    for _ in range(5):
        site.tick(summer)
        for m, _ip, _spec in meters:
            m.update()
    s = site.state
    print(f"  Model state: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f} "
          f"cool_frac={s.cooling_load_fraction:.2f} heat_frac={s.heating_load_fraction:.2f}")
    print(f"  Model kW:    A={s.meter_a_kw:.1f}  B={s.meter_b_kw:.1f}  C={s.meter_c_kw:.1f}  "
          f"B-C={s.meter_b_kw - s.meter_c_kw:.1f}")
    await asyncio.sleep(0.5)

    summer_wire: dict[str, float] = {}
    for m, ip, spec in meters:
        kw = await read_kw(client, ip, cfg.network.bacnet_port, spec["device_id"])
        summer_wire[spec["scope"]] = kw
        print(f"  Wire {spec['name']}: Real_power = {kw:.2f} kW")

    a, b, c = summer_wire["A"], summer_wire["B"], summer_wire["C"]
    if a >= b >= c:
        OK(f"Nesting A>=B>=C holds ({a:.1f} >= {b:.1f} >= {c:.1f})")
    else:
        FAIL(f"Nesting broken: A={a:.1f} B={b:.1f} C={c:.1f}")

    bc_delta = abs(b - c)
    if bc_delta < 5.0:
        OK(f"Summer B-C = {bc_delta:.2f} kW (reheat dormant, expected < 5)")
    else:
        FAIL(f"Summer B-C = {bc_delta:.2f} kW (expected ~0 when reheat off)")

    # ----- Teardown -----
    print()
    try:
        client.disconnect()
    except Exception:
        pass
    for m, _ip, _spec in meters:
        m.close()

    print("=" * 66)
    print(f"Result: {passes} passed, {fails} failed")
    print("=" * 66)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
