"""
Simple chiller plant thermal model for simulation.
Models CHW supply/return temps, chiller staging response, and cooling tower.
"""
import random


class ChillerPlantModel:
    """2-chiller plant with primary/secondary pumps and cooling tower."""

    def __init__(self, num_chillers=2, capacity_per_chiller=500):
        self.num_chillers = num_chillers
        self.capacity_per_chiller = capacity_per_chiller

        # State
        self.chwst = 44.0           # CHW supply temp (deg F)
        self.chwrt = 56.0           # CHW return temp (deg F)
        self.chw_flow = 0.0         # Primary flow (GPM)
        self.chw_dp = 12.0          # Differential pressure (psi)
        self.cwst = 75.0            # CW supply temp (deg F)
        self.cwrt = 85.0            # CW return temp (deg F)
        self.oa_wet_bulb = 72.0

        # Per-chiller state
        self.chiller_running = [False] * num_chillers
        self.chiller_load_pct = [0.0] * num_chillers
        self.chiller_kw = [0.0] * num_chillers

        # Plant parameters
        self.design_flow_per_chiller = 600  # GPM per chiller
        self.building_load_tons = 0.0

    def step(self, dt_sec, chiller_cmds, pump_cmds, pump_speeds, ct_fan_speed,
             chwst_sp, building_load_tons):
        """
        Advance plant model one time step.

        Args:
            chiller_cmds: list of bool, command per chiller
            pump_cmds: list of bool, primary pump commands
            pump_speeds: list of float, secondary pump speeds (%)
            ct_fan_speed: cooling tower fan speed (%)
            chwst_sp: active CHWST setpoint
            building_load_tons: current building cooling load
        """
        self.building_load_tons = building_load_tons

        # Count running chillers
        num_running = 0
        for i in range(self.num_chillers):
            self.chiller_running[i] = chiller_cmds[i] and pump_cmds[i]
            if self.chiller_running[i]:
                num_running += 1

        # Flow: proportional to number of running pumps
        self.chw_flow = sum(1 for p in pump_cmds if p) * self.design_flow_per_chiller

        if num_running == 0 or self.chw_flow == 0:
            # No chillers — plant off, temps drift toward ambient
            self.chwst += (75.0 - self.chwst) * 0.001 * dt_sec
            self.chwrt += (75.0 - self.chwrt) * 0.001 * dt_sec
            self.chw_dp = 0
            for i in range(self.num_chillers):
                self.chiller_load_pct[i] = 0
                self.chiller_kw[i] = 0
            return

        # Plant capacity
        total_capacity = num_running * self.capacity_per_chiller

        # CHWRT rises with building load
        # Q = flow * (CHWRT - CHWST) / 24 → CHWRT = CHWST + Q*24/flow
        if self.chw_flow > 0:
            target_chwrt = self.chwst + (building_load_tons * 24.0) / self.chw_flow
            alpha = min(1.0, dt_sec / 120.0)  # 2-minute time constant
            self.chwrt += alpha * (target_chwrt - self.chwrt)
            self.chwrt = max(self.chwst, min(100, self.chwrt))

        # CHWST: chillers drive toward setpoint
        target_chwst = chwst_sp
        chiller_alpha = min(1.0, dt_sec / 60.0)  # 1-minute lag
        self.chwst += chiller_alpha * (target_chwst - self.chwst)
        self.chwst = max(38, min(60, self.chwst))
        # Add noise
        self.chwst += random.gauss(0, 0.1)

        # Per-chiller load
        load_per_chiller = building_load_tons / max(1, num_running)
        for i in range(self.num_chillers):
            if self.chiller_running[i]:
                self.chiller_load_pct[i] = min(100, (load_per_chiller / self.capacity_per_chiller) * 100)
                # kW: roughly 0.6 kW/ton at part load
                self.chiller_kw[i] = load_per_chiller * 0.6
            else:
                self.chiller_load_pct[i] = 0
                self.chiller_kw[i] = 0

        # DP: proportional to flow squared, offset by secondary pump speed
        avg_pump_spd = sum(pump_speeds) / max(1, len(pump_speeds))
        self.chw_dp = 15.0 * (avg_pump_spd / 100.0) ** 2
        self.chw_dp += random.gauss(0, 0.2)
        self.chw_dp = max(0, self.chw_dp)

        # Cooling tower: CW temps
        # Tower drives CWST toward wet bulb + approach
        approach = max(5.0, 15.0 - (ct_fan_speed / 100.0) * 10.0)
        target_cwst = self.oa_wet_bulb + approach
        ct_alpha = min(1.0, dt_sec / 180.0)
        self.cwst += ct_alpha * (target_cwst - self.cwst)
        self.cwrt = self.cwst + 10.0 * (building_load_tons / max(1, total_capacity))
