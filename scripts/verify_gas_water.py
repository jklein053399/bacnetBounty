"""Verify ONICON gas + water meters on the wire.

Launches both meters on their own IPs. Forces SiteModel to winter and
summer weekday afternoons, plus occupied/unoccupied water readings.
Reads Flow_Rate and Totalizer via BACnet each time.

Validates:
  - Both devices bind and are readable
  - Flow rates are non-negative at both winter and summer
  - Totalizers are monotonically increasing over ~60 seconds of ticking
  - Winter gas SCFH > summer gas SCFH (AHU preheat season check)
  - Occupied water GPM > unoccupied water GPM (schedule-driven check)

Pattern follows scripts/verify_meters_abc.py.

Run from repo root:
    py scripts/verify_gas_water.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Windows cp1252 default stdout can't encode some common chars. Reconfigure
# so print() never crashes on a unicode char in an f-string. Python 3.7+.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import BAC0

from simulator.config import load_config
from simulator.site_model import SiteModel
from simulator.devices.onicon_gas import OniconF5500Gas
from simulator.devices.onicon_water import OniconF3500Water

BAC0.log_level("silence")


# ip_offsets match simulator/__main__.py DEVICE_MANIFEST for gas/water.
# Client binds at top of the 5-device block (offset 5 = meters A/B/C + gas + water).
GAS_OFFSET = 3
WATER_OFFSET = 4
CLIENT_OFFSET = 5  # top of Phase 3 slice


async def read_ai(client, device_ip: str, port: int, instance: int) -> float:
    return float(await client.read(
        f"{device_ip}:{port} analogInput {instance} presentValue"
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

    # ----- Build gas + water devices -----
    gas_ip = f"{cfg.network.base_ip}{cfg.network.start_octet + GAS_OFFSET}"
    water_ip = f"{cfg.network.base_ip}{cfg.network.start_octet + WATER_OFFSET}"

    gas = OniconF5500Gas(
        device_id=110001,
        device_name="GAS_METER",
        local_ip=gas_ip,
        subnet_mask_prefix=cfg.network.subnet_mask_prefix,
        bacnet_port=cfg.network.bacnet_port,
        site_model=site,
    )
    gas.update()
    print(f"  bound GAS_METER   @ {gas_ip}:{cfg.network.bacnet_port}")

    water = OniconF3500Water(
        device_id=120001,
        device_name="WATER_METER",
        local_ip=water_ip,
        subnet_mask_prefix=cfg.network.subnet_mask_prefix,
        bacnet_port=cfg.network.bacnet_port,
        site_model=site,
    )
    water.update()
    print(f"  bound WATER_METER @ {water_ip}:{cfg.network.bacnet_port}")

    # ----- Client -----
    client_ip = f"{cfg.network.base_ip}{cfg.network.start_octet + CLIENT_OFFSET}"
    print(f"  client on {client_ip}")
    client = BAC0.lite(
        ip=f"{client_ip}/{cfg.network.subnet_mask_prefix}",
        port=cfg.network.bacnet_port,
        deviceId=999998,
        localObjName="VerifyClientGW",
    )
    await asyncio.sleep(1.5)

    # ----- Bind check: read each AI once -----
    print()
    print("=" * 66)
    print("Bind check: all 6 AIs readable")
    print("=" * 66)
    try:
        gas_flow_0   = await read_ai(client, gas_ip, cfg.network.bacnet_port, 1)
        gas_tot_0    = await read_ai(client, gas_ip, cfg.network.bacnet_port, 2)
        gas_temp_0   = await read_ai(client, gas_ip, cfg.network.bacnet_port, 3)
        water_flow_0 = await read_ai(client, water_ip, cfg.network.bacnet_port, 1)
        water_tot_0  = await read_ai(client, water_ip, cfg.network.bacnet_port, 2)
        water_temp_0 = await read_ai(client, water_ip, cfg.network.bacnet_port, 3)
        OK(f"All 6 AIs readable (gas F/T/Temp = {gas_flow_0:.1f}/{gas_tot_0:.2f}/{gas_temp_0:.1f}; water F/T/Temp = {water_flow_0:.2f}/{water_tot_0:.2f}/{water_temp_0:.1f})")
    except Exception as e:
        FAIL("AI read failed", str(e))
        try:
            client.disconnect()
        except Exception:
            pass
        gas.close(); water.close()
        return 1

    # ----- Winter gas check: Jan 21, 1 PM -----
    print()
    print("=" * 66)
    print("Winter check: Jan 21 2026, 13:00 (occupied, heating active)")
    print("=" * 66)
    winter = datetime(2026, 1, 21, 13, 0, 0)
    for _ in range(5):
        site.tick(winter)
        gas.update(); water.update()
    s = site.state
    print(f"  Model: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f} "
          f"gas_heat_frac={s.gas_heating_fraction:.2f} scfh={s.gas_scfh:.0f}")
    await asyncio.sleep(0.5)

    winter_gas_flow = await read_ai(client, gas_ip, cfg.network.bacnet_port, 1)
    print(f"  Wire gas Flow_Rate = {winter_gas_flow:.1f} SCFH")

    if winter_gas_flow >= 0:
        OK(f"Winter gas flow non-negative ({winter_gas_flow:.1f} SCFH)")
    else:
        FAIL(f"Winter gas flow negative ({winter_gas_flow:.1f} SCFH)")

    # ----- Summer gas check: Jul 21, 3 PM -----
    print()
    print("=" * 66)
    print("Summer check: Jul 21 2026, 15:00 (occupied, no heating)")
    print("=" * 66)
    summer = datetime(2026, 7, 21, 15, 0, 0)
    for _ in range(5):
        site.tick(summer)
        gas.update(); water.update()
    s = site.state
    print(f"  Model: OAT={s.oat_f:.1f}F occ={s.occupancy_fraction:.2f} "
          f"gas_heat_frac={s.gas_heating_fraction:.2f} scfh={s.gas_scfh:.0f}")
    await asyncio.sleep(0.5)

    summer_gas_flow = await read_ai(client, gas_ip, cfg.network.bacnet_port, 1)
    print(f"  Wire gas Flow_Rate = {summer_gas_flow:.1f} SCFH")

    if summer_gas_flow >= 0:
        OK(f"Summer gas flow non-negative ({summer_gas_flow:.1f} SCFH)")
    else:
        FAIL(f"Summer gas flow negative ({summer_gas_flow:.1f} SCFH)")

    if winter_gas_flow > summer_gas_flow:
        OK(f"Winter gas > summer gas ({winter_gas_flow:.0f} > {summer_gas_flow:.0f} SCFH)")
    else:
        FAIL(f"Winter gas NOT > summer gas ({winter_gas_flow:.0f} vs {summer_gas_flow:.0f} SCFH)")

    # ----- Occupied vs unoccupied water -----
    print()
    print("=" * 66)
    print("Water occupancy check: weekday 13:00 (occupied) vs 02:00 (unoccupied)")
    print("=" * 66)
    # Average water flow across several ticks to smooth the burst-noise
    async def avg_water_flow(ts: datetime, n: int = 10) -> float:
        readings: list[float] = []
        for _ in range(n):
            site.tick(ts)
            water.update()
            readings.append(await read_ai(client, water_ip, cfg.network.bacnet_port, 1))
        return sum(readings) / len(readings)

    occupied_ts = datetime(2026, 4, 15, 13, 0, 0)
    unoccupied_ts = datetime(2026, 4, 15, 2, 0, 0)
    occ_water = await avg_water_flow(occupied_ts, n=10)
    unocc_water = await avg_water_flow(unoccupied_ts, n=10)
    print(f"  avg occupied   water flow: {occ_water:.3f} GPM")
    print(f"  avg unoccupied water flow: {unocc_water:.3f} GPM")

    if occ_water > unocc_water:
        OK(f"Occupied water > unoccupied water ({occ_water:.2f} > {unocc_water:.2f} GPM)")
    else:
        FAIL(f"Occupied water NOT > unoccupied water ({occ_water:.2f} vs {unocc_water:.2f} GPM)")

    # ----- Totalizer monotonicity -----
    print()
    print("=" * 66)
    print("Totalizer monotonicity check: ~60 seconds of ticking")
    print("=" * 66)
    # Use the last-state totalizer as the starting baseline
    gas_tot_start   = await read_ai(client, gas_ip,   cfg.network.bacnet_port, 2)
    water_tot_start = await read_ai(client, water_ip, cfg.network.bacnet_port, 2)
    print(f"  start: gas_scf={gas_tot_start:.2f}, water_gal={water_tot_start:.2f}")

    # Tick for ~60 seconds of simulated time. We feed monotonically increasing
    # timestamps so the wall-clock dt the model uses for kWh/SCF/gal integration
    # advances properly. Sleep between calls isn't needed — the model uses the
    # datetime arg, not wall time.
    base_ts = occupied_ts  # occupied -> non-zero flow -> totalizer should climb
    from datetime import timedelta
    for step in range(1, 7):  # 6 x 10-sec ticks = 60 sim-seconds
        ts = base_ts + timedelta(seconds=10 * step)
        site.tick(ts)
        gas.update(); water.update()

    gas_tot_end   = await read_ai(client, gas_ip,   cfg.network.bacnet_port, 2)
    water_tot_end = await read_ai(client, water_ip, cfg.network.bacnet_port, 2)
    print(f"  end:   gas_scf={gas_tot_end:.2f}, water_gal={water_tot_end:.2f}")

    if gas_tot_end > gas_tot_start:
        OK(f"Gas totalizer monotonic (+{gas_tot_end - gas_tot_start:.2f} SCF in 60s)")
    else:
        FAIL(f"Gas totalizer NOT monotonic ({gas_tot_start:.2f} -> {gas_tot_end:.2f})")

    if water_tot_end > water_tot_start:
        OK(f"Water totalizer monotonic (+{water_tot_end - water_tot_start:.2f} gal in 60s)")
    else:
        FAIL(f"Water totalizer NOT monotonic ({water_tot_start:.2f} -> {water_tot_end:.2f})")

    # ----- Teardown -----
    print()
    try:
        client.disconnect()
    except Exception:
        pass
    gas.close()
    water.close()

    print("=" * 66)
    print(f"Result: {passes} passed, {fails} failed")
    print("=" * 66)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
