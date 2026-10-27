"""Shared site model: one model behind the 28 sales-demo devices (profiles/sales).

Unlike SiteModel, every value here is a pure function of the time and the seed. The weather has no
random walk and the noise is keyed to the timestamp, so the history export (simulator.export) and the
live run compute the same numbers for the same moment. Totalizers integrate on a fixed time grid from
a fixed epoch, so a station whose history is loaded weeks after another still joins the live values
with no jump.

What it models, per spec of the sales demo handoff (BAS-Atlas Sales-Demo/HANDOFF.md, Phase 1):
    RTU_1    AAON VAV rooftop, DX cooling, gas heat, feeds VAV_1..10
    VAV_1-10 JCI VAVs with electric reheat
    AHU_1    JCI single-zone AHU, chilled water from CHWS_1, hot water from HWS_1
    CHWS_1   air-cooled chiller plant;   HWS_1  boiler plant (gas)
    EF_1-5   exhaust fans;               CUH_1-3  cabinet unit heaters (hot water)
    Meter A  everything electric          Meter B  RTU_1 + AHU_1 + VAV reheat
    Meter C  the central plant            Meter D  a separate, smaller building
    Gas      RTU_1 gas heat + HWS_1 boilers;   Water  domestic use

Live use: the same interface the meter devices read from SiteModel (.state, .config,
.peak_demand_kw(scope), .tick(now)).
"""
from __future__ import annotations

import json
import math
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .config import Config

SCOPES = ("A", "B", "C", "D")
OCCUPIED_MIN = 0.1          # below this share the building is unoccupied (Sunday's 0.05 is a few people, not a schedule)


# ---------------------------------------------------------------- noise (pure, keyed to the time)

def h01(seed: int, key: str, k: int) -> float:
    """Deterministic value in [0, 1) for (seed, key, k). zlib.crc32, not hash(): hash() of a str
    changes from one Python process to the next."""
    return zlib.crc32(f"{seed}|{key}|{k}".encode()) / 4294967296.0


def smooth(seed: int, key: str, ts: float, period: float) -> float:
    """Smooth value noise in [-1, 1]: random knots every `period` seconds, eased between."""
    x = ts / period
    k = math.floor(x)
    f = x - k
    f = f * f * (3.0 - 2.0 * f)
    a = h01(seed, key, k)
    b = h01(seed, key, k + 1)
    return 2.0 * (a + (b - a) * f) - 1.0


def jitter(seed: int, key: str, ts: float, step: float = 60.0) -> float:
    """Step noise in [-1, 1], constant within each `step` seconds."""
    return 2.0 * h01(seed, key, math.floor(ts / step)) - 1.0


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------- settings

@dataclass
class SharedSettings:
    seed: int = 20261027
    epoch: str = "2025-09-01T00:00:00"      # local time; totalizers are zero here (plus their offsets)
    grid_seconds: int = 60                  # totalizer integration step
    square_feet: float = 30000
    vav_count: int = 10
    ef_count: int = 5
    cuh_count: int = 3
    # electric loads (kW)
    rtu_peak_kw: float = 55.0               # fan + DX at full load
    ahu_fan_kw: float = 6.0
    vav_reheat_peak_kw_each: float = 3.6
    chiller_peak_kw: float = 48.0
    chw_pump_kw: float = 5.5
    hw_pump_kw: float = 3.7
    ef_kw_each: float = 0.75
    cuh_fan_kw_each: float = 0.15
    lighting_peak_kw: float = 33.0
    plug_peak_kw: float = 27.0
    plug_baseline_kw: float = 4.0
    misc_kw: float = 8.0
    plant_aux_kw: float = 2.0
    meter_d_square_feet: float = 15000
    meter_d_peak_kw: float = 70.0
    meter_d_baseline_kw: float = 9.0
    # gas (SCFH at full fire) and water (GPM)
    rtu_gas_peak_scfh: float = 290.0
    boiler_gas_peak_scfh: float = 480.0
    gas_pilot_scfh: float = 12.0
    water_peak_gpm: float = 8.0
    water_baseline_gpm: float = 0.05
    # register offsets, so meters look like they have been in service for years
    offsets: dict = field(default_factory=lambda: {
        "A": 1843210.0, "B": 702455.0, "C": 512040.0, "D": 388117.0, "gas": 9120455.0, "water": 1254300.0})

    @classmethod
    def from_raw(cls, raw: dict) -> "SharedSettings":
        known = {k: v for k, v in (raw or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)


# ---------------------------------------------------------------- state

@dataclass
class SharedState:
    """One moment of the shared site. Field names the meter devices read match SiteState."""
    timestamp: datetime
    oat_f: float
    oa_rh: float
    occupancy_fraction: float
    cooling_load_fraction: float
    heating_load_fraction: float
    mode: str                               # "cooling" / "heating" / "shoulder"
    meter_a_kw: float
    meter_b_kw: float
    meter_c_kw: float
    meter_d_kw: float
    meter_a_kwh: float
    meter_b_kwh: float
    meter_c_kwh: float
    meter_d_kwh: float
    gas_scfh: float
    gas_scf_total: float
    gas_temp_f: float
    water_gpm: float
    water_gallons_total: float
    water_temp_f: float
    units: dict                             # per-unit channels: units["RTU_1"], units["VAV_3"] ...
    epoch_ts: float = 0.0


# ---------------------------------------------------------------- the model

class SharedSiteModel:
    def __init__(self, config: Config, settings: SharedSettings | None = None):
        self.config = config
        self.s = settings or SharedSettings.from_raw(config.raw.get("shared_model", {}))
        self.seed = self.s.seed
        self.epoch_ts = datetime.fromisoformat(self.s.epoch).timestamp()
        self.grid = float(self.s.grid_seconds)
        self.state: SharedState | None = None
        # integrator: running sums at grid index n, plus a checkpoint every day
        self._n = 0
        self._sums = {k: 0.0 for k in (*SCOPES, "gas", "water")}
        self._checkpoints: dict[int, dict] = {0: dict(self._sums)}
        self._per_day = int(86400 / self.grid)
        w = config.weather
        self._month_mean = [(hi + lo) / 2.0 for hi, lo in w.monthly_high_low_f]
        self._month_range = [hi - lo for hi, lo in w.monthly_high_low_f]
        sched = config.schedule
        self._occ_start = _hhmm(sched.occupied_weekday_start)
        self._occ_end = _hhmm(sched.occupied_weekday_end)

    # ---------------- drivers

    def _seasonal(self, lt: datetime) -> tuple[float, float]:
        """Monthly normals eased between mid-month knots, so the year has no monthly steps."""
        doy = lt.timetuple().tm_yday - 1 + (lt.hour + lt.minute / 60.0) / 24.0
        pos = doy / 365.25 * 12.0 - 0.5            # 0.0 = mid-January
        i = math.floor(pos)
        f = pos - i
        f = (1 - math.cos(math.pi * f)) / 2.0
        a, b = i % 12, (i + 1) % 12
        mean = self._month_mean[a] + (self._month_mean[b] - self._month_mean[a]) * f
        rng = self._month_range[a] + (self._month_range[b] - self._month_range[a]) * f
        return mean, rng

    def oat(self, ts: float, lt: datetime) -> float:
        w = self.config.weather
        mean, rng = self._seasonal(lt)
        hour = lt.hour + lt.minute / 60.0 + lt.second / 3600.0
        diurnal = -math.cos(2 * math.pi * (hour - w.diurnal_trough_hour) / 24.0)
        days = (ts - self.epoch_ts) / 86400.0
        weather = (4.0 * math.sin(2 * math.pi * days / 4.3 + 6.28 * h01(self.seed, "wx1", 0))
                   + 2.5 * math.sin(2 * math.pi * days / 9.7 + 6.28 * h01(self.seed, "wx2", 0))
                   + 1.5 * math.sin(2 * math.pi * days / 2.1 + 6.28 * h01(self.seed, "wx3", 0))
                   + 3.0 * smooth(self.seed, "wx", ts, 6 * 3600.0))
        weather = clamp(weather, -w.random_walk_bound_f * 2, w.random_walk_bound_f * 2)
        return mean + rng / 2.0 * diurnal + weather + 0.4 * smooth(self.seed, "oatn", ts, 600.0)

    def oa_rh(self, ts: float, lt: datetime) -> float:
        hour = lt.hour + lt.minute / 60.0
        night = math.cos(2 * math.pi * (hour - 5.0) / 24.0)      # +1 before dawn, -1 mid-afternoon
        base = 70.0 if lt.month in (11, 12, 1, 2, 3) else 64.0
        return clamp(base + 14.0 * night + 8.0 * smooth(self.seed, "rh", ts, 4 * 3600.0), 22.0, 98.0)

    def occupancy(self, lt: datetime) -> float:
        sched = self.config.schedule
        wd = lt.weekday()
        hour = lt.hour + lt.minute / 60.0
        if wd < 5:
            start, end = self._occ_start, self._occ_end
            if hour < start or hour > end:
                return 0.0
            if hour < start + sched.ramp_up_hours:
                return (hour - start) / sched.ramp_up_hours
            if hour > end - sched.ramp_down_hours:
                return max(0.0, (end - hour) / sched.ramp_down_hours)
            return 1.0
        if wd == 5:
            return sched.saturday_peak_fraction if 8.0 <= hour <= 14.0 else 0.0
        return sched.sunday_baseline_fraction

    @staticmethod
    def thermal(oat: float) -> tuple[float, float]:
        cool = clamp((oat - 60.0) / 30.0, 0.0, 1.0)
        heat = clamp((55.0 - oat) / 40.0, 0.0, 1.0)
        return cool, heat

    # ---------------- loads (kW, SCFH, GPM) at one moment; cheap enough for the 60 s grid

    def loads(self, ts: float) -> dict:
        s, seed = self.s, self.seed
        lt = datetime.fromtimestamp(ts)
        oat = self.oat(ts, lt)
        occ = self.occupancy(lt)
        cool, heat = self.thermal(oat)
        hour = lt.hour + lt.minute / 60.0
        wd = lt.weekday()
        lights_on = (6.0 <= hour <= 22.0) if wd < 5 else (7.0 <= hour <= 15.0) if wd == 5 else False

        lighting = s.lighting_peak_kw * (0.95 + 0.05 * h01(seed, "lt", int(ts // 60))) if lights_on else 2.0
        plug = (s.plug_baseline_kw + occ * (s.plug_peak_kw - s.plug_baseline_kw)) * (0.95 + 0.05 * h01(seed, "pl", int(ts // 60)))

        fan_on = occ > OCCUPIED_MIN
        fan_demand = max(0.5 * occ, cool * occ, 0.7 * heat * occ)
        econ_only = cool > 0 and oat < 62.0
        dx = 0.0 if econ_only else cool
        rtu_kw = (0.8 + 0.2 * fan_demand * s.rtu_peak_kw + 0.8 * occ * dx * s.rtu_peak_kw) * (0.97 + 0.06 * h01(seed, "rtu", int(ts // 60)))
        ahu_kw = s.ahu_fan_kw * (0.96 + 0.04 * h01(seed, "ahu", int(ts // 60))) if fan_on else 0.3

        reheat_base = heat * max(0.3, occ) if fan_on else 0.0      # no airflow, no electric reheat
        valves = []
        for i in range(s.vav_count):
            phase = 1.0 + 0.20 * math.sin(math.radians(i * 36.0))
            weight = 1.15 if i < 6 else 0.85                    # VAV_1..6 perimeter, 7..10 interior
            valves.append(clamp(reheat_base * phase * weight, 0.0, 1.0))
        reheat_kw = sum(valves) * s.vav_reheat_peak_kw_each * (0.98 + 0.04 * h01(seed, "rh", int(ts // 60)))

        chw_on = oat > 55.0 and (occ > OCCUPIED_MIN or oat > 78.0)
        chw_load = clamp(cool * (0.4 + 0.6 * occ), 0.0, 1.0) if chw_on else 0.0
        chiller_kw = s.chiller_peak_kw * (0.15 + 0.85 * chw_load) * (0.97 + 0.06 * h01(seed, "ch", int(ts // 60))) if chw_on else 0.0
        chw_pumps_kw = s.chw_pump_kw * (0.4 + 0.6 * chw_load) ** 2.5 if chw_on else 0.0
        hw_on = oat < 55.0
        hw_load = clamp(heat * (0.3 + 0.7 * max(occ, 0.25)), 0.0, 1.0) if hw_on else 0.0
        hw_pumps_kw = s.hw_pump_kw * (0.4 + 0.6 * hw_load) ** 2.5 if hw_on else 0.0
        ef_kw = sum(s.ef_kw_each for i in range(s.ef_count) if self.ef_on(i, occ, lt))
        cuh_kw = sum(s.cuh_fan_kw_each for i in range(s.cuh_count) if self.cuh_on(i, ts, heat))

        plant_kw = chiller_kw + chw_pumps_kw + hw_pumps_kw + s.plant_aux_kw
        meter_b = rtu_kw + ahu_kw + reheat_kw
        meter_a = meter_b + plant_kw + ef_kw + cuh_kw + lighting + plug + s.misc_kw
        meter_c = plant_kw
        d_occ = self.occupancy(datetime.fromtimestamp(ts + 1800))     # opens half an hour earlier
        meter_d = (s.meter_d_baseline_kw + (s.meter_d_peak_kw - s.meter_d_baseline_kw)
                   * (0.55 * d_occ + 0.45 * d_occ * max(cool, 0.6 * heat))) * (0.96 + 0.08 * h01(seed, "md", int(ts // 60)))

        rtu_heat = clamp(heat * 0.8, 0.0, 1.0) if fan_on else 0.0
        boiler_fire = hw_load
        gas = s.gas_pilot_scfh + rtu_heat * s.rtu_gas_peak_scfh + boiler_fire * s.boiler_gas_peak_scfh
        gas *= 0.96 + 0.08 * h01(seed, "gas", int(ts // 60))

        water = s.water_baseline_gpm + occ * (s.water_peak_gpm * 0.4 - s.water_baseline_gpm)
        if occ > 0.2 and h01(seed, "wburst", int(ts // 60)) > 0.85:
            water += 2.0 + (s.water_peak_gpm - 2.0) * h01(seed, "wsize", int(ts // 60))

        return dict(lt=lt, oat=oat, occ=occ, cool=cool, heat=heat, fan_on=fan_on, fan_demand=fan_demand,
                    econ_only=econ_only, dx=dx, rtu_heat=rtu_heat, valves=valves, chw_on=chw_on, chw_load=chw_load,
                    hw_on=hw_on, hw_load=hw_load, A=meter_a, B=meter_b, C=meter_c, D=meter_d,
                    gas=gas, water=max(0.0, water), rtu_kw=rtu_kw, ahu_kw=ahu_kw, reheat_kw=reheat_kw,
                    chiller_kw=chiller_kw)

    def ef_on(self, i: int, occ: float, lt: datetime) -> bool:
        return occ > OCCUPIED_MIN if i < 3 else (6 <= lt.hour < 21)     # EF_4, EF_5: restrooms, longer hours

    def cuh_on(self, i: int, ts: float, heat: float) -> bool:
        """Cabinet heaters cycle on a heating call: a 20-minute cycle, on for the heating share of it."""
        if heat <= 0.0:
            return False
        duty = clamp(0.15 + 0.85 * heat, 0.0, 1.0)
        return ((ts / 1200.0 + h01(self.seed, "cuh", i)) % 1.0) < duty

    # ---------------- totalizers on the grid

    @lru_cache(maxsize=8192)
    def _grid_loads(self, n: int) -> tuple:
        L = self.loads(self.epoch_ts + n * self.grid)
        return L["A"], L["B"], L["C"], L["D"], L["gas"], L["water"]

    def _advance_to(self, n: int) -> None:
        if n < self._n:
            day = max(d for d in self._checkpoints if d * self._per_day <= n)
            self._n, self._sums = day * self._per_day, dict(self._checkpoints[day])
        dt_h = self.grid / 3600.0
        while self._n < n:
            a, b, c, d, gas, water = self._grid_loads(self._n)
            sm = self._sums
            sm["A"] += a * dt_h
            sm["B"] += b * dt_h
            sm["C"] += c * dt_h
            sm["D"] += d * dt_h
            sm["gas"] += gas * dt_h
            sm["water"] += water * self.grid / 60.0
            self._n += 1
            if self._n % self._per_day == 0:
                self._checkpoints[self._n // self._per_day] = dict(sm)

    def totals(self, ts: float) -> dict:
        """Register readings at ts: kWh per scope, SCF of gas, gallons of water (offsets included)."""
        x = (ts - self.epoch_ts) / self.grid
        n = max(0, math.floor(x))
        self._advance_to(n)
        part = (x - n) * self.grid if x > 0 else 0.0
        a, b, c, d, gas, water = self._grid_loads(n)
        off = self.s.offsets
        return {"A": off["A"] + self._sums["A"] + a * part / 3600.0,
                "B": off["B"] + self._sums["B"] + b * part / 3600.0,
                "C": off["C"] + self._sums["C"] + c * part / 3600.0,
                "D": off["D"] + self._sums["D"] + d * part / 3600.0,
                "gas": off["gas"] + self._sums["gas"] + gas * part / 3600.0,
                "water": off["water"] + self._sums["water"] + water * part / 60.0}

    def peak_demand_at(self, ts: float, scope: str) -> float:
        """Peak 15-minute demand of the last completed fixed window (calendar quarter hours)."""
        end = math.floor(ts / 900.0) * 900.0
        idx = "ABCD".index(scope)
        first = math.ceil((end - 900.0 - self.epoch_ts) / self.grid)
        last = math.floor((end - self.epoch_ts) / self.grid - 1e-9)
        vals = [self._grid_loads(n)[idx] for n in range(max(0, first), max(0, last) + 1)]
        return max(vals) if vals else self.loads(ts)[scope]

    def save_state(self, path: Path) -> None:
        """Running sums at the current grid index, so a live start needn't integrate from the epoch."""
        Path(path).write_text(json.dumps({"seed": self.seed, "epoch": self.s.epoch, "grid": self.grid,
                                          "n": self._n, "sums": self._sums}, indent=1))

    def load_state(self, path: Path) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        d = json.loads(p.read_text())
        if (d["seed"], d["epoch"], d["grid"]) != (self.seed, self.s.epoch, self.grid):
            return False
        self._n, self._sums = d["n"], dict(d["sums"])
        if self._n % self._per_day == 0:
            self._checkpoints[self._n // self._per_day] = dict(self._sums)
        return True

    # ---------------- one moment, with every unit's channels

    def state_at(self, ts: float) -> SharedState:
        L = self.loads(ts)
        T = self.totals(ts)
        lt, oat, occ, cool, heat = L["lt"], L["oat"], L["occ"], L["cool"], L["heat"]
        mode = "heating" if heat > cool else "cooling" if cool > heat else "shoulder"
        units = self._units(ts, L, mode)
        seed = self.seed
        return SharedState(
            timestamp=lt, oat_f=oat, oa_rh=self.oa_rh(ts, lt), occupancy_fraction=occ,
            cooling_load_fraction=cool, heating_load_fraction=heat, mode=mode,
            meter_a_kw=L["A"], meter_b_kw=L["B"], meter_c_kw=L["C"], meter_d_kw=L["D"],
            meter_a_kwh=T["A"], meter_b_kwh=T["B"], meter_c_kwh=T["C"], meter_d_kwh=T["D"],
            gas_scfh=L["gas"], gas_scf_total=T["gas"], gas_temp_f=oat + 2.0 + 4.0 * h01(seed, "gt", int(ts // 60)),
            water_gpm=L["water"], water_gallons_total=T["water"], water_temp_f=55.0 + jitter(seed, "wt", ts),
            units=units, epoch_ts=self.epoch_ts)

    def _units(self, ts: float, L: dict, mode: str) -> dict:
        s, seed = self.s, self.seed
        sched = self.config.schedule
        oat, occ, cool, heat, fan_on = L["oat"], L["occ"], L["cool"], L["heat"], L["fan_on"]
        occupied = occ > OCCUPIED_MIN
        clg_sp = sched.cooling_setpoint_occupied if occupied else sched.cooling_setpoint_unoccupied
        htg_sp = sched.heating_setpoint_occupied if occupied else sched.heating_setpoint_unoccupied
        zone_target = htg_sp + 1.0 if mode == "heating" else clg_sp - 1.0 if mode == "cooling" else 72.0
        if not fan_on:                                            # unoccupied: zones float toward outdoors a little
            zone_target = clamp(72.0 + 0.12 * (oat - 60.0), htg_sp, clg_sp)
        n = lambda key, amp, period=900.0: amp * smooth(seed, key, ts, period)   # noqa: E731
        u: dict[str, dict] = {}

        # RTU_1: VAV rooftop
        sat_sp = 55.0 if mode == "cooling" else 60.0 if mode == "heating" else 58.0
        econ = (100.0 if L["econ_only"] else 15.0) if fan_on else 0.0
        if fan_on and mode == "cooling" and not L["econ_only"] and oat < 70.0:
            econ = 40.0
        vfd = clamp(40.0 + 60.0 * max(cool, 0.6 * heat), 40.0, 100.0) if fan_on else 0.0
        zones = []
        for i in range(s.vav_count):
            bias = (0.5 if i < 6 else 0.0) * (-1.0 if mode == "heating" else 1.0)
            zones.append(zone_target + 0.8 * math.sin(math.radians(i * 36.0)) + bias + n(f"zn{i}", 0.5, 1200.0))
        space = sum(zones) / len(zones)
        cooling_pct = 100.0 * L["dx"] if fan_on else 0.0
        space_rh = clamp(32.0 + 0.25 * (oat - 30.0) + n("sprh", 3.0, 3600.0), 20.0, 60.0)
        u["RTU_1"] = dict(
            rh=space_rh,
            fan_on=fan_on, sat=(sat_sp + n("rtusat", 0.7)) if fan_on else space - 2.0 + n("rtusat", 0.5),
            sat_sp=sat_sp, space=space, rat=space + (1.2 if mode == "cooling" else 0.4), oat=oat,
            static=(1.2 * (1.0 + n("rtusp", 0.03))) if fan_on else 0.01, static_sp=1.2, vfd=vfd,
            econ=econ, ret_dpr=(100.0 - econ) if fan_on else 0.0, cooling=cooling_pct,
            heating=100.0 * L["rtu_heat"], co2=420.0 + 480.0 * occ + n("co2", 25.0),
            bldg_p=(0.05 + n("bp", 0.01)) if fan_on else 0.0,
            suction=(118.0 + 10.0 * L["dx"] + n("suc", 2.0)) if cooling_pct > 0 else 70.0 + 0.6 * oat,
            head=(220.0 + 4.0 * (oat - 70.0) + n("head", 5.0)) if cooling_pct > 0 else 70.0 + 0.6 * oat,
            sst=(42.0 + n("sst", 1.0)) if cooling_pct > 0 else oat, slt=(52.0 + n("slt", 1.5)) if cooling_pct > 0 else oat,
            dlt=(165.0 + 0.6 * (oat - 70.0) + n("dlt", 3.0)) if cooling_pct > 0 else oat + 5.0,
            hood=fan_on and 10.5 <= L["lt"].hour + L["lt"].minute / 60.0 <= 14.0)

        # VAV_1..10 under RTU_1
        for i in range(s.vav_count):
            design, minf = 600.0, 150.0
            if not fan_on:
                flow_sp = 0.0
            elif mode == "heating":
                flow_sp = minf + 0.25 * (design - minf) * L["valves"][i]
            else:
                phase = 1.0 + 0.2 * math.sin(math.radians(i * 36.0 + 90.0))
                flow_sp = minf + (design - minf) * clamp(cool * occ * phase, 0.0, 1.0)
            flow = max(0.0, flow_sp * (1.0 + n(f"fl{i}", 0.03, 300.0))) if fan_on else 0.0
            u[f"VAV_{i + 1}"] = dict(
                zone=zones[i], sat=u["RTU_1"]["sat"], flow=flow, flow_sp=flow_sp,
                damper=clamp(100.0 * (flow_sp / design) ** 0.7, 5.0, 100.0) if fan_on else 0.0,
                vp=0.15 * (flow / 400.0) ** 2, reheat=100.0 * L["valves"][i] if fan_on or heat > 0 else 0.0,
                eff_clg=clg_sp, eff_htg=htg_sp, zn_sp=72.0, occupied=occupied,
                dat=u["RTU_1"]["sat"] + 30.0 * L["valves"][i] if fan_on else zones[i])

        # AHU_1: single zone, chilled and hot water
        ahu_zone = zone_target + n("ahuzn", 0.6, 1500.0)
        oad = (100.0 if L["econ_only"] else 20.0) if fan_on else 0.0
        mat = (oad / 100.0) * oat + (1.0 - oad / 100.0) * (ahu_zone + 1.0) if fan_on else ahu_zone
        if mode == "cooling":
            dat_sp = 55.0
        elif mode == "heating":
            dat_sp = 75.0 + 20.0 * heat
        else:
            dat_sp = 65.0
        u["AHU_1"] = dict(
            fan_on=fan_on, zone=ahu_zone, rat=ahu_zone + 1.0, mat=mat, pht=max(mat, 48.0) if oat < 40 else mat,
            dat=(dat_sp + n("ahudat", 0.8)) if fan_on else ahu_zone - 1.0, dat_sp=dat_sp,
            clg=100.0 * clamp(cool * 1.1, 0.0, 1.0) if fan_on and mode == "cooling" and not L["econ_only"] else 0.0,
            htg=100.0 * clamp(heat * 1.1, 0.0, 1.0) if fan_on and mode == "heating" else 0.0,
            oad=oad, moad=20.0 if fan_on else 0.0, rad=(100.0 - oad) if fan_on else 0.0,
            phfbd=100.0 if (fan_on and oat < 40.0) else 0.0, rh=clamp(space_rh + n("ahurh", 2.0), 20.0, 60.0),
            co2=420.0 + 420.0 * occ + n("ahuco2", 20.0), oat=oat, eff_clg=clg_sp, eff_htg=htg_sp, occupied=occupied,
            # AHU_STATE: 1 Satisfied, 2 Econ, 4 HX Cool+Mech, 5 HX Heat
            state=(2 if L["econ_only"] else 4) if mode == "cooling" and fan_on else (5 if mode == "heating" and fan_on else 1))

        # CHWS_1: air-cooled chiller plant
        on = L["chw_on"]
        chws = (44.0 + n("chws", 0.4)) if on else clamp(62.0 + 0.2 * (oat - 60.0), 50.0, 75.0)
        dt = 6.0 + 6.0 * L["chw_load"] if on else 0.5
        u["CHWS_1"] = dict(on=on, chws=chws, chwr=chws + dt + (n("chwr", 0.3) if on else 0.0), dt=dt, oat=oat,
                           p1=(40.0 + 50.0 * L["chw_load"]) if on else 0.0, p2_on=on and L["chw_load"] > 0.85,
                           p2=(40.0 + 50.0 * L["chw_load"]) if on and L["chw_load"] > 0.85 else 0.0,
                           room=70.0 + n("chwroom", 1.5, 3600.0))

        # HWS_1: boiler plant, outdoor-air reset
        on = L["hw_on"]
        reset = clamp(180.0 - (oat - 10.0) * (60.0 / 50.0), 120.0, 180.0)
        phws = (reset + n("phws", 1.5)) if on else clamp(90.0 + 0.3 * (oat - 60.0), 75.0, 110.0)
        u["HWS_1"] = dict(on=on, reset=reset, phws=phws, phwr=phws - ((10.0 + 10.0 * L["hw_load"]) if on else 1.0),
                          dp=(12.0 + n("hwdp", 0.4)) if on else 0.3, p1=(40.0 + 50.0 * L["hw_load"]) if on else 0.0,
                          p2_on=on and L["hw_load"] > 0.85, oat=oat, fire=L["hw_load"])

        # EF_1..5 and CUH_1..3
        lt = L["lt"]
        for i in range(s.ef_count):
            on = self.ef_on(i, occ, lt)
            u[f"EF_{i + 1}"] = dict(on=on, speed=(65.0 + 10.0 * h01(seed, "efspd", i)) if on else 0.0)
        for i in range(s.cuh_count):
            on = self.cuh_on(i, ts, heat)
            entry = 66.0 + (2.0 if on else 0.0) if heat > 0 else clamp(70.0 + 0.3 * (oat - 65.0), 68.0, 80.0)
            u[f"CUH_{i + 1}"] = dict(on=on, zone=entry + n(f"cuhzn{i}", 0.6, 900.0), occupied=occupied,
                                     eff_htg=sched.heating_setpoint_occupied if occupied else sched.heating_setpoint_unoccupied,
                                     eff_clg=clg_sp)
        return u

    # ---------------- live interface (same as SiteModel)

    def tick(self, now: datetime) -> SharedState:
        self.state = self.state_at(now.timestamp())
        return self.state

    def peak_demand_kw(self, scope: str) -> float:
        ts = self.state.timestamp.timestamp() if self.state else datetime.now().timestamp()
        return self.peak_demand_at(ts, scope)


def _hhmm(s: str) -> float:
    h, m = s.split(":")
    return int(h) + int(m) / 60.0
