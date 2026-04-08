"""
Simple thermal zone model for simulating VAV box behavior.
First-order model: zone temp responds to supply air, internal loads, and envelope.
"""
import random


class ZoneModel:
    """Single thermal zone served by a VAV box."""

    def __init__(self, name: str, area_sqft: float = 200, design_cfm: float = 800):
        self.name = name
        self.area_sqft = area_sqft
        self.design_cfm = design_cfm

        # State
        self.zone_temp = 72.0           # Current zone temp (deg F)
        self.supply_air_temp = 55.0     # From AHU

        # Thermal parameters
        self.thermal_mass = 50.0        # Higher = slower response (BTU/F)
        self.internal_load = 2000.0     # Internal heat gain (BTU/hr) — people, lights, equipment
        self.envelope_ua = 30.0         # Envelope UA value (BTU/hr/F)
        self.outdoor_temp = 85.0        # Outdoor temp (deg F)

        # Noise
        self.sensor_noise = 0.1         # Sensor noise amplitude (deg F)

    def step(self, dt_sec: float, airflow_cfm: float, reheat_pct: float):
        """
        Advance the zone model by one time step.

        Args:
            dt_sec: Time step in seconds
            airflow_cfm: Current airflow into the zone (CFM)
            reheat_pct: Reheat valve position 0-100%

        Returns:
            Updated zone temperature (deg F)
        """
        dt_hr = dt_sec / 3600.0

        # Supply air temp after reheat: base SAT + reheat contribution
        reheat_rise = (reheat_pct / 100.0) * 35.0  # Max 35F rise at 100%
        actual_sat = self.supply_air_temp + reheat_rise

        # Heat transfer from supply air to zone (BTU/hr)
        # Q = 1.08 × CFM × (T_supply - T_zone)
        q_supply = 1.08 * airflow_cfm * (actual_sat - self.zone_temp)

        # Internal heat gains (BTU/hr)
        q_internal = self.internal_load

        # Envelope heat gain/loss (BTU/hr)
        q_envelope = self.envelope_ua * (self.outdoor_temp - self.zone_temp)

        # Net heat into zone (BTU/hr)
        q_net = q_supply + q_internal + q_envelope

        # Temperature change: dT = Q × dt / thermal_mass
        delta_t = q_net * dt_hr / self.thermal_mass
        self.zone_temp += delta_t

        # Clamp to reasonable range
        self.zone_temp = max(40.0, min(120.0, self.zone_temp))

        return self.zone_temp

    def get_sensed_temp(self) -> float:
        """Zone temp with sensor noise."""
        return self.zone_temp + random.gauss(0, self.sensor_noise)

    def get_discharge_temp(self, reheat_pct: float) -> float:
        """Discharge air temp based on SAT + reheat."""
        reheat_rise = (reheat_pct / 100.0) * 35.0
        return self.supply_air_temp + reheat_rise + random.gauss(0, 0.2)

    def get_airflow(self, damper_pct: float) -> float:
        """Simulated airflow based on damper position and duct static pressure."""
        # Simple linear model: flow proportional to damper position
        min_flow = self.design_cfm * 0.1  # Leakage at 0%
        flow = min_flow + (damper_pct / 100.0) * (self.design_cfm - min_flow)
        # Add measurement noise
        return max(0, flow + random.gauss(0, flow * 0.02))
