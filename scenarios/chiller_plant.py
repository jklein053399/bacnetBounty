"""
Chiller Plant Scenario — 2-chiller plant with G36 staging logic.

Adds chiller plant devices to the building simulation with:
  - OPLR-based chiller staging (G36 Section 5.20.4)
  - CHWST reset via T&R (Section 5.20.5)
  - Primary pump control (dedicated, one per chiller)
  - Secondary pump DP reset
  - Cooling tower fan control
  - Building load driven by VAV zone cooling demand

Network: Same 8 devices as small_office + chiller plant device (Device 5001, port 47816)

Run: python run_simulator.py chiller_plant
"""
import asyncio
import sys
import os
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from devices.jace8000 import create_jace_points
from devices.jci_fec_vav import create_fec_vav_points
from devices.aaon_rtu import create_aaon_rtu_points
from devices.jci_fec_misc import create_misc_controller_points
from devices.chiller_plant import create_all_plant_points
from simulation.zone_model import ZoneModel
from simulation.ahu_model import AhuModel
from simulation.plant_model import ChillerPlantModel
from simulation.g36_controller import G36VavReheat, G36AhuController, TrimAndRespond, PiController

VAV_ZONES = [
    ("Interior-1",  600,  2500, 250),
    ("Interior-2",  600,  2000, 250),
    ("Perim-South", 900,  4000, 300),
    ("Perim-North", 800,  1500, 300),
    ("Conf-Room",   1200, 6000, 400),
]

SIM_INTERVAL = 2.0

# Plant staging thresholds (simplified SPLR)
SPLR_UP = 0.85
SPLR_DN = 0.85
STAGE_TIMER_SEC = 60  # Shortened from 900 for demo (real: 15 min)


async def start_device(device_id, name, port, point_creator, *args):
    import BAC0
    bacnet = await BAC0.lite(deviceId=device_id, localObjName=name, port=port).__aenter__()
    obj = point_creator(*args)
    obj.add_objects_to_application(bacnet)
    return bacnet


async def run_scenario():
    import BAC0
    BAC0.log_level("error")

    print("=" * 60)
    print("  Chiller Plant + Building Simulation")
    print("  G36 staging, T&R resets, thermal response")
    print("=" * 60)
    print()

    devices = []

    try:
        # --- Start building devices ---
        jace = await start_device(1001, "JACE-8000", 47808, create_jace_points)
        devices.append(jace)

        vav_devs = []
        for i, (name, cfm, load, area) in enumerate(VAV_ZONES):
            dev = await start_device(2001 + i, f"FEC-VAV{i+1}", 47809 + i,
                                     create_fec_vav_points, name, cfm)
            vav_devs.append(dev)
            devices.append(dev)

        rtu = await start_device(3001, "AAON-RTU", 47814, create_aaon_rtu_points)
        devices.append(rtu)

        misc = await start_device(4001, "FEC-MISC", 47815, create_misc_controller_points)
        devices.append(misc)

        # --- Chiller plant device ---
        plant_dev = await start_device(5001, "CHW-PLANT", 47816, create_all_plant_points)
        devices.append(plant_dev)

        print(f"All {len(devices)} devices online (including chiller plant on port 47816).")

        # --- Initialize models ---
        zones = []
        for name, cfm, load, area in VAV_ZONES:
            z = ZoneModel(name, area_sqft=area, design_cfm=cfm)
            z.internal_load = load
            z.outdoor_temp = 90.0  # Hot day to drive chiller load
            zones.append(z)

        ahu_model = AhuModel()
        ahu_model.outdoor_air_temp = 90.0

        plant_model = ChillerPlantModel(num_chillers=2, capacity_per_chiller=500)
        plant_model.oa_wet_bulb = 76.0

        # --- G36 controllers ---
        vav_ctrls = []
        for name, cfm, load, area in VAV_ZONES:
            vav_ctrls.append(G36VavReheat(v_cool_max=cfm, v_min=cfm * 0.3, v_heat_max=cfm * 0.6))

        ahu_ctrl = G36AhuController(sp_max=2.0, min_clg_sat=55.0, max_clg_sat=65.0)
        ahu_ctrl.start(0)

        # Plant resets
        chwst_reset = TrimAndRespond(
            sp0=48.0, sp_min=42.0, sp_max=48.0,
            delay_sec=600, step_sec=120, ignores=2,
            sp_trim=0.1, sp_res=-0.2, sp_res_max=-0.6)
        chwst_reset.start(0)

        dp_reset = TrimAndRespond(
            sp0=15.0, sp_min=3.75, sp_max=15.0,
            delay_sec=600, step_sec=120, ignores=2,
            sp_trim=-1.0, sp_res=2.0, sp_res_max=4.0)
        dp_reset.start(0)

        sec_pump_pi = PiController(3.0, 0.3, 20, 100, reverse=False)
        ct_fan_pi = PiController(3.0, 0.5, 20, 100, reverse=True)

        # Plant state
        num_chillers_on = 0
        plant_enabled = False
        last_stage_change = 0
        stage_up_start = None
        stage_down_start = None

        rtu["SF-CMD"].presentValue = "active"
        rtu["SF-SPD"].presentValue = 75.0

        print("Simulation running. Press Ctrl+C to stop.")
        print("-" * 60)

        tick = 0
        sim_time = 0.0

        while True:
            await asyncio.sleep(SIM_INTERVAL)
            tick += 1
            sim_time += SIM_INTERVAL

            oat = 90.0 + 5.0 * random.gauss(0, 0.3)  # Hot day with variation
            jace["OAT"].presentValue = round(oat, 1)
            ahu_model.outdoor_air_temp = oat

            # --- AHU model ---
            ahu_model.step(SIM_INTERVAL, float(ahu_ctrl.oa_dmpr),
                          float(ahu_ctrl.chw_vlv), float(ahu_ctrl.hw_vlv),
                          float(ahu_ctrl.fan_spd), ahu_ctrl.fan_cmd)

            rtu["SA-T"].presentValue = round(ahu_model.get_sensed_sat(), 1)
            rtu["MA-T"].presentValue = round(ahu_model.get_sensed_mat(), 1)
            rtu["SA-SP"].presentValue = round(ahu_model.get_sensed_sp(), 2)

            # --- VAV zones + G36 controllers ---
            total_sp_req = 0
            total_sat_req = 0
            total_chw_demand = 0  # Proxy for building load

            for i, (zone, vav_dev, ctrl) in enumerate(zip(zones, vav_devs, vav_ctrls)):
                zone.supply_air_temp = ahu_model.supply_air_temp
                airflow = zone.get_airflow(ctrl.dmpr_cmd)
                zone.step(SIM_INTERVAL, airflow, ctrl.htg_vlv)

                zn_temp = zone.get_sensed_temp()
                da_temp = zone.get_discharge_temp(ctrl.htg_vlv)

                vav_dev["ZN-T"].presentValue = round(zn_temp, 1)
                vav_dev["DA-CFM"].presentValue = round(airflow, 0)
                vav_dev["DA-T"].presentValue = round(da_temp, 1)

                ctrl.execute(SIM_INTERVAL, sim_time, zn_temp, airflow, da_temp)

                vav_dev["DPR-O"].presentValue = round(ctrl.dmpr_cmd, 1)
                vav_dev["HTG-O"].presentValue = round(ctrl.htg_vlv, 1)

                total_sp_req += ctrl.sp_reset_requests
                total_sat_req += ctrl.clg_sat_requests

                # Estimate building load from cooling demand
                if ctrl.zone_state == "cooling":
                    total_chw_demand += (ctrl.clg_loop.output / 100.0) * zone.design_cfm * 0.05

            # --- AHU G36 controller ---
            ahu_ctrl.execute(SIM_INTERVAL, sim_time,
                            ahu_model.supply_air_temp,
                            ahu_model.mixed_air_temp,
                            oat, ahu_model.duct_static_pressure,
                            total_sp_req, total_sat_req)

            # --- Building load (tons) ---
            building_load = max(10, total_chw_demand + random.gauss(0, 5))

            # --- Plant enable/disable ---
            chw_valve_pct = ahu_ctrl.chw_vlv
            plant_request = 1 if chw_valve_pct > 95 else 0

            if not plant_enabled and oat > 55 and chw_valve_pct > 30:
                plant_enabled = True
                num_chillers_on = 1
                last_stage_change = sim_time
                print(f"  [t={sim_time:.0f}s] PLANT ENABLED — Chiller 1 ON")

            if plant_enabled and oat < 54:
                plant_enabled = False
                num_chillers_on = 0
                print(f"  [t={sim_time:.0f}s] PLANT DISABLED — OAT lockout")

            # --- OPLR staging ---
            if plant_enabled and num_chillers_on > 0:
                stage_capacity = num_chillers_on * 500
                oplr = building_load / stage_capacity if stage_capacity > 0 else 0

                # Stage up
                if num_chillers_on < 2 and sim_time - last_stage_change > STAGE_TIMER_SEC:
                    if oplr > SPLR_UP:
                        if stage_up_start is None:
                            stage_up_start = sim_time
                        elif sim_time - stage_up_start > STAGE_TIMER_SEC:
                            num_chillers_on = 2
                            last_stage_change = sim_time
                            stage_up_start = None
                            print(f"  [t={sim_time:.0f}s] STAGE UP — Chiller 2 ON (OPLR={oplr:.2f})")
                    else:
                        stage_up_start = None

                # Stage down
                if num_chillers_on > 1 and sim_time - last_stage_change > STAGE_TIMER_SEC:
                    lower_capacity = (num_chillers_on - 1) * 500
                    oplr_lower = building_load / lower_capacity if lower_capacity > 0 else 999
                    if oplr_lower < SPLR_DN:
                        if stage_down_start is None:
                            stage_down_start = sim_time
                        elif sim_time - stage_down_start > STAGE_TIMER_SEC:
                            num_chillers_on = 1
                            last_stage_change = sim_time
                            stage_down_start = None
                            print(f"  [t={sim_time:.0f}s] STAGE DOWN — Chiller 2 OFF (OPLR_lower={oplr_lower:.2f})")
                    else:
                        stage_down_start = None

            # --- Plant model step ---
            chiller_cmds = [i < num_chillers_on for i in range(2)]
            pump_cmds = chiller_cmds[:]
            chwst_sp = chwst_reset.execute(sim_time, int(chw_valve_pct > 95))
            ct_fan = ct_fan_pi.execute(SIM_INTERVAL, 80.0, plant_model.cwrt)

            plant_model.step(SIM_INTERVAL, chiller_cmds, pump_cmds,
                           [70.0, 70.0], ct_fan, chwst_sp, building_load)

            # --- Update plant BACnet points ---
            plant_dev["CHW_SUPPLY_TEMP"].presentValue = round(plant_model.chwst, 1)
            plant_dev["CHW_RETURN_TEMP"].presentValue = round(plant_model.chwrt, 1)
            plant_dev["CHW_DP"].presentValue = round(plant_model.chw_dp, 1)
            plant_dev["CHW_FLOW"].presentValue = round(plant_model.chw_flow, 0)
            plant_dev["CHW_SUPPLY_TEMP_SP"].presentValue = round(chwst_sp, 1)
            plant_dev["CW_SUPPLY_TEMP"].presentValue = round(plant_model.cwst, 1)
            plant_dev["CW_RETURN_TEMP"].presentValue = round(plant_model.cwrt, 1)
            plant_dev["NUM_CH_ON"].presentValue = float(num_chillers_on)
            plant_dev["CHW_PLANT_LOAD"].presentValue = round(building_load, 1)

            for ch_id in [1, 2]:
                idx = ch_id - 1
                plant_dev[f"CH{ch_id}_CMD"].presentValue = "active" if chiller_cmds[idx] else "inactive"
                plant_dev[f"CH{ch_id}_STS"].presentValue = "active" if chiller_cmds[idx] else "inactive"
                plant_dev[f"CH{ch_id}_CHWST"].presentValue = round(plant_model.chwst, 1)
                plant_dev[f"CH{ch_id}_LOAD"].presentValue = round(plant_model.chiller_load_pct[idx], 1)
                plant_dev[f"CH{ch_id}_KW"].presentValue = round(plant_model.chiller_kw[idx], 1)

            for p in [1, 2]:
                idx = p - 1
                plant_dev[f"CHWP{p}_CMD"].presentValue = "active" if pump_cmds[idx] else "inactive"
                plant_dev[f"CHWP{p}_STS"].presentValue = "active" if pump_cmds[idx] else "inactive"

            plant_dev["CT1_FAN_SPD"].presentValue = round(ct_fan, 1)

            # --- Status print ---
            if tick % 15 == 0:
                oplr_val = building_load / (num_chillers_on * 500) if num_chillers_on > 0 else 0
                print(f"[t={sim_time:.0f}s] Load={building_load:.0f}T  "
                      f"Chillers={num_chillers_on}  OPLR={oplr_val:.2f}  "
                      f"CHWST={plant_model.chwst:.1f}F(sp={chwst_sp:.1f})  "
                      f"CWRT={plant_model.cwrt:.1f}F  CT={ct_fan:.0f}%")
                for i, (zone, ctrl) in enumerate(zip(zones, vav_ctrls)):
                    print(f"  VAV-{i+1} {zone.name:14s}  "
                          f"ZnT={zone.zone_temp:.1f}F  [{ctrl.zone_state:11s}]  "
                          f"Dmpr={ctrl.dmpr_cmd:.0f}%")
                print()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for dev in reversed(devices):
            try:
                await dev.__aexit__(None, None, None)
            except Exception:
                pass
        print("All devices stopped.")


def main():
    asyncio.run(run_scenario())


if __name__ == "__main__":
    main()
