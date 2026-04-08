"""
Simple AHU model for simulating multi-zone VAV AHU behavior.
Computes mixed air temp, supply air temp based on valve/damper positions.
"""
import random


class AhuModel:
    """Multi-zone VAV AHU thermal model."""

    def __init__(self):
        # State
        self.supply_air_temp = 55.0
        self.mixed_air_temp = 65.0
        self.return_air_temp = 72.0
        self.outdoor_air_temp = 85.0
        self.duct_static_pressure = 1.0

        # Equipment response lag
        self.sat_lag = 0.3  # Time constant for SAT response

    def step(self, dt_sec: float, oa_dmpr_pct: float, chw_vlv_pct: float,
             hw_vlv_pct: float, fan_spd_pct: float, fan_on: bool):
        """
        Advance AHU model one time step.

        Args:
            dt_sec: Time step in seconds
            oa_dmpr_pct: OA damper position 0-100%
            chw_vlv_pct: CHW valve position 0-100%
            hw_vlv_pct: HW valve position 0-100%
            fan_spd_pct: Fan speed 0-100%
            fan_on: Fan command status
        """
        if not fan_on:
            self.duct_static_pressure = 0
            return

        # Mixed air temperature: blend of OA and RA based on damper position
        oa_fraction = oa_dmpr_pct / 100.0
        self.mixed_air_temp = (oa_fraction * self.outdoor_air_temp +
                                (1 - oa_fraction) * self.return_air_temp)

        # Target SAT based on coil positions
        target_sat = self.mixed_air_temp

        # Cooling coil effect: pulls SAT down toward 42F at 100% valve
        if chw_vlv_pct > 0:
            coil_leaving = 42.0  # CHW coil leaving temp at 100%
            cooling_effect = (chw_vlv_pct / 100.0) * (self.mixed_air_temp - coil_leaving)
            target_sat -= cooling_effect

        # Heating coil effect: pushes SAT up
        if hw_vlv_pct > 0:
            heating_capacity = 40.0  # Max temp rise at 100% valve
            target_sat += (hw_vlv_pct / 100.0) * heating_capacity

        # First-order lag
        alpha = min(1.0, dt_sec / (30.0 / self.sat_lag))  # ~30 second time constant
        self.supply_air_temp += alpha * (target_sat - self.supply_air_temp)
        self.supply_air_temp = max(40.0, min(120.0, self.supply_air_temp))

        # Duct static pressure: proportional to fan speed squared (fan affinity)
        design_sp = 1.5  # Design static pressure at 100% speed
        self.duct_static_pressure = design_sp * (fan_spd_pct / 100.0) ** 2

    def get_sensed_sat(self) -> float:
        return self.supply_air_temp + random.gauss(0, 0.15)

    def get_sensed_mat(self) -> float:
        return self.mixed_air_temp + random.gauss(0, 0.2)

    def get_sensed_sp(self) -> float:
        return max(0, self.duct_static_pressure + random.gauss(0, 0.02))
