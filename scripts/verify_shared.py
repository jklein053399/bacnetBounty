"""Offline checks of the shared sales-demo model (profiles/sales). Opens no sockets: it can run while
another Bounty is running.

    .venv\\Scripts\\python.exe scripts\\verify_shared.py [sales_config.json] [--t0 2026-10-27T14:00]

1. Meter nesting: Meter A >= Meter B and A >= C, every 15 minutes for 13 months.
2. kWh totals equal the kW readings summed over time (15-minute samples), month by month, within 1%.
3. The year shows seasons (outdoor air, electricity, gas by month).
4. The join: a live run that starts from the saved state at T0 and ticks irregularly reads the same
   totalizers, later, as a fresh export to that later time.
5. kBtu/sf for the Single Building over the 12 months before T0 (US offices: roughly 50-90).
6. Live update dry run: every point-list device's update() against real BAC0 objects (no network),
   then a Niagara-style override and release on one point of each writable kind.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulator.config import load_config  # noqa: E402
from simulator.export import months_before  # noqa: E402
from simulator.shared_model import SharedSiteModel  # noqa: E402

FAILS: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {what}")
    if not ok:
        FAILS.append(what)


def month_key(ts: float) -> str:
    return f"{datetime.fromtimestamp(ts):%Y-%m}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config", nargs="?", default=str(ROOT / "sales_config.json"))
    ap.add_argument("--t0", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    t0_dt = datetime.fromisoformat(args.t0) if args.t0 else datetime.now()
    t0 = math.floor(t0_dt.timestamp() / 900) * 900
    start = math.ceil(months_before(datetime.fromtimestamp(t0), 13).timestamp() / 900) * 900
    m = SharedSiteModel(cfg)

    # 1 + 2 + 3: one pass over 13 months at 15 minutes
    print(f"1-3. {datetime.fromtimestamp(start):%Y-%m-%d} to {datetime.fromtimestamp(t0):%Y-%m-%d %H:%M}, 15-minute samples")
    worst_ab = worst_ac = 1e9
    months: dict[str, dict] = {}
    ts = start
    while ts <= t0:
        L = m.loads(ts)
        worst_ab = min(worst_ab, L["A"] - L["B"])
        worst_ac = min(worst_ac, L["A"] - L["C"])
        mk = month_key(ts)
        row = months.setdefault(mk, {"oat": [], "kw_sum_kwh": 0.0, "gas_sum": 0.0, "t_first": ts})
        row["oat"].append(L["oat"])
        row["kw_sum_kwh"] += L["A"] * 0.25
        row["gas_sum"] += L["gas"] * 0.25
        row["t_last"] = ts
        ts += 900
    check(worst_ab >= 0, f"Meter A >= Meter B at every sample (smallest margin {worst_ab:.2f} kW)")
    check(worst_ac >= 0, f"Meter A >= Meter C at every sample (smallest margin {worst_ac:.2f} kW)")

    print("     month    OAT   kWh A (register)  kWh A (sum of kW)  diff   gas SCF")
    worst = 0.0
    full = [k for k in months if k not in (month_key(start), month_key(t0))]
    for mk, row in months.items():
        a0 = m.totals(row["t_first"])["A"]
        a1 = m.totals(row["t_last"] + 900)["A"]
        reg = a1 - a0
        diff = (row["kw_sum_kwh"] - reg) / reg * 100 if reg else 0.0
        if mk in full:
            worst = max(worst, abs(diff))
        oat = sum(row["oat"]) / len(row["oat"])
        row.update(oat_mean=oat, kwh=reg)
        print(f"     {mk}  {oat:5.1f}  {reg:15,.0f}  {row['kw_sum_kwh']:17,.0f}  {diff:+5.2f}%  {row['gas_sum']:9,.0f}")
    check(worst <= 1.0, f"register kWh = sum of kW over time within 1% in every full month (worst {worst:.2f}%)")
    by_month = {int(k[5:]): v for k, v in months.items() if k in full}
    jul, jan, apr = by_month.get(7), by_month.get(1), by_month.get(4)
    if jul and jan and apr:
        check(jul["oat_mean"] - jan["oat_mean"] > 30, f"July is warmer than January by {jul['oat_mean'] - jan['oat_mean']:.0f} F")
        check(jul["kwh"] > apr["kwh"], f"July uses more electricity than April ({jul['kwh']:,.0f} vs {apr['kwh']:,.0f} kWh)")
        check(jan["gas_sum"] > 3 * jul["gas_sum"], f"January burns more than 3x July's gas ({jan['gas_sum']:,.0f} vs {jul['gas_sum']:,.0f} SCF)")

    # 4: the join
    print("4. The join at T0")
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state.json"
        m.totals(t0)
        m.save_state(state)
        live = SharedSiteModel(cfg)
        check(live.load_state(state), "a fresh live model loads the state saved at T0")
        rng = random.Random(7)
        t = t0
        end = t0 + 6 * 3600
        while t < end:                                   # ticks of 7-13 s, and one 5-minute pause
            t += rng.uniform(7.0, 13.0) + (300.0 if abs(t - (t0 + 3600)) < 6 else 0.0)
            live.tick(datetime.fromtimestamp(t))
        later = SharedSiteModel(cfg)                     # an export to the later time, from the epoch
        s_live, s_later = live.state_at(t), later.state_at(t)
        for scope in "ABCD":
            a, b = getattr(s_live, f"meter_{scope.lower()}_kwh"), getattr(s_later, f"meter_{scope.lower()}_kwh")
            check(abs(a - b) <= 1e-6 * max(1.0, abs(b)), f"Meter {scope} register 6 h after T0: live {a:,.3f} = export {b:,.3f}")
        check(abs(s_live.gas_scf_total - s_later.gas_scf_total) < 1e-3, "gas totalizer: live = export")
        check(abs(s_live.units["VAV_3"]["zone"] - s_later.units["VAV_3"]["zone"]) < 1e-9, "a zone temperature: live = export")

    # 5: kBtu/sf over the 12 months before T0
    t12 = months_before(datetime.fromtimestamp(t0), 12).timestamp()
    a, b = m.totals(t12), m.totals(t0)
    kwh, scf = b["A"] - a["A"], b["gas"] - a["gas"]
    sf = m.s.square_feet
    eui = (kwh * 3.412 + scf * 1.037) / sf
    print(f"5. Single Building, 12 months: {kwh:,.0f} kWh, {scf:,.0f} SCF gas, {sf:,.0f} sf")
    check(50 <= eui <= 90, f"kBtu/sf = {eui:.1f} (electricity {kwh * 3.412 / sf:.1f}, gas {scf * 1.037 / sf:.1f})")
    d_kwh = b["D"] - a["D"]
    print(f"   Meter D's building: {d_kwh:,.0f} kWh = {d_kwh * 3.412 / m.s.meter_d_square_feet:.1f} kBtu/sf electric")

    # 6: live update dry run
    print("6. Live update dry run (BAC0 objects, no network)")
    asyncio.run(dry_run(Path(args.config), m, t0))

    print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED'}")
    return 1 if FAILS else 0


async def dry_run(cfg_path: Path, m: SharedSiteModel, t0: float) -> None:
    import BAC0
    from BAC0.core.devices.local.factory import ObjectFactory
    from bacpypes3.basetypes import BinaryPV
    from bacpypes3.primitivedata import Null, Real, Unsigned

    from simulator.__main__ import load_profile
    from simulator.devices import model_pointlist

    class FakeApp:                                       # stands in for BAC0.lite: holds the objects, opens nothing
        def __init__(self, *a, **k):
            self.this_application = type("T", (), {"app": type("A", (), {"objectIdentifier": {}})()})()
            self.objs = {}

        def __getitem__(self, name):
            return self.objs[name]

        def disconnect(self):
            pass

    real_lite, real_add = BAC0.lite, ObjectFactory.add_objects_to_application
    BAC0.lite = FakeApp
    ObjectFactory.add_objects_to_application = lambda self, app: app.objs.update(ObjectFactory.objects)
    try:
        manifest, location = load_profile(cfg_path)
        m.tick(datetime.fromtimestamp(t0))
        devs = []
        for spec in manifest:
            if spec["kind"] != "pointlist":
                continue
            d = model_pointlist.ModelPointListDevice(
                device_type=spec["type"], site_model=m, device_id=spec["device_id"], device_name=spec["name"],
                local_ip="0.0.0.0", subnet_mask_prefix=24, bacnet_port=47808, vendor_id=spec["vendor_id"],
                vendor_name=spec["vendor_name"], model_name=spec["model_name"], points=spec["points"], location=location)
            d.update()
            devs.append(d)
        check(len(devs) == 22, f"{len(devs)} point-list devices built and updated")
        vav = next(d for d in devs if d.device_name == "VAV_1")
        u = m.state.units["VAV_1"]
        check(abs(float(vav.bacnet["ZN-T"].presentValue) - round(u["zone"], 2)) < 0.01,
              f"VAV_1 ZN-T on the object = the model ({float(vav.bacnet['ZN-T'].presentValue):.2f})")
        ahu = next(d for d in devs if d.device_name == "AHU_1")
        sf_c, sf_s = ahu.bacnet["SF_C"], ahu.bacnet["SF_S"]
        check(str(sf_s.presentValue) == str(sf_c.presentValue), f"AHU_1 SF_S follows SF_C ({sf_c.presentValue})")

        # Niagara-style override and release on an AO, a BO, an MSV and a writable AV
        cases = [(vav, "DPR-O", Real(12.0)), (ahu, "SF_C", BinaryPV("inactive" if str(sf_c.presentValue) == "active" else "active")),
                 (vav, "OCC-MODE", Unsigned(4)), (vav, "EFFCLG-SP", Real(77.0))]
        for dev, name, val in cases:
            o = dev.bacnet[name]
            model_v = o.presentValue
            await o.write_property("presentValue", val, priority=8)
            dev.update()
            shown = str(o.presentValue)
            held = shown == str(val)
            await o.write_property("presentValue", Null(()), priority=8)
            dev.update()
            back = str(o.presentValue) == str(model_v)
            check(held and back, f"{dev.device_name} {name}: override @8 holds through a tick ({shown}), release returns to the model ({o.presentValue})")
        o = vav.bacnet["DPR-O"]
        await o.write_property("presentValue", Real(5.0), priority=16)
        vav.update()
        held = abs(float(o.presentValue) - 5.0) < 1e-6
        await o.write_property("presentValue", Null(()), priority=16)
        vav.update()
        check(held and abs(float(o.presentValue) - round(u["damper"], 2)) < 0.01, "VAV_1 DPR-O: a write @16 also holds, and its release returns to the model")
    finally:
        BAC0.lite, ObjectFactory.add_objects_to_application = real_lite, real_add


if __name__ == "__main__":
    sys.exit(main())
