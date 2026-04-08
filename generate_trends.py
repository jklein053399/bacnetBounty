"""
Generate a simulated 24-hour day of trend data for the small office building.

Outputs CSV files with 1-minute interval data for all key points:
  - AHU trends (SAT, MAT, fan speed, valve positions, mode)
  - VAV trends per zone (zone temp, airflow, damper, reheat, state)
  - Outdoor conditions (OAT, RH)
  - Plant trends (CHWST, CWRT, chiller status, load)

Simulates realistic daily profile:
  05:00 — Morning warmup begins
  07:00 — Occupied, zones cooling down
  09:00 — Full occupancy, loads climbing
  14:00 — Afternoon peak (solar + internal)
  18:00 — Unoccupied, setback
  22:00 — Overnight minimum

Run: python generate_trends.py
Output: trends/ directory with CSV files
"""
import csv
import os
import math
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation.zone_model import ZoneModel
from simulation.ahu_model import AhuModel
from simulation.plant_model import ChillerPlantModel
from simulation.g36_controller import G36VavReheat, G36AhuController

# --- Configuration ---
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trends")
STEP_SEC = 10          # Simulation step (seconds)
RECORD_INTERVAL = 60   # Write to CSV every 60 seconds
TOTAL_HOURS = 24

VAV_ZONES = [
    # (name, design_cfm, base_internal_load_btu, area_sqft)
    ("Interior-1",  600,  2500, 250),
    ("Interior-2",  600,  2000, 250),
    ("Perim-South", 900,  3000, 300),  # Solar varies
    ("Perim-North", 800,  1500, 300),
    ("Conf-Room",   1200, 1000, 400),  # Occupancy varies
]


def oat_profile(hour):
    """Outdoor air temperature profile — typical summer day."""
    # Low at 5AM (~72F), peak at 3PM (~95F)
    return 83.0 + 12.0 * math.sin((hour - 9.0) / 24.0 * 2 * math.pi)


def oat_rh_profile(hour):
    """Outdoor RH — inverse of temperature."""
    return 60.0 - 15.0 * math.sin((hour - 9.0) / 24.0 * 2 * math.pi)


def solar_load_factor(hour):
    """South-facing solar gain factor (0-1). Peak at 1PM."""
    if hour < 6 or hour > 20:
        return 0.0
    return max(0, math.sin((hour - 6.0) / 14.0 * math.pi))


def occupancy_factor(hour, zone_name):
    """Occupancy schedule factor (0-1)."""
    if "Conf" in zone_name:
        # Conference room: meetings 9-11, 13-15
        if 9 <= hour < 11 or 13 <= hour < 15:
            return 1.0
        elif 7 <= hour < 18:
            return 0.2
        return 0.0
    else:
        # Office zones: 7AM-6PM occupied
        if 7 <= hour < 8:
            return (hour - 7.0)  # Ramp up
        elif 8 <= hour < 17:
            return 1.0
        elif 17 <= hour < 18:
            return (18.0 - hour)  # Ramp down
        return 0.0


def is_occupied(hour):
    """Building schedule: occupied 6:30AM to 6PM."""
    return 6.5 <= hour < 18.0


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Initialize models ---
    zones = []
    for name, cfm, load, area in VAV_ZONES:
        z = ZoneModel(name, area_sqft=area, design_cfm=cfm)
        z.internal_load = load
        z.zone_temp = 68.0  # Start cool (overnight)
        zones.append(z)

    ahu = AhuModel()
    plant = ChillerPlantModel(num_chillers=2, capacity_per_chiller=500)

    vav_ctrls = []
    for name, cfm, load, area in VAV_ZONES:
        ctrl = G36VavReheat(v_cool_max=cfm, v_min=cfm * 0.3, v_heat_max=cfm * 0.6)
        vav_ctrls.append(ctrl)

    ahu_ctrl = G36AhuController(sp_max=2.0, min_clg_sat=55.0, max_clg_sat=65.0)

    # --- Open CSV files ---
    ahu_file = open(os.path.join(OUTPUT_DIR, "ahu_trends.csv"), "w", newline="")
    ahu_writer = csv.writer(ahu_file)
    ahu_writer.writerow([
        "Timestamp", "Hour", "OAT", "OA_RH", "SAT", "SAT_SP", "MAT",
        "Fan_Spd", "CHW_Vlv", "HW_Vlv", "OA_Dmpr", "SP_SP",
        "Mode", "Occupied"
    ])

    vav_files = []
    vav_writers = []
    for i, (name, cfm, load, area) in enumerate(VAV_ZONES):
        f = open(os.path.join(OUTPUT_DIR, f"vav{i+1}_{name.lower().replace('-','_')}.csv"), "w", newline="")
        w = csv.writer(f)
        w.writerow([
            "Timestamp", "Hour", "ZN_Temp", "CLG_SP", "HTG_SP",
            "DA_Flow", "Flow_SP", "Dmpr_Cmd", "HTG_Vlv",
            "DA_Temp", "CLG_Loop", "HTG_Loop", "Zone_State",
            "Internal_Load", "Occupancy"
        ])
        vav_files.append(f)
        vav_writers.append(w)

    plant_file = open(os.path.join(OUTPUT_DIR, "plant_trends.csv"), "w", newline="")
    plant_writer = csv.writer(plant_file)
    plant_writer.writerow([
        "Timestamp", "Hour", "CHWST", "CHWRT", "CHW_Flow",
        "Chillers_On", "CH1_Load", "CH2_Load", "CH1_KW", "CH2_KW",
        "CWST", "CWRT", "Building_Load_Tons"
    ])

    # --- Simulation loop ---
    total_steps = int(TOTAL_HOURS * 3600 / STEP_SEC)
    records_written = 0
    last_record_time = -RECORD_INTERVAL

    print(f"Generating {TOTAL_HOURS}-hour trend data...")
    print(f"  Step interval: {STEP_SEC}s")
    print(f"  Record interval: {RECORD_INTERVAL}s")
    print(f"  Output: {OUTPUT_DIR}/")
    print()

    num_chillers_on = 0
    plant_enabled = False

    for step in range(total_steps):
        sim_sec = step * STEP_SEC
        hour = sim_sec / 3600.0
        timestamp = f"{int(hour):02d}:{int((sim_sec % 3600) / 60):02d}:{int(sim_sec % 60):02d}"

        # --- Outdoor conditions ---
        oat = oat_profile(hour)
        oa_rh = oat_rh_profile(hour)
        ahu.outdoor_air_temp = oat
        plant.oa_wet_bulb = oat - 10  # Rough wet bulb approximation

        # --- Occupancy ---
        occ = is_occupied(hour)

        # --- AHU mode ---
        if not ahu_ctrl.fan_cmd and occ and hour > 5.5:
            ahu_ctrl.start(sim_sec)
        elif ahu_ctrl.fan_cmd and not occ and hour > 18.5:
            ahu_ctrl.fan_cmd = False

        # --- Update zone loads ---
        for i, (zone, (name, cfm, base_load, area)) in enumerate(zip(zones, VAV_ZONES)):
            zone.outdoor_temp = oat
            solar = solar_load_factor(hour)
            occ_factor = occupancy_factor(hour, name)

            # Internal load varies with occupancy
            people_load = occ_factor * 250 * (area / 100)  # ~250 BTU/person, density varies
            lights_load = occ_factor * base_load * 0.4
            equip_load = occ_factor * base_load * 0.4 + base_load * 0.1  # 10% always on
            solar_load = solar * 1500 if "South" in name else solar * 300

            zone.internal_load = people_load + lights_load + equip_load + solar_load

            # Update VAV controller setpoints based on occupancy
            if occ:
                vav_ctrls[i].occ_clg_sp = 75.0
                vav_ctrls[i].occ_htg_sp = 70.0
            else:
                vav_ctrls[i].occ_clg_sp = 85.0
                vav_ctrls[i].occ_htg_sp = 60.0

        # --- AHU model step ---
        ahu.step(STEP_SEC, float(ahu_ctrl.oa_dmpr),
                float(ahu_ctrl.chw_vlv), float(ahu_ctrl.hw_vlv),
                float(ahu_ctrl.fan_spd), ahu_ctrl.fan_cmd)

        # --- VAV + G36 controllers ---
        total_sp_req = 0
        total_sat_req = 0
        total_cooling_demand = 0

        for i, (zone, ctrl) in enumerate(zip(zones, vav_ctrls)):
            zone.supply_air_temp = ahu.supply_air_temp
            airflow = zone.get_airflow(ctrl.dmpr_cmd)
            zone.step(STEP_SEC, airflow, ctrl.htg_vlv)

            zn_t = zone.get_sensed_temp()
            da_t = zone.get_discharge_temp(ctrl.htg_vlv)
            ctrl.execute(STEP_SEC, sim_sec, zn_t, airflow, da_t, occ)

            total_sp_req += ctrl.sp_reset_requests
            total_sat_req += ctrl.clg_sat_requests
            if ctrl.zone_state == "cooling":
                total_cooling_demand += (ctrl.clg_loop.output / 100.0) * zone.design_cfm * 0.05

        # --- AHU G36 controller ---
        if ahu_ctrl.fan_cmd:
            ahu_ctrl.execute(STEP_SEC, sim_sec,
                            ahu.supply_air_temp, ahu.mixed_air_temp,
                            oat, ahu.duct_static_pressure,
                            total_sp_req, total_sat_req)

        # --- Plant staging ---
        building_load = max(0, total_cooling_demand)

        if not plant_enabled and oat > 60 and ahu_ctrl.chw_vlv > 30:
            plant_enabled = True
            num_chillers_on = 1

        if plant_enabled and (oat < 55 or not ahu_ctrl.fan_cmd):
            plant_enabled = False
            num_chillers_on = 0

        if plant_enabled and num_chillers_on > 0:
            stage_cap = num_chillers_on * 500
            oplr = building_load / stage_cap if stage_cap > 0 else 0
            if num_chillers_on < 2 and oplr > 0.85:
                num_chillers_on = 2
            if num_chillers_on > 1:
                lower_oplr = building_load / 500 if building_load > 0 else 0
                if lower_oplr < 0.5:
                    num_chillers_on = 1

        chiller_cmds = [i < num_chillers_on for i in range(2)]
        plant.step(STEP_SEC, chiller_cmds, chiller_cmds, [70, 70], 60.0,
                  44.0, building_load)

        # --- Write CSV records ---
        if sim_sec - last_record_time >= RECORD_INTERVAL:
            last_record_time = sim_sec
            records_written += 1

            mode = "Occupied" if ahu_ctrl.fan_cmd else "Unoccupied"

            ahu_writer.writerow([
                timestamp, f"{hour:.2f}", f"{oat:.1f}", f"{oa_rh:.0f}",
                f"{ahu.supply_air_temp:.1f}", f"{ahu_ctrl.sat_sp:.1f}",
                f"{ahu.mixed_air_temp:.1f}",
                f"{ahu_ctrl.fan_spd:.1f}", f"{ahu_ctrl.chw_vlv:.1f}",
                f"{ahu_ctrl.hw_vlv:.1f}", f"{ahu_ctrl.oa_dmpr:.1f}",
                f"{ahu_ctrl.sp_sp:.2f}", mode, occ
            ])

            for i, (zone, ctrl) in enumerate(zip(zones, vav_ctrls)):
                clg_sp = ctrl.occ_clg_sp
                htg_sp = ctrl.occ_htg_sp
                occ_f = occupancy_factor(hour, VAV_ZONES[i][0])
                vav_writers[i].writerow([
                    timestamp, f"{hour:.2f}", f"{zone.zone_temp:.1f}",
                    f"{clg_sp:.0f}", f"{htg_sp:.0f}",
                    f"{zone.get_airflow(ctrl.dmpr_cmd):.0f}", f"{ctrl.flow_sp:.0f}",
                    f"{ctrl.dmpr_cmd:.1f}", f"{ctrl.htg_vlv:.1f}",
                    f"{zone.get_discharge_temp(ctrl.htg_vlv):.1f}",
                    f"{ctrl.clg_loop.output:.1f}", f"{ctrl.htg_loop.output:.1f}",
                    ctrl.zone_state, f"{zone.internal_load:.0f}", f"{occ_f:.2f}"
                ])

            plant_writer.writerow([
                timestamp, f"{hour:.2f}",
                f"{plant.chwst:.1f}", f"{plant.chwrt:.1f}",
                f"{plant.chw_flow:.0f}",
                num_chillers_on,
                f"{plant.chiller_load_pct[0]:.1f}", f"{plant.chiller_load_pct[1]:.1f}",
                f"{plant.chiller_kw[0]:.1f}", f"{plant.chiller_kw[1]:.1f}",
                f"{plant.cwst:.1f}", f"{plant.cwrt:.1f}",
                f"{building_load:.1f}"
            ])

        # Progress
        if step % (total_steps // 24) == 0:
            print(f"  {timestamp} — OAT={oat:.0f}F  Zones: ", end="")
            for z in zones:
                print(f"{z.zone_temp:.0f}", end=" ")
            print(f" Chillers={num_chillers_on}  Load={building_load:.0f}T")

    # --- Close files ---
    ahu_file.close()
    for f in vav_files:
        f.close()
    plant_file.close()

    print()
    print(f"Done! {records_written} records written per file.")
    print(f"Files in: {OUTPUT_DIR}/")
    print(f"  ahu_trends.csv")
    for i, (name, _, _, _) in enumerate(VAV_ZONES):
        print(f"  vav{i+1}_{name.lower().replace('-','_')}.csv")
    print(f"  plant_trends.csv")


if __name__ == "__main__":
    main()
