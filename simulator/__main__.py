"""BACnet Bounty simulator entry point.

Loads site_config.json, instantiates the SiteModel, brings up the BACnet devices
per the manifest, and ticks every N seconds.

Run from repo root:
    py -m simulator
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

import BAC0

from .config import load_config
from .logging_config import setup_logging
from .site_model import SiteModel
from .devices.emon import EmonClass3200
from .devices.onicon_gas import OniconF5500Gas
from .devices.onicon_water import OniconF3500Water


log = logging.getLogger("simulator")


# Device manifest — 6-digit Metro device ID scheme:
#   1xxxxx = electric meters, 11xxxx = gas, 12xxxx = water,
#   2xxxxx = AHUs, 3xxxxx = VAVs.
# ip_offset is the octet offset from network.start_octet in site_config.json.
# Vertical-slice subset (Phase 1 in progress); commented entries come online as
# their device modules land.
DEVICE_MANIFEST: list[dict] = [
    {"kind": "emon",         "device_id": 100001, "name": "ELECTRICAL_METER_A", "ip_offset": 0, "scope": "A"},
    {"kind": "emon",         "device_id": 100002, "name": "ELECTRICAL_METER_B", "ip_offset": 1, "scope": "B"},
    {"kind": "emon",         "device_id": 100003, "name": "ELECTRICAL_METER_C", "ip_offset": 2, "scope": "C"},
    {"kind": "onicon_gas",   "device_id": 110001, "name": "GAS_METER",          "ip_offset": 3},
    {"kind": "onicon_water", "device_id": 120001, "name": "WATER_METER",        "ip_offset": 4},
    # AHUs: "ahu"  200001/200002/200003   ip_offset 5/6/7        (Session B)
    # VAVs: "vav"  300001..300020         ip_offset 8..27        (Session B)
]


async def run():
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site_config.json")
    cfg = load_config(cfg_path)
    setup_logging(cfg.logging)

    # Quiet BAC0's own chatter so our banner stays clean
    BAC0.log_level("error")

    log.info("=" * 66)
    log.info("BACnet Bounty simulator starting")
    log.info(f"Site: {cfg.site.name} ({cfg.site.square_feet:,} sf, {cfg.site.location})")
    log.info(f"Tick: {cfg.simulation.tick_interval_seconds}s, port {cfg.network.bacnet_port}")
    log.info("=" * 66)

    # IP plan banner
    n_devices = len(DEVICE_MANIFEST)
    workbench_ip = f"{cfg.network.base_ip}{cfg.network.start_octet + n_devices}"
    log.info("IP plan (assign these to the 'BACNet Simulator' loopback adapter before startup):")
    for spec in DEVICE_MANIFEST:
        ip = f"{cfg.network.base_ip}{cfg.network.start_octet + spec['ip_offset']}"
        log.info(f"  device    {ip:<18}  [{spec['device_id']}] {spec['name']}")
    log.info(f"  RESERVED  {workbench_ip:<18}  Niagara Workbench / Soft Station — do NOT bind simulator here")
    log.info(f"  Required IPs on loopback: {n_devices + 1} minimum ({n_devices} device + 1 Workbench, top of range).")
    log.info("=" * 66)

    site = SiteModel(cfg)
    site.tick(datetime.now())  # prime

    devices: list = []
    for spec in DEVICE_MANIFEST:
        ip = f"{cfg.network.base_ip}{cfg.network.start_octet + spec['ip_offset']}"
        kind = spec["kind"]
        common_kwargs = dict(
            device_id=spec["device_id"],
            device_name=spec["name"],
            local_ip=ip,
            subnet_mask_prefix=cfg.network.subnet_mask_prefix,
            bacnet_port=cfg.network.bacnet_port,
            site_model=site,
        )
        if kind == "emon":
            dev = EmonClass3200(scope=spec["scope"], **common_kwargs)
            tag = f"E-Mon scope {spec['scope']}"
        elif kind == "onicon_gas":
            dev = OniconF5500Gas(**common_kwargs)
            tag = "ONICON F-5500 gas"
        elif kind == "onicon_water":
            dev = OniconF3500Water(**common_kwargs)
            tag = "ONICON F-3500 water"
        else:
            log.warning(f"Unknown device kind in manifest: {kind!r}")
            continue
        dev.update()
        devices.append(dev)
        log.info(f"  [{spec['device_id']}] {spec['name']:<22} @ {ip}:{cfg.network.bacnet_port} ({tag})")

    log.info(f"{len(devices)} devices online.")
    log.info("Entering tick loop. Ctrl+C to stop.")

    stop = asyncio.Event()

    def _handle_stop(*_):
        log.info("Stop signal received.")
        stop.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_running_loop().add_signal_handler(sig, _handle_stop)
    except (NotImplementedError, AttributeError):
        pass  # Windows asyncio doesn't always support add_signal_handler; Ctrl+C still works

    heartbeat_interval = 60
    last_heartbeat = 0.0
    tick_interval = cfg.simulation.tick_interval_seconds
    loop_count = 0

    try:
        while not stop.is_set():
            now = datetime.now()
            s = site.tick(now)
            for dev in devices:
                dev.update()

            loop_count += 1
            if loop_count == 1 or (now.timestamp() - last_heartbeat) >= heartbeat_interval:
                log.info(
                    f"tick#{loop_count} OAT={s.oat_f:5.1f}F occ={s.occupancy_fraction:.2f} "
                    f"kW_A={s.meter_a_kw:6.1f} kW_B={s.meter_b_kw:6.1f} kW_C={s.meter_c_kw:6.1f} "
                    f"gas={s.gas_scfh:.0f}scfh water={s.water_gpm:.2f}gpm"
                )
                last_heartbeat = now.timestamp()

            try:
                await asyncio.wait_for(stop.wait(), timeout=tick_interval)
            except asyncio.TimeoutError:
                pass
    finally:
        log.info("Shutting down devices...")
        for dev in devices:
            try:
                dev.close()
            except Exception as e:
                log.warning(f"Error closing {dev.device_name}: {e}")
        log.info("Shutdown complete.")


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
