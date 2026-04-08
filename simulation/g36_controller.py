"""
G36 Controller — Python implementation of core G36 sequences for closed-loop
simulation testing. Mirrors the Java G36 sequencer logic.

This is the simulation controller, NOT the production code.
Production deployment uses the Java/Niagara ProgramComponent templates.
"""
import math


class PiController:
    """PI controller with anti-windup. Direct or reverse acting."""

    def __init__(self, kp, ki, out_min, out_max, reverse=False):
        self.kp = kp
        self.ki = ki
        self.out_min = out_min
        self.out_max = out_max
        self.reverse = reverse
        self.integral = 0.0
        self.output = out_min

    def execute(self, dt_sec, setpoint, pv):
        if dt_sec <= 0:
            return self.output
        error = setpoint - pv
        if self.reverse:
            error = -error

        p_term = self.kp * error
        candidate = p_term + self.integral + self.ki * error * dt_sec

        if self.out_min <= candidate <= self.out_max:
            self.integral += self.ki * error * dt_sec
        elif candidate < self.out_min and error > 0:
            self.integral += self.ki * error * dt_sec
        elif candidate > self.out_max and error < 0:
            self.integral += self.ki * error * dt_sec

        self.output = max(self.out_min, min(self.out_max, p_term + self.integral))
        return self.output

    def reset(self, value=None):
        self.integral = 0.0
        self.output = value if value is not None else self.out_min


class TrimAndRespond:
    """G36 Trim-and-Respond setpoint reset algorithm."""

    def __init__(self, sp0, sp_min, sp_max, delay_sec, step_sec,
                 ignores, sp_trim, sp_res, sp_res_max):
        self.sp0 = sp0
        self.sp_min = sp_min
        self.sp_max = sp_max
        self.delay_sec = delay_sec
        self.step_sec = step_sec
        self.ignores = ignores
        self.sp_trim = sp_trim
        self.sp_res = sp_res
        self.sp_res_max = sp_res_max

        self.setpoint = sp0
        self.started = False
        self.start_time = 0
        self.last_step_time = 0

    def start(self, now_sec):
        self.setpoint = self.sp0
        self.start_time = now_sec
        self.last_step_time = now_sec
        self.started = True

    def stop(self):
        self.started = False

    def execute(self, now_sec, requests):
        if not self.started:
            return self.setpoint
        if now_sec - self.start_time < self.delay_sec:
            return self.setpoint
        if now_sec - self.last_step_time < self.step_sec:
            return self.setpoint

        self.last_step_time = now_sec
        active = requests - self.ignores

        if active <= 0:
            self.setpoint += self.sp_trim
        else:
            response = self.sp_res * active
            if self.sp_res_max > 0:
                response = min(response, self.sp_res_max)
            else:
                response = max(response, self.sp_res_max)
            self.setpoint += response

        self.setpoint = max(self.sp_min, min(self.sp_max, self.setpoint))
        return self.setpoint


class G36VavReheat:
    """
    G36 Section 5.6 — Single-Duct VAV with Reheat.
    Dual-maximum heating logic. Reads sensor values, outputs damper and valve commands.
    """

    def __init__(self, v_cool_max, v_min, v_heat_max, max_t=20.0):
        self.v_cool_max = v_cool_max
        self.v_min = v_min
        self.v_heat_max = v_heat_max
        self.max_t = max_t

        self.occ_clg_sp = 75.0
        self.occ_htg_sp = 70.0

        self.clg_loop = PiController(10.0, 0.5, 0, 100, reverse=True)
        self.htg_loop = PiController(10.0, 0.5, 0, 100, reverse=False)
        self.flow_loop = PiController(2.0, 0.3, 0, 100, reverse=False)
        self.dat_loop = PiController(5.0, 1.0, 0, 100, reverse=False)

        # State
        self.zone_state = "deadband"
        self.flow_sp = v_min
        self.dmpr_cmd = 50.0
        self.htg_vlv = 0.0
        self.clg_sat_requests = 0
        self.sp_reset_requests = 0
        self.htg_sat_requests = 0

        # Request timers
        self._clg_5f_start = None
        self._clg_3f_start = None
        self._clg_latch = False
        self._sp_50_start = None
        self._sp_70_start = None
        self._sp_latch = False

    def execute(self, dt_sec, now_sec, zn_temp, da_flow, da_temp, occupied=True):
        """
        Execute one scan cycle. Returns (dmpr_cmd, htg_vlv, zone_state, flow_sp).
        """
        clg_sp = self.occ_clg_sp if occupied else 85.0
        htg_sp = self.occ_htg_sp if occupied else 60.0
        dat_limit = htg_sp + self.max_t

        clg_out = self.clg_loop.execute(dt_sec, clg_sp, zn_temp)
        htg_out = self.htg_loop.execute(dt_sec, htg_sp, zn_temp)

        if zn_temp > clg_sp:
            self.zone_state = "cooling"
            self.flow_sp = self.v_min + (clg_out / 100.0) * (self.v_cool_max - self.v_min)
            self.htg_vlv = 0.0
            self.htg_loop.reset()

        elif zn_temp >= htg_sp:
            self.zone_state = "deadband"
            self.flow_sp = self.v_min
            self.htg_vlv = 0.0
            self.clg_loop.reset()
            self.htg_loop.reset()

        else:
            self.clg_loop.reset()
            if htg_out < 100.0:
                self.zone_state = "heating-p1"
                self.flow_sp = self.v_min
                self.htg_vlv = htg_out
            else:
                self.zone_state = "heating-p2"
                temp_below = htg_sp - zn_temp
                phase2_pct = min(temp_below / 5.0 * 100.0, 100.0)
                self.flow_sp = self.v_min + (phase2_pct / 100.0) * (self.v_heat_max - self.v_min)
                self.htg_vlv = 100.0

            # DAT limiting
            dat_override = self.dat_loop.execute(dt_sec, dat_limit, da_temp)
            self.htg_vlv = min(self.htg_vlv, dat_override)

        self.dmpr_cmd = self.flow_loop.execute(dt_sec, self.flow_sp, da_flow)

        # Zone requests
        self._update_requests(now_sec, zn_temp, clg_sp, htg_sp, clg_out, htg_out, da_flow)

        return self.dmpr_cmd, self.htg_vlv, self.zone_state, self.flow_sp

    def _update_requests(self, now, zn_t, clg_sp, htg_sp, clg_out, htg_out, da_flow):
        # Cooling SAT requests
        over5 = zn_t > clg_sp + 5
        over3 = zn_t > clg_sp + 3
        if over5:
            if self._clg_5f_start is None: self._clg_5f_start = now
            if now - self._clg_5f_start >= 120: self.clg_sat_requests = 3; return
        else:
            self._clg_5f_start = None
        if over3:
            if self._clg_3f_start is None: self._clg_3f_start = now
            if now - self._clg_3f_start >= 120: self.clg_sat_requests = 2; return
        else:
            self._clg_3f_start = None
        if clg_out > 95: self._clg_latch = True
        if clg_out < 85: self._clg_latch = False
        self.clg_sat_requests = 1 if self._clg_latch else 0

        # Static pressure requests
        starving50 = self.flow_sp > 0 and da_flow < 0.5 * self.flow_sp and self.dmpr_cmd > 95
        starving70 = self.flow_sp > 0 and da_flow < 0.7 * self.flow_sp and self.dmpr_cmd > 95
        if starving50:
            if self._sp_50_start is None: self._sp_50_start = now
            if now - self._sp_50_start >= 60: self.sp_reset_requests = 3; return
        else:
            self._sp_50_start = None
        if starving70:
            if self._sp_70_start is None: self._sp_70_start = now
            if now - self._sp_70_start >= 60: self.sp_reset_requests = 2; return
        else:
            self._sp_70_start = None
        if self.dmpr_cmd > 95: self._sp_latch = True
        if self.dmpr_cmd < 85: self._sp_latch = False
        self.sp_reset_requests = 1 if self._sp_latch else 0


class G36AhuController:
    """
    G36 Section 5.16 — Multi-Zone VAV AHU controller.
    Manages SP reset, SAT reset, and output sequencing.
    """

    def __init__(self, sp_max=2.0, min_clg_sat=55.0, max_clg_sat=65.0):
        self.sp_reset = TrimAndRespond(
            sp0=0.5, sp_min=0.1, sp_max=sp_max,
            delay_sec=600, step_sec=120, ignores=2,
            sp_trim=-0.05, sp_res=0.06, sp_res_max=0.13)

        self.sat_reset = TrimAndRespond(
            sp0=max_clg_sat, sp_min=min_clg_sat, sp_max=max_clg_sat,
            delay_sec=600, step_sec=120, ignores=2,
            sp_trim=0.2, sp_res=-0.3, sp_res_max=-1.0)

        self.sp_loop = PiController(5.0, 0.5, 0, 100, reverse=False)
        self.sat_loop = PiController(5.0, 0.5, 0, 100, reverse=True)

        self.min_oa_pos = 20.0
        self.econ_limit = 75.0

        # Outputs
        self.fan_cmd = False
        self.fan_spd = 0.0
        self.chw_vlv = 0.0
        self.hw_vlv = 0.0
        self.oa_dmpr = 20.0
        self.ra_dmpr = 80.0
        self.sat_sp = max_clg_sat
        self.sp_sp = 0.5

    def start(self, now_sec):
        self.sp_reset.start(now_sec)
        self.sat_reset.start(now_sec)
        self.fan_cmd = True

    def execute(self, dt_sec, now_sec, sa_temp, ma_temp, oa_temp, duct_sp,
                sp_requests, sat_requests):
        """Execute one AHU scan cycle."""
        if not self.fan_cmd:
            self.fan_spd = 0
            self.chw_vlv = 0
            self.hw_vlv = 0
            self.oa_dmpr = 0
            self.ra_dmpr = 100
            return

        # SP reset
        self.sp_sp = self.sp_reset.execute(now_sec, sp_requests)

        # Fan speed
        self.fan_spd = self.sp_loop.execute(dt_sec, self.sp_sp, duct_sp)

        # SAT reset
        self.sat_sp = self.sat_reset.execute(now_sec, sat_requests)

        # SAT control loop
        loop_out = self.sat_loop.execute(dt_sec, self.sat_sp, sa_temp)

        # Sequence outputs
        econ_enabled = oa_temp < self.econ_limit

        if loop_out < 25:
            self.hw_vlv = (1.0 - loop_out / 25.0) * 100.0
            self.oa_dmpr = self.min_oa_pos
            self.chw_vlv = 0
        elif loop_out < 50:
            self.hw_vlv = 0
            if econ_enabled:
                self.oa_dmpr = self.min_oa_pos + ((loop_out - 25) / 25.0) * (100 - self.min_oa_pos)
            else:
                self.oa_dmpr = self.min_oa_pos
            self.chw_vlv = 0
        else:
            self.hw_vlv = 0
            self.oa_dmpr = 100 if econ_enabled else self.min_oa_pos
            self.chw_vlv = (loop_out - 50) / 50.0 * 100.0

        self.oa_dmpr = max(self.oa_dmpr, self.min_oa_pos)
        self.ra_dmpr = 100 - self.oa_dmpr

        # Freeze protection
        if ma_temp < 34:
            self.fan_cmd = False
            self.fan_spd = 0
            self.oa_dmpr = 0
            self.ra_dmpr = 100
            self.hw_vlv = 100
            self.chw_vlv = 0
        elif ma_temp < 40:
            self.oa_dmpr = min(self.oa_dmpr, self.min_oa_pos)
            self.ra_dmpr = 100 - self.oa_dmpr
