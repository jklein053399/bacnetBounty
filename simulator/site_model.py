"""Site-level simulation model — OAT, occupancy, lighting/plug, HVAC loads, meter rollup.

Pure Python math, no BACnet awareness. Tick-driven. Devices read current values
off this object to populate their present-values each tick.

Per spec §6: OAT drives everything thermal; occupancy drives loads. Level-1
couplings only (plausible not physically derived), with Level-2 exceptions for
kWh integrals and meter nesting (A >= B >= C at every tick).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime

from .config import Config


_MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_MISC_ALWAYS_ON_KW = 10.0  # servers/networking/phantom loads beyond itemized


@dataclass
class SiteState:
    """Snapshot of all site-level values at a given tick.

    Everything downstream devices need reads off this struct.
    """
    timestamp: datetime

    # Weather
    oat_f: float                        # outside air temperature, deg F

    # Occupancy / schedule
    occupancy_fraction: float           # 0.0 - 1.0
    lighting_scheduled: bool            # are main lights on per schedule

    # Thermal demand drivers (0..1)
    cooling_load_fraction: float
    heating_load_fraction: float
    gas_heating_fraction: float         # AHU preheat demand (boiler-fed), not VAV reheat (electric)

    # Itemized electric loads (kW)
    lighting_kw: float
    plug_kw: float
    ahu_sz_kw: float                    # AHU_1
    ahu_vav_1_kw: float                 # AHU_2
    ahu_vav_2_kw: float                 # AHU_3
    vav_reheat_total_kw: float          # sum across 20 VAVs
    misc_kw: float                      # always-on miscellaneous

    # Meter scopes (kW, derived)
    meter_a_kw: float                   # building total
    meter_b_kw: float                   # AHU_2+3 + all VAVs (incl. reheat)
    meter_c_kw: float                   # AHU_2+3 only (no VAVs)

    # Gas (SCFH)
    gas_scfh: float
    gas_temp_f: float                   # pipe reads near ambient

    # Water (GPM)
    water_gpm: float
    water_temp_f: float                 # domestic cold, stable ~55F

    # Per-AHU supply air temperature (degF) — primary data for AHU devices
    # and shared reference for downstream VAV physics (see VAV discharge-air-temp).
    # Indexed AHU_1 / AHU_2 / AHU_3 in parallel to config order.
    ahu_sat_f: tuple[float, float, float] = (55.0, 55.0, 55.0)

    # Per-VAV reheat valve positions (0.0 .. 1.0). Primary data for Meter B
    # rollup (per spec doc 03 §Flag 1: "reheat valve position × per-VAV max
    # reheat kW is computed at the model layer and rolls up into Meter B's kW").
    # VAV device objects read their own valve by index (parallel to cfg.vavs).
    # Zero drift between per-VAV readings and Meter B — same numbers, same tick.
    vav_valve_positions: tuple[float, ...] = ()

    # Per-VAV zone temperature (degF). Primary data for VAV device objects
    # (Zone_Temperature point). Phase-shifted per-instance from site-wide
    # occupancy + thermal state, deterministic from zone_phase_deg.
    vav_zone_temps_f: tuple[float, ...] = ()

    # Totalizers (integrated across ticks)
    meter_a_kwh: float = 0.0
    meter_b_kwh: float = 0.0
    meter_c_kwh: float = 0.0
    gas_scf_total: float = 0.0
    water_gallons_total: float = 0.0


class SiteModel:
    """Tick-driven site state. Call .tick(now) each interval to advance."""

    def __init__(self, config: Config, seed: int | None = None):
        self.config = config
        self._vav_configs = config.vavs
        self._rng = random.Random(seed)
        self._oat_walk = 0.0  # current random-walk offset
        self._last_tick: datetime | None = None

        # Integrators carried across ticks
        self._meter_a_kwh = 0.0
        self._meter_b_kwh = 0.0
        self._meter_c_kwh = 0.0
        self._gas_scf = 0.0
        self._water_gal = 0.0

        # Peak demand trackers (fixed 15-min windows)
        self._peak_demand_kw: dict[str, float] = {"A": 0.0, "B": 0.0, "C": 0.0}
        self._peak_demand_committed: dict[str, float] = {"A": 0.0, "B": 0.0, "C": 0.0}
        self._current_quarter: tuple[int, int, int, int] | None = None  # (Y, M, D, quarter)

        # Current state (populated on first tick)
        self.state: SiteState | None = None

    # -------- Driver: OAT --------

    def _oat(self, now: datetime) -> float:
        w = self.config.weather
        # Interpolate monthly high/low across day-of-year
        doy = now.timetuple().tm_yday
        month_idx = now.month - 1
        # Use current-month high/low; for smoothness could blend adjacent months,
        # but Level-1 scope says plausible is sufficient.
        hi, lo = w.monthly_high_low_f[month_idx]

        # Diurnal sinusoid: low at trough_hour, high at peak_hour
        hour = now.hour + now.minute / 60.0 + now.second / 3600.0
        # Phase so that diurnal_trough_hour gives -1 (low) and diurnal_peak_hour gives +1 (high)
        # Generic approach: shift cos so its min sits at trough_hour.
        phase = 2 * math.pi * (hour - w.diurnal_trough_hour) / 24.0
        # -cos gives -1 at phase=0 (trough) and +1 at phase=pi (12h later ≈ peak if trough=5, peak=17)
        # Peak hour 15 with trough 5 → 10h apart, reasonable approximation.
        diurnal = -math.cos(phase)
        oat_deterministic = (hi + lo) / 2.0 + (hi - lo) / 2.0 * diurnal

        # Bounded random walk
        step = self._rng.gauss(0, 0.3)
        self._oat_walk = max(-w.random_walk_bound_f, min(w.random_walk_bound_f, self._oat_walk + step))
        return oat_deterministic + self._oat_walk

    # -------- Driver: occupancy --------

    def _occupancy(self, now: datetime) -> float:
        sched = self.config.schedule
        weekday = now.weekday()  # Mon=0..Sun=6
        hour = now.hour + now.minute / 60.0

        if weekday < 5:  # weekday
            start = _parse_hhmm(sched.occupied_weekday_start)
            end = _parse_hhmm(sched.occupied_weekday_end)
            ramp_up = sched.ramp_up_hours
            ramp_down = sched.ramp_down_hours
            if hour < start or hour > end:
                return 0.0
            if hour < start + ramp_up:
                return (hour - start) / ramp_up
            if hour > end - ramp_down:
                return max(0.0, (end - hour) / ramp_down)
            return 1.0
        if weekday == 5:  # Saturday
            if 8.0 <= hour <= 14.0:
                return sched.saturday_peak_fraction
            return 0.0
        # Sunday
        return sched.sunday_baseline_fraction

    def _lighting_scheduled(self, now: datetime) -> bool:
        weekday = now.weekday()
        hour = now.hour + now.minute / 60.0
        if weekday < 5:
            return 6.0 <= hour <= 22.0
        if weekday == 5:
            return 7.0 <= hour <= 15.0
        return False

    # -------- Driver: thermal loads --------

    def _thermal_fractions(self, oat_f: float) -> tuple[float, float]:
        # Cooling load: ramps from 0 at 60F to 1 at 90F
        if oat_f > 60.0:
            cool = min(1.0, (oat_f - 60.0) / 30.0)
        else:
            cool = 0.0
        # Heating/reheat load: ramps from 0 at 55F down to 1 at 15F
        if oat_f < 55.0:
            heat = min(1.0, (55.0 - oat_f) / 40.0)
        else:
            heat = 0.0
        return cool, heat

    # -------- Main tick --------

    def tick(self, now: datetime) -> SiteState:
        cfg = self.config
        mags = cfg.magnitudes

        # Use ACTUAL elapsed wall time since the last tick for integrators, not
        # the configured interval. This keeps kWh accurate under fast/slow tick
        # rates (e.g. test harnesses ticking faster than the 10s default).
        if self._last_tick is None:
            dt_hours = cfg.simulation.tick_interval_seconds / 3600.0
        else:
            dt_seconds = max(0.0, (now - self._last_tick).total_seconds())
            # Guard against absurd jumps (clock skew, paused process, etc.)
            dt_seconds = min(dt_seconds, cfg.simulation.tick_interval_seconds * 10)
            dt_hours = dt_seconds / 3600.0

        oat = self._oat(now)
        occ = self._occupancy(now)
        lighting_on = self._lighting_scheduled(now)
        cool_frac, heat_frac = self._thermal_fractions(oat)

        # Lighting kW: on/off + jitter
        if lighting_on:
            lighting_kw = mags.lighting_peak_kw * (0.95 + 0.05 * self._rng.random())
        else:
            lighting_kw = 2.0 * (0.9 + 0.2 * self._rng.random())  # security baseline

        # Plug kW: occupancy-driven with baseline
        plug_kw = mags.plug_baseline_kw + occ * (mags.plug_peak_kw - mags.plug_baseline_kw)
        plug_kw *= 0.95 + 0.05 * self._rng.random()

        # AHU kW: split into fan (runs whenever AHU is on) + DX compressor (cool_frac only).
        # Fans deliver air for reheat in heating season too, so fan kW must not drop to zero
        # in winter. DX compressors are off in heating season (gas preheat handles it).
        # Rough split: fan+aux ~20% of peak AHU kW; DX compressor ~80%. Matches typical
        # packaged VAV RTU where a 40-ton unit with 10 HP fan + 120 kW compressor sums
        # to ~55 kW peak and ~10 kW fan-only.
        FAN_SHARE = 0.20
        DX_SHARE = 0.80
        # Minimum fan demand when occupied — zones need ventilation air even at zero load
        MIN_FAN_DEMAND = 0.5
        # Fan demand follows whichever season's load is active; heating-season fan demand
        # typically runs 50-70% of design because min-airflow + reheat airflow drives it
        fan_demand = max(MIN_FAN_DEMAND * occ, cool_frac * occ, 0.7 * heat_frac * occ)

        ahu_vav_standby = 0.8  # VFD + controls standby

        ahu_sz_kw = (
            occ * (
                FAN_SHARE * max(MIN_FAN_DEMAND, cool_frac, 0.5 * heat_frac) * mags.ahu_sz_peak_kw
                + DX_SHARE * cool_frac * mags.ahu_sz_peak_kw
            )
        )
        ahu_vav_1_kw = ahu_vav_standby + (
            FAN_SHARE * fan_demand * mags.ahu_vav_peak_kw_each
            + DX_SHARE * occ * cool_frac * mags.ahu_vav_peak_kw_each
        )
        ahu_vav_2_kw = ahu_vav_standby + (
            FAN_SHARE * fan_demand * mags.ahu_vav_peak_kw_each
            + DX_SHARE * occ * cool_frac * mags.ahu_vav_peak_kw_each
        )
        # jitter
        ahu_sz_kw *= 0.97 + 0.06 * self._rng.random()
        ahu_vav_1_kw *= 0.97 + 0.06 * self._rng.random()
        ahu_vav_2_kw *= 0.97 + 0.06 * self._rng.random()

        # VAV electric reheat: heat_frac-driven, scoped to Meters A & B (not C).
        # Per spec doc 03 §Flag 1: valve position × per-VAV max reheat kW rolls
        # up into Meter B. Site model owns per-VAV valve positions as primary
        # data (vav_valve_positions tuple below); Meter B sums them. VAV
        # devices read their own valve by index — zero drift between device
        # readings and Meter B.
        #
        # When no VAVs are configured (earlier phases), fall back to the
        # aggregate heuristic so Meter B still gets a plausible reheat kW.
        reheat_occ_floor = 0.3
        reheat_activity_base = heat_frac * max(reheat_occ_floor, occ)

        vav_valve_positions: tuple[float, ...] = ()
        vav_zone_temps_f: tuple[float, ...] = ()

        if self._vav_configs:
            valves: list[float] = []
            zones: list[float] = []
            for v in self._vav_configs:
                # Per-VAV reheat valve — base activity modulated by per-instance
                # phase offset (±20% of base) so 20 VAVs don't march in lockstep.
                # Perimeter zones run higher reheat load than interior (envelope
                # exposure). Deterministic noise from zone_phase_deg so each
                # tick's value is stable per VAV but varies across VAVs.
                phase_rad = math.radians(v.zone_phase_deg)
                phase_mod = 1.0 + 0.20 * math.sin(phase_rad)  # 0.8 .. 1.2
                position_weight = 1.15 if v.position == "perimeter" else 0.85
                valve = reheat_activity_base * phase_mod * position_weight
                valve = max(0.0, min(1.0, valve))
                valves.append(valve)

                # Per-VAV zone temperature — drifts around the active setpoint
                # with per-instance phase. Cooling season: setpoint 74F;
                # heating season: 70F; shoulder: 72F. Perimeter zones
                # over/undershoot the interior average by ±0.5F (solar/envelope).
                if heat_frac > cool_frac:
                    zone_sp = cfg.schedule.heating_setpoint_occupied if occ > 0 else cfg.schedule.heating_setpoint_unoccupied
                elif cool_frac > heat_frac:
                    zone_sp = cfg.schedule.cooling_setpoint_occupied if occ > 0 else cfg.schedule.cooling_setpoint_unoccupied
                else:
                    zone_sp = 72.0
                drift = 0.8 * math.sin(phase_rad)  # ±0.8F phase-driven
                envelope_bias = 0.5 if v.position == "perimeter" else 0.0
                if heat_frac > cool_frac:
                    envelope_bias = -envelope_bias  # perimeter colder in heating
                zones.append(zone_sp + drift + envelope_bias + self._rng.uniform(-0.3, 0.3))

            vav_valve_positions = tuple(valves)
            vav_zone_temps_f = tuple(zones)
            # Meter B rollup: sum of per-VAV reheat kW. This IS the spec-aligned
            # path (doc 03 §Flag 1). Small jitter applied to the aggregate keeps
            # Meter B visually live tick-to-tick.
            vav_reheat_total_kw = sum(valves) * mags.vav_reheat_peak_kw_each
            vav_reheat_total_kw *= 0.98 + 0.04 * self._rng.random()
        else:
            # Phase 1-3 fallback: aggregate-level reheat kW when no VAVs configured
            vav_reheat_total_kw = reheat_activity_base * 20 * mags.vav_reheat_peak_kw_each
            vav_reheat_total_kw *= 0.95 + 0.1 * self._rng.random()

        misc_kw = _MISC_ALWAYS_ON_KW * (0.95 + 0.1 * self._rng.random())

        # Meter rollups per spec §4
        meter_c_kw = ahu_vav_1_kw + ahu_vav_2_kw
        meter_b_kw = meter_c_kw + vav_reheat_total_kw
        meter_a_kw = meter_b_kw + ahu_sz_kw + lighting_kw + plug_kw + misc_kw

        # Nesting invariant — defensive check (jitter could otherwise edge below)
        if meter_a_kw < meter_b_kw:
            meter_a_kw = meter_b_kw + 0.01
        if meter_b_kw < meter_c_kw:
            meter_b_kw = meter_c_kw + 0.01

        # Integrators: kWh = kW * dt_hours
        self._meter_a_kwh += meter_a_kw * dt_hours
        self._meter_b_kwh += meter_b_kw * dt_hours
        self._meter_c_kwh += meter_c_kw * dt_hours

        # Peak demand tracking (fixed 15-min calendar intervals per handoff §Flag 2)
        self._update_peak_demand(now, {"A": meter_a_kw, "B": meter_b_kw, "C": meter_c_kw})

        # Gas — AHU preheat only (VAV reheat is electric per handoff doc 03 Flag 1).
        # Spec doc 02 Section 3: heating_load_fraction = (1 - OAT/60) clamped, gated
        # by occupancy. Small always-on term (0.3 floor when cold) represents boiler
        # cycling during low-occupancy cold weather. Multiplicative with occupancy
        # so warm-weather unoccupied hours sit at pure baseline (pilot).
        if oat < 60.0:
            oat_term = (60.0 - oat) / 60.0
        else:
            oat_term = 0.0
        gas_heating_fraction = min(1.0, oat_term * (0.3 + 0.7 * occ))

        gas_scfh = mags.gas_baseline_scfh + gas_heating_fraction * (mags.gas_peak_scfh - mags.gas_baseline_scfh)
        gas_scfh *= 0.95 + 0.1 * self._rng.random()
        self._gas_scf += gas_scfh * dt_hours

        # Gas pipe temperature — tracks OAT with small offset (pipe runs outdoor or
        # through service penetration; gas flow warms it slightly vs ambient).
        gas_temp_f = oat + 2.0 + 4.0 * self._rng.random()

        # Water — occupancy-driven with Poisson-ish bursts
        water_base = mags.water_baseline_gpm + occ * (mags.water_peak_gpm * 0.4 - mags.water_baseline_gpm)
        if occ > 0.2 and self._rng.random() < 0.15:
            water_base += self._rng.uniform(2.0, mags.water_peak_gpm)
        water_gpm = max(0.0, water_base)
        self._water_gal += water_gpm * (dt_hours * 60.0)  # GPM * minutes

        # Water temperature — domestic cold, stable ~55F year-round with small jitter
        water_temp_f = 55.0 + self._rng.uniform(-1.0, 1.0)

        # Per-AHU SAT — 55F in cooling season, 65F in heating season, interpolated
        # in shoulder seasons. Per spec 02 §5 AV 1 ("55F cooling / 65F heating
        # schedule"). Small per-AHU drift around the setpoint so device readings
        # don't all sit at the same decimal. VAV physics reads these to compute
        # discharge air temp; AHU devices expose them as Supply_Air_Temperature.
        # Uses raw cool_frac/heat_frac before any occupancy gating — SAT tracks
        # the dominant thermal mode regardless of load level.
        if heat_frac > cool_frac:
            sat_target = 65.0
        elif cool_frac > heat_frac:
            sat_target = 55.0
        else:
            sat_target = 60.0  # shoulder / both zero
        ahu_sat_f = (
            sat_target + self._rng.uniform(-0.8, 0.8),
            sat_target + self._rng.uniform(-0.8, 0.8),
            sat_target + self._rng.uniform(-0.8, 0.8),
        )

        state = SiteState(
            timestamp=now,
            oat_f=oat,
            occupancy_fraction=occ,
            lighting_scheduled=lighting_on,
            cooling_load_fraction=cool_frac,
            heating_load_fraction=heat_frac,
            gas_heating_fraction=gas_heating_fraction,
            lighting_kw=lighting_kw,
            plug_kw=plug_kw,
            ahu_sz_kw=ahu_sz_kw,
            ahu_vav_1_kw=ahu_vav_1_kw,
            ahu_vav_2_kw=ahu_vav_2_kw,
            vav_reheat_total_kw=vav_reheat_total_kw,
            misc_kw=misc_kw,
            meter_a_kw=meter_a_kw,
            meter_b_kw=meter_b_kw,
            meter_c_kw=meter_c_kw,
            gas_scfh=gas_scfh,
            gas_temp_f=gas_temp_f,
            water_gpm=water_gpm,
            water_temp_f=water_temp_f,
            meter_a_kwh=self._meter_a_kwh,
            meter_b_kwh=self._meter_b_kwh,
            meter_c_kwh=self._meter_c_kwh,
            gas_scf_total=self._gas_scf,
            water_gallons_total=self._water_gal,
            ahu_sat_f=ahu_sat_f,
            vav_valve_positions=vav_valve_positions,
            vav_zone_temps_f=vav_zone_temps_f,
        )
        self.state = state
        self._last_tick = now
        return state

    # -------- Peak demand (fixed 15-min calendar window) --------

    def _update_peak_demand(self, now: datetime, kw_by_scope: dict[str, float]) -> None:
        quarter = now.minute // 15
        key = (now.year, now.month, now.day, now.hour * 4 + quarter)

        if self._current_quarter is None:
            self._current_quarter = key

        if key != self._current_quarter:
            # Boundary crossed — commit running max as the peak demand for the PREVIOUS window
            for scope in self._peak_demand_kw:
                self._peak_demand_committed[scope] = self._peak_demand_kw[scope]
                self._peak_demand_kw[scope] = 0.0
            self._current_quarter = key

        for scope, kw in kw_by_scope.items():
            if kw > self._peak_demand_kw[scope]:
                self._peak_demand_kw[scope] = kw

    def peak_demand_kw(self, scope: str) -> float:
        """Committed peak-demand kW for the last completed 15-min window.

        Before the first window closes, falls back to the running max in the
        current window so the point has a sensible value at startup.
        """
        committed = self._peak_demand_committed.get(scope, 0.0)
        if committed > 0.0:
            return committed
        return self._peak_demand_kw.get(scope, 0.0)


def _parse_hhmm(s: str) -> float:
    h, m = s.split(":")
    return int(h) + int(m) / 60.0
