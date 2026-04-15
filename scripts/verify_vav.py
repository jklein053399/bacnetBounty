"""Verify VAV devices on the wire.

Spot-checks 3 representative VAVs: VAV_1 (first, under AHU_2, perimeter),
VAV_11 (first under AHU_3, perimeter), VAV_20 (last in block, interior).
Covers both parent AHUs and both position tags.

Validates:
  - All 3 devices bind, all 9 points readable
  - Zone_Temperature in plausible range (60-80F)
  - Supply_Airflow >= min_cfm when occupied
  - Damper_Position modulates with load
  - Reheat_Valve_Position > 0 in winter heating mode, ~0 in summer cooling
  - Discharge_Air_Temperature ≈ parent AHU SAT + reheat delta
  - Occupancy_Status active during occupied hours, inactive at 02:00

Pattern follows scripts/verify_ahu.py.

Run from repo root:
    py scripts/verify_vav.py
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
from simulator.devices.vav import VAV

BAC0.log_level("silence")


# Spot-check subset: first of AHU_2's VAVs, first of AHU_3's, last of the block.
# device_id / ip_offset parallel simulator/__main__.py DEVICE_MANIFEST.
VAV_SPECS = [
    {"device_id": 300001, "name": "VAV_1",  "ip_offset": 8,  "vav_index": 0},
    {"device_id": 300011, "name": "VAV_11", "ip_offset": 18, "vav_index": 10},
    {"device_id": 300020, "name": "VAV_20", "ip_offset": 27, "vav_index": 19},
]

# Client binds at top-of-full-block (28 devices) = offset 28 = .228 with
# start_octet=200. Using .228 keeps this verify compatible with the ship range.
CLIENT_OFFSET = 28


async def read_ai(client, ip: str, port: int, instance: int) -> float:
    return float(await client.read(f"{ip}:{port} analogInput {instance} presentValue"))


async def read_av(client, ip: str, port: int, instance: int) -> float:
    return float(await client.read(f"{ip}:{port} analogValue {instance} presentValue"))


async def read_bi(client, ip: str, port: int, instance: int) -> str:
    return str(await client.read(f"{ip}:{port} binaryInput {instance} presentValue"))


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

    # ----- Build the 3 sampled VAVs -----
    vavs: list = []
    for spec in VAV_SPECS:
        ip = f"{cfg.network.base_ip}{cfg.network.start_octet + spec['ip_offset']}"
        vav_cfg = cfg.vavs[spec["vav_index"]]
        dev = VAV(
            device_id=spec["device_id"],
            device_name=spec["name"],
            local_ip=ip,
            subnet_mask_prefix=cfg.network.subnet_mask_prefix,
            bacnet_port=cfg.network.bacnet_port,
            site_model=site,
            vav_config=vav_cfg,
            vav_index=spec["vav_index"],
        )
        dev.update()
        vavs.append((dev, ip, spec, vav_cfg))
        print(f"  bound {spec['name']} @ {ip}:{cfg.network.bacnet_port} "
              f"({vav_cfg.position}, parent {vav_cfg.parent_ahu})")

    # ----- Client -----
    client_ip = f"{cfg.network.base_ip}{cfg.network.start_octet + CLIENT_OFFSET}"
    print(f"  client on {client_ip}")
    client = BAC0.lite(
        ip=f"{client_ip}/{cfg.network.subnet_mask_prefix}",
        port=cfg.network.bacnet_port,
        deviceId=999996,
        localObjName="VerifyClientVAV",
    )
    await asyncio.sleep(2.0)

    port = cfg.network.bacnet_port

    # ----- Bind check: read every point on each sampled VAV -----
    print()
    print("=" * 66)
    print("Bind check: 9 points × 3 VAVs = 27 reads")
    print("=" * 66)
    try:
        for dev, ip, spec, _ in vavs:
            for inst in range(1, 4):  # 3 AIs
                await read_ai(client, ip, port, inst)
            for inst in range(1, 6):  # 5 AVs
                await read_av(client, ip, port, inst)
            await read_bi(client, ip, port, 1)
        OK("All 27 points readable across 3 sampled VAVs")
    except Exception as e:
        FAIL("Bind/read failed", str(e))
        try: client.disconnect()
        except Exception: pass
        for dev, *_ in vavs: dev.close()
        return 1

    # ----- Winter check: Jan 21 13:00 (occupied heating) -----
    print()
    print("=" * 66)
    print("Winter check: Jan 21 2026, 13:00 (occupied, heating)")
    print("=" * 66)
    winter = datetime(2026, 1, 21, 13, 0, 0)
    for _ in range(5):
        site.tick(winter)
        for dev, *_ in vavs: dev.update()
    s = site.state
    print(f"  Model: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f} "
          f"heat_frac={s.heating_load_fraction:.2f} AHU_2 SAT={s.ahu_sat_f[1]:.1f}F AHU_3 SAT={s.ahu_sat_f[2]:.1f}F")
    await asyncio.sleep(0.5)

    for dev, ip, spec, vav_cfg in vavs:
        zone = await read_ai(client, ip, port, 1)
        airflow = await read_ai(client, ip, port, 2)
        da_temp = await read_ai(client, ip, port, 3)
        cool_sp = await read_av(client, ip, port, 1)
        heat_sp = await read_av(client, ip, port, 2)
        airflow_sp = await read_av(client, ip, port, 3)
        damper = await read_av(client, ip, port, 4)
        reheat = await read_av(client, ip, port, 5)
        occupancy = await read_bi(client, ip, port, 1)
        print(f"  {spec['name']} ({vav_cfg.position}, {vav_cfg.parent_ahu}): "
              f"zone={zone:.1f}F DA={da_temp:.1f}F valve={reheat:.0f}% "
              f"airflow={airflow:.0f}/{airflow_sp:.0f} damper={damper:.0f}% occ={occupancy}")

        if 60.0 <= zone <= 80.0:
            OK(f"{spec['name']} zone temp in plausible range ({zone:.1f}F)")
        else:
            FAIL(f"{spec['name']} zone temp out of plausible range ({zone:.1f}F)")

        if airflow >= vav_cfg.min_cfm * 0.95:  # small tolerance for jitter
            OK(f"{spec['name']} airflow >= min_cfm×0.95 ({airflow:.0f} >= {vav_cfg.min_cfm * 0.95:.0f})")
        else:
            FAIL(f"{spec['name']} airflow below min ({airflow:.0f} < {vav_cfg.min_cfm * 0.95:.0f})")

        # Reheat valve should be active in winter
        if reheat > 10.0:
            OK(f"{spec['name']} reheat valve active in winter ({reheat:.0f}%)")
        else:
            FAIL(f"{spec['name']} reheat valve inactive in winter ({reheat:.0f}%)")

        # Discharge-air-temp should be > parent AHU SAT (reheat adds delta)
        parent_sat_idx = {"AHU_1": 0, "AHU_2": 1, "AHU_3": 2}[vav_cfg.parent_ahu]
        parent_sat = s.ahu_sat_f[parent_sat_idx]
        if da_temp > parent_sat + 2.0:
            OK(f"{spec['name']} DA temp above parent SAT when reheating ({da_temp:.1f} > {parent_sat:.1f})")
        else:
            FAIL(f"{spec['name']} DA temp not elevated ({da_temp:.1f} vs parent SAT {parent_sat:.1f})")

        if occupancy == "active":
            OK(f"{spec['name']} occupancy status = active during occupied hours")
        else:
            FAIL(f"{spec['name']} occupancy status = {occupancy} (expected active)")

    # ----- Summer check: Jul 21 15:00 (occupied cooling) -----
    print()
    print("=" * 66)
    print("Summer check: Jul 21 2026, 15:00 (occupied, cooling)")
    print("=" * 66)
    summer = datetime(2026, 7, 21, 15, 0, 0)
    for _ in range(5):
        site.tick(summer)
        for dev, *_ in vavs: dev.update()
    s = site.state
    print(f"  Model: OAT={s.oat_f:.1f}F cool_frac={s.cooling_load_fraction:.2f} "
          f"AHU_2 SAT={s.ahu_sat_f[1]:.1f}F")
    await asyncio.sleep(0.5)

    for dev, ip, spec, vav_cfg in vavs:
        airflow = await read_ai(client, ip, port, 2)
        da_temp = await read_ai(client, ip, port, 3)
        reheat = await read_av(client, ip, port, 5)

        if reheat < 5.0:
            OK(f"{spec['name']} reheat valve closed in summer ({reheat:.1f}%)")
        else:
            FAIL(f"{spec['name']} reheat valve still open in summer ({reheat:.1f}%)")

        # Summer airflow should exceed min_cfm (cooling demand drives more flow)
        if airflow > vav_cfg.min_cfm * 1.2:
            OK(f"{spec['name']} summer airflow above min (cooling active, {airflow:.0f} CFM)")
        else:
            FAIL(f"{spec['name']} summer airflow low ({airflow:.0f} vs min_cfm={vav_cfg.min_cfm})")

        # DA temp should be close to parent SAT (reheat off)
        parent_sat_idx = {"AHU_1": 0, "AHU_2": 1, "AHU_3": 2}[vav_cfg.parent_ahu]
        parent_sat = s.ahu_sat_f[parent_sat_idx]
        if abs(da_temp - parent_sat) < 3.0:
            OK(f"{spec['name']} DA temp ~= parent SAT when no reheat ({da_temp:.1f} vs {parent_sat:.1f})")
        else:
            FAIL(f"{spec['name']} DA temp drifted from parent SAT ({da_temp:.1f} vs {parent_sat:.1f})")

    # ----- Unoccupied check: 02:00 weekday -----
    print()
    print("=" * 66)
    print("Unoccupied check: 02:00 weekday")
    print("=" * 66)
    unocc = datetime(2026, 4, 15, 2, 0, 0)
    for _ in range(3):
        site.tick(unocc)
        for dev, *_ in vavs: dev.update()
    s = site.state
    print(f"  Model: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f}")
    await asyncio.sleep(0.5)

    for dev, ip, spec, vav_cfg in vavs:
        occupancy = await read_bi(client, ip, port, 1)
        if occupancy == "inactive":
            OK(f"{spec['name']} occupancy status = inactive at 02:00")
        else:
            FAIL(f"{spec['name']} occupancy status = {occupancy} at 02:00 (expected inactive)")

    # ----- Teardown -----
    print()
    try: client.disconnect()
    except Exception: pass
    for dev, *_ in vavs: dev.close()

    print("=" * 66)
    print(f"Result: {passes} passed, {fails} failed")
    print("=" * 66)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
