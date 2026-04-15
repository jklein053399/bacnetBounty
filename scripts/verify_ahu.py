"""Verify the 3 AHU devices on the wire.

Launches AHU_1 (single-zone), AHU_2, AHU_3 (both VAV) on their own IPs.
Forces SiteModel to winter and summer weekday afternoons. Reads every point
from each AHU via BACnet, validates against the point-list in spec 02 §5
with doc 04 Flag E overrides (AV/BV for commandable points).

Pattern follows scripts/verify_meters_abc.py and scripts/verify_gas_water.py.

Run from repo root:
    py scripts/verify_ahu.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Windows cp1252 default stdout can't encode some common chars (≈ ± × etc).
# Reconfigure to utf-8 with replace fallback so print() never crashes on a
# unicode char slipping into an f-string. Python 3.7+.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import BAC0

from simulator.config import load_config
from simulator.site_model import SiteModel
from simulator.devices.ahu import AHU

BAC0.log_level("silence")


AHU_SPECS = [
    {"device_id": 200001, "name": "AHU_1", "ip_offset": 5, "ahu_index": 0},
    {"device_id": 200002, "name": "AHU_2", "ip_offset": 6, "ahu_index": 1},
    {"device_id": 200003, "name": "AHU_3", "ip_offset": 7, "ahu_index": 2},
]

CLIENT_OFFSET = 8  # top of 8-device Phase 4 slice (3 EMon + gas + water + 3 AHUs)


async def read_ai(client, ip: str, port: int, instance: int) -> float:
    return float(await client.read(f"{ip}:{port} analogInput {instance} presentValue"))


async def read_av(client, ip: str, port: int, instance: int) -> float:
    return float(await client.read(f"{ip}:{port} analogValue {instance} presentValue"))


async def read_bi(client, ip: str, port: int, instance: int) -> str:
    return str(await client.read(f"{ip}:{port} binaryInput {instance} presentValue"))


async def read_bv(client, ip: str, port: int, instance: int) -> str:
    return str(await client.read(f"{ip}:{port} binaryValue {instance} presentValue"))


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

    # ----- Build AHUs -----
    ahus: list = []
    for spec in AHU_SPECS:
        ip = f"{cfg.network.base_ip}{cfg.network.start_octet + spec['ip_offset']}"
        ahu_cfg = cfg.ahus[spec["ahu_index"]]
        dev = AHU(
            device_id=spec["device_id"],
            device_name=spec["name"],
            local_ip=ip,
            subnet_mask_prefix=cfg.network.subnet_mask_prefix,
            bacnet_port=cfg.network.bacnet_port,
            site_model=site,
            ahu_config=ahu_cfg,
            ahu_index=spec["ahu_index"],
        )
        dev.update()
        ahus.append((dev, ip, spec, ahu_cfg))
        print(f"  bound {spec['name']} @ {ip}:{cfg.network.bacnet_port} (kind={ahu_cfg.kind})")

    # ----- Client -----
    client_ip = f"{cfg.network.base_ip}{cfg.network.start_octet + CLIENT_OFFSET}"
    print(f"  client on {client_ip}")
    client = BAC0.lite(
        ip=f"{client_ip}/{cfg.network.subnet_mask_prefix}",
        port=cfg.network.bacnet_port,
        deviceId=999997,
        localObjName="VerifyClientAHU",
    )
    await asyncio.sleep(2.0)

    port = cfg.network.bacnet_port

    # ----- Bind check: read every point on every AHU -----
    print()
    print("=" * 66)
    print("Bind check: all 18 points × 3 AHUs = 54 reads")
    print("=" * 66)

    try:
        for dev, ip, spec, ahu_cfg in ahus:
            # 8 AIs
            for inst in range(1, 9):
                await read_ai(client, ip, port, inst)
            # 6 AVs
            for inst in range(1, 7):
                await read_av(client, ip, port, inst)
            # 2 BIs
            await read_bi(client, ip, port, 1)
            await read_bi(client, ip, port, 2)
            # 1 BV
            await read_bv(client, ip, port, 1)
        OK("All 54 points readable across 3 AHUs")
    except Exception as e:
        FAIL("Bind/read failed", str(e))
        try: client.disconnect()
        except Exception: pass
        for dev, *_ in ahus: dev.close()
        return 1

    # ----- Summer check: occupied cooling -----
    print()
    print("=" * 66)
    print("Summer check: Jul 21 2026, 15:00 (occupied, cooling active)")
    print("=" * 66)
    summer = datetime(2026, 7, 21, 15, 0, 0)
    for _ in range(5):
        site.tick(summer)
        for dev, *_ in ahus: dev.update()
    s = site.state
    print(f"  Model: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f} "
          f"cool_frac={s.cooling_load_fraction:.2f} SAT_targets={s.ahu_sat_f[0]:.1f}/{s.ahu_sat_f[1]:.1f}/{s.ahu_sat_f[2]:.1f}")
    await asyncio.sleep(0.5)

    for dev, ip, spec, ahu_cfg in ahus:
        sat = await read_ai(client, ip, port, 1)
        sat_sp = await read_av(client, ip, port, 1)
        oat = await read_ai(client, ip, port, 4)
        power = await read_ai(client, ip, port, 8)
        vfd = await read_av(client, ip, port, 3)
        fan_status = await read_bi(client, ip, port, 1)
        fan_cmd = await read_bv(client, ip, port, 1)
        cool_stage = await read_av(client, ip, port, 6)
        heat_valve = await read_av(client, ip, port, 5)
        print(f"  {spec['name']}: SAT={sat:.1f}F SP={sat_sp:.0f}F kW={power:.1f} VFD={vfd:.0f}% "
              f"cool={cool_stage:.0f}% heat={heat_valve:.0f}% fan={fan_status}/{fan_cmd}")

        # SAT should be within ±10F of setpoint (loose, not commissioning-tuned)
        if abs(sat - sat_sp) <= 10.0:
            OK(f"{spec['name']} summer SAT within ±10F of setpoint ({sat:.1f} vs {sat_sp:.0f})")
        else:
            FAIL(f"{spec['name']} summer SAT drift too large ({sat:.1f} vs {sat_sp:.0f})")

        # OAT should match site OAT exactly (mirror)
        if abs(oat - s.oat_f) < 0.1:
            OK(f"{spec['name']} OAT mirrors site OAT ({oat:.1f}F)")
        else:
            FAIL(f"{spec['name']} OAT = {oat:.1f}F, site OAT = {s.oat_f:.1f}F (expected mirror)")

        # Fan should be on when occupied
        if fan_status == "active" and fan_cmd == "active":
            OK(f"{spec['name']} fan running (status=cmd=active)")
        else:
            FAIL(f"{spec['name']} fan not running during occupied hours (status={fan_status} cmd={fan_cmd})")

        # Cooling stage should be active in summer
        if cool_stage > 5.0:
            OK(f"{spec['name']} cooling active ({cool_stage:.0f}%)")
        else:
            FAIL(f"{spec['name']} cooling inactive in summer ({cool_stage:.0f}%)")

        # Heating valve should be off in summer
        if heat_valve < 1.0:
            OK(f"{spec['name']} heating valve closed in summer ({heat_valve:.1f}%)")
        else:
            FAIL(f"{spec['name']} heating valve open in summer ({heat_valve:.0f}%)")

        # AHU power should be > 0.5 kW when occupied (fan minimum load)
        if power > 0.5:
            OK(f"{spec['name']} real power > 0.5 kW during occupied hours ({power:.1f} kW)")
        else:
            FAIL(f"{spec['name']} real power too low during occupied hours ({power:.2f} kW)")

    # ----- Winter check: occupied heating -----
    print()
    print("=" * 66)
    print("Winter check: Jan 21 2026, 13:00 (occupied, heating active)")
    print("=" * 66)
    winter = datetime(2026, 1, 21, 13, 0, 0)
    for _ in range(5):
        site.tick(winter)
        for dev, *_ in ahus: dev.update()
    s = site.state
    print(f"  Model: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f} "
          f"heat_frac={s.heating_load_fraction:.2f} SAT_targets={s.ahu_sat_f[0]:.1f}/{s.ahu_sat_f[1]:.1f}/{s.ahu_sat_f[2]:.1f}")
    await asyncio.sleep(0.5)

    for dev, ip, spec, ahu_cfg in ahus:
        sat = await read_ai(client, ip, port, 1)
        sat_sp = await read_av(client, ip, port, 1)
        cool_stage = await read_av(client, ip, port, 6)
        heat_valve = await read_av(client, ip, port, 5)

        if 60.0 <= sat_sp <= 70.0:
            OK(f"{spec['name']} winter SAT setpoint in heating range ({sat_sp:.0f}F)")
        else:
            FAIL(f"{spec['name']} winter SAT setpoint out of heating range ({sat_sp:.0f}F, expected ~65)")

        if cool_stage < 1.0:
            OK(f"{spec['name']} cooling off in winter ({cool_stage:.1f}%)")
        else:
            FAIL(f"{spec['name']} cooling active in winter ({cool_stage:.0f}%)")

        if heat_valve > 5.0:
            OK(f"{spec['name']} heating valve active in winter ({heat_valve:.0f}%)")
        else:
            FAIL(f"{spec['name']} heating valve inactive in winter ({heat_valve:.1f}%)")

    # ----- Teardown -----
    print()
    try: client.disconnect()
    except Exception: pass
    for dev, *_ in ahus: dev.close()

    print("=" * 66)
    print(f"Result: {passes} passed, {fails} failed")
    print("=" * 66)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
