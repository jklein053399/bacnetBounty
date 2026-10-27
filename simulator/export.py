"""History export for the shared sales-demo site: the past, written out for loading into Niagara.

    .venv\\Scripts\\python.exe -m simulator.export sales_config.json [--end 2026-10-27T14:00] [--out exports\\sales]

Runs the shared model (simulator/shared_model.py) on a fake clock up to the end time T0 and writes, per
point, a gzipped CSV of "epoch_ms,value" lines, plus manifest.json describing every file. It opens no
network sockets and starts no devices, so it can run while another Bounty is running.

    analog points       one value every 15 minutes (the history standard's interval)
    binary / multistate one record at the start, then one per change, checked every 5 minutes

Depth: 13 months for the meter points the Energy Dashboard uses, 6 months for everything else
(sales_config.json, shared_model.history). The Niagara loader picks each history's records to suit the
history extension the station has on that point (interval or change of value); "history_hint" in the
manifest is the history standard's choice, for reference.

The model's state at T0 is saved (shared_model.state_file) so the live run starts from the same
totalizers. The live run would compute the same values anyway: every value is a function of the time.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from .__main__ import load_profile
from .config import load_config
from .devices import emon, onicon_gas, onicon_water
from .devices.pointlist import ALWAYS_WRITABLE, COMMAND_TAIL, STATUS_TAIL, stem
from .shared_model import SharedSiteModel
from .shared_points import NO_DRIFT, point_value

DASHBOARD_METER_POINTS = {
    "emon": {"Energy_delivered", "Real_power", "Peak_demand", "Power_factor"},
    "onicon_gas": {"Flow_Rate", "Totalizer"},
    "onicon_water": {"Flow_Rate", "Totalizer"},
}
BINARY, MULTI = ("BI", "BO", "BV"), ("MSI", "MSO", "MSV")
BACNET_TYPE = {"AI": 0, "AO": 1, "AV": 2, "BI": 3, "BO": 4, "BV": 5, "MSI": 13, "MSO": 14, "MSV": 19}


def months_before(t: datetime, months: int) -> datetime:
    y, m = divmod(t.year * 12 + (t.month - 1) - months, 12)
    return t.replace(year=y, month=m + 1, day=min(t.day, 28))


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def build_points(manifest: list[dict]) -> list[dict]:
    """Every point of every device, with what the export needs to compute and describe it."""
    out = []
    for d in manifest:
        kind = d["kind"]
        if kind == "pointlist":
            follow, commands = {}, {}
            pts = []
            for p in d["points"]:
                k = p["type"]
                writable = bool(p.get("writable")) or k in ALWAYS_WRITABLE
                if k in BINARY:
                    init = str(p.get("value")).lower() in ("true", "1", "active", "on")
                elif k in MULTI:
                    init = max(1, min(len(p.get("states") or [1, 2]), int(float(p.get("value") or 1))))
                else:
                    init = float(p.get("value") or 0)
                pts.append(dict(device=d["name"], device_id=d["device_id"], dtype=d["type"], src="pointlist", name=p["name"], kind=k,
                                writable=writable, base=init if k not in BINARY + MULTI else 0.0, init=init,
                                object=f"{k}:{p['instance']}", units=p.get("units") or "", states=p.get("states") or [],
                                months="other"))
                if k in ("BO", "BV") and writable and stem(p["name"], COMMAND_TAIL):
                    commands[stem(p["name"], COMMAND_TAIL)] = p["name"]
            for q in pts:
                s = stem(q["name"], STATUS_TAIL) if q["kind"] in ("BI", "BV") and not q["writable"] else None
                if s and s in commands:
                    follow[q["name"]] = commands[s]
            for q in pts:
                q["follows"] = follow.get(q["name"])
            out += pts
        else:
            table = {"emon": emon.POINTS, "onicon_gas": onicon_gas.POINTS, "onicon_water": onicon_water.POINTS}[kind]
            for inst, name, desc, units in table:
                out.append(dict(device=d["name"], dtype=kind, src=kind, scope=d.get("scope"), device_id=d["device_id"],
                                name=name, kind="AI", writable=False, object=f"AI:{inst}", units=units or "",
                                states=[], follows=None,
                                months="dashboard" if name in DASHBOARD_METER_POINTS[kind] else "other"))
    return out


def history_hint(q: dict) -> str:
    """The history standard's choice: setpoints and binaries / enums on change of value, the rest on interval."""
    if q["kind"] in BINARY + MULTI:
        return "cov"
    return "cov" if NO_DRIFT.search(q["name"]) and "RUNTIME" not in q["name"] else "interval"


class Writer:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = gzip.open(path, "wt", encoding="ascii", compresslevel=6, newline="\n")
        self.n = 0
        self.last = None

    def write(self, ts: float, v) -> None:
        if isinstance(v, bool):
            txt = "true" if v else "false"
        elif isinstance(v, int):
            txt = str(v)
        else:
            txt = f"{v:.3f}".rstrip("0").rstrip(".") if math.isfinite(v) else "nan"
        self.f.write(f"{int(round(ts * 1000))},{txt}\n")
        self.n += 1

    def close(self) -> None:
        self.f.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("config", type=Path)
    ap.add_argument("--end", help="T0, local time (default: now, rounded down to 15 minutes)")
    ap.add_argument("--out", type=Path, help="output folder (default: exports/sales_<T0>)")
    ap.add_argument("--months", type=int, nargs=2, metavar=("DASHBOARD", "OTHER"),
                    help="depth in months, overriding the config (for a quick test run)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if cfg.raw.get("model") != "shared":
        print("This config does not use the shared model (\"model\": \"shared\").", file=sys.stderr)
        return 2
    manifest, _location = load_profile(args.config)
    hist = cfg.raw.get("shared_model", {}).get("history", {})
    dash_months, other_months = args.months or (hist.get("dashboard_meter_months", 13), hist.get("other_months", 6))
    interval = 60 * hist.get("interval_minutes", 15)
    step = 60 * hist.get("change_step_minutes", 5)

    end_dt = datetime.fromisoformat(args.end) if args.end else datetime.now()
    end_ts = math.floor(end_dt.timestamp() / interval) * interval
    end_dt = datetime.fromtimestamp(end_ts)
    out = args.out or (args.config.parent / "exports" / f"sales_{end_dt:%Y%m%d_%H%M}")
    model = SharedSiteModel(cfg)
    if model.epoch_ts > months_before(end_dt, dash_months).timestamp():
        print(f"The epoch ({model.s.epoch}) is later than {dash_months} months before T0.", file=sys.stderr)
        return 2
    starts = {"dashboard": math.ceil(months_before(end_dt, dash_months).timestamp() / interval) * interval,
              "other": math.ceil(months_before(end_dt, other_months).timestamp() / interval) * interval}

    points = build_points(manifest)
    for q in points:
        q["file"] = f"{safe(q['device'])}/{safe(q['name'])}.csv.gz"
        q["writer"] = Writer(out / q["file"])
    by_device: dict[str, list[dict]] = {}
    for q in points:
        by_device.setdefault(q["device"], []).append(q)
    mags = cfg.magnitudes

    t_start = time.perf_counter()
    ts = float(starts["dashboard"])
    k = 0
    print(f"T0 {end_dt:%Y-%m-%d %H:%M}; {len(points)} points on {len(by_device)} devices -> {out}")
    while ts <= end_ts:
        in_other = ts >= starts["other"]
        on_interval = (ts - starts["dashboard"]) % interval == 0
        if not in_other and not on_interval:
            ts += step
            continue
        st = model.state_at(ts)
        for dev, qs in by_device.items():
            vals: dict[str, object] = {}
            src = qs[0]["src"]
            if src == "emon":
                scope = qs[0]["scope"]
                vals = emon.emon_point_values(getattr(st, f"meter_{scope.lower()}_kw"), getattr(st, f"meter_{scope.lower()}_kwh"),
                                              model.peak_demand_at(ts, scope), mags, qs[0]["device_id"])
            elif src == "onicon_gas":
                vals = {"Flow_Rate": st.gas_scfh, "Totalizer": st.gas_scf_total, "Gas_Temperature": st.gas_temp_f}
            elif src == "onicon_water":
                vals = {"Flow_Rate": st.water_gpm, "Totalizer": st.water_gallons_total, "Water_Temperature": st.water_temp_f}
            for q in qs:
                months_ok = ts >= starts[q["months"]]
                if not months_ok:
                    continue
                discrete = q["kind"] in BINARY + MULTI
                if not discrete and not on_interval:
                    continue
                if src == "pointlist":
                    v = point_value(q["dtype"], dev, q, st, ts, model.seed)
                    if v is None:
                        v = q["init"]
                    if discrete:
                        v = bool(v) if q["kind"] in BINARY else int(v)
                    else:
                        v = round(float(v), 2)
                else:
                    v = float(vals[q["name"]])
                vals[q["name"]] = v
            for q in qs:
                if q["name"] not in vals or not (ts >= starts[q["months"]]):
                    continue
                v = vals[q["follows"]] if q.get("follows") and q["follows"] in vals else vals[q["name"]]
                w = q["writer"]
                if q["kind"] in BINARY + MULTI:
                    if w.last is None or v != w.last:
                        w.write(ts, v)
                        w.last = v
                elif on_interval:
                    w.write(ts, v)
        k += 1
        if k % 5000 == 0:
            print(f"  {datetime.fromtimestamp(ts):%Y-%m-%d}  ({time.perf_counter() - t_start:.0f} s)")
        ts += step

    total = 0
    for q in points:
        q["writer"].close()
        total += q["writer"].n
    meta = {
        "about": "BACnet Bounty sales-demo history export (simulator/export.py). One gzipped CSV per point: epoch_ms,value. "
                 "Binary values are true/false; multistate values are the BACnet value (1-based).",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "config": str(args.config), "seed": model.seed, "epoch": model.s.epoch,
        "t0": end_dt.isoformat(timespec="minutes"), "t0_ms": int(end_ts * 1000),
        "interval_minutes": interval // 60, "change_step_minutes": step // 60,
        "starts": {k_: datetime.fromtimestamp(v_).isoformat(timespec="minutes") for k_, v_ in starts.items()},
        "points": [{"device": q["device"], "point": q["name"], "object": q["object"],
                    "kind": "boolean" if q["kind"] in BINARY else "enum" if q["kind"] in MULTI else "numeric",
                    "units": q["units"], "states": q["states"], "writable": q["writable"],
                    "series": "changes" if q["kind"] in BINARY + MULTI else "interval",
                    "history_hint": history_hint(q), "months": dash_months if q["months"] == "dashboard" else other_months,
                    "records": q["writer"].n, "file": q["file"]} for q in points],
    }
    (out / "manifest.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    # the same list as tab-separated text, for the Niagara loader (a Robot has no JSON parser)
    rows = ["# t0_ms\t" + str(meta["t0_ms"]),
            "\t".join(("device_id", "device", "point", "object_type", "instance", "kind", "series", "months",
                           "records", "file"))]
    for q, pm in zip(points, meta["points"]):
        kind_code, inst = q["object"].split(":")
        rows.append("\t".join(str(x) for x in (q["device_id"], q["device"], q["name"], BACNET_TYPE[kind_code], inst,
                                                pm["kind"], pm["series"], pm["months"], pm["records"], pm["file"])))
    (out / "manifest.tsv").write_text("\n".join(rows) + "\n", encoding="ascii")
    model.totals(end_ts)
    model.save_state(out / "state.json")
    state_file = cfg.raw.get("shared_model", {}).get("state_file")
    if state_file:
        (args.config.parent / state_file).parent.mkdir(parents=True, exist_ok=True)
        model.save_state(args.config.parent / state_file)
    size = sum(f.stat().st_size for f in out.rglob("*.csv.gz"))
    print(f"Done in {time.perf_counter() - t_start:.0f} s: {total:,} records, {size / 1e6:.1f} MB, manifest {out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
