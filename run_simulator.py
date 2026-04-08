"""
BACnet HVAC Simulator — Main Entry Point

Usage:
    python run_simulator.py                  # Default: small office (no control)
    python run_simulator.py small_office     # Manual control — write commands via Yabe/Niagara
    python run_simulator.py closed_loop      # G36 closed-loop — controllers drive everything

Scenarios:
    small_office  — 8 BACnet devices, thermal sim, manual control via external client
    closed_loop   — Same devices + G36 VAV/AHU controllers + fault injection schedule
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    scenario = "small_office"
    if len(sys.argv) > 1:
        scenario = sys.argv[1]

    if scenario == "small_office":
        from scenarios.small_office import main as run
        run()
    elif scenario == "closed_loop":
        from scenarios.closed_loop import main as run
        run()
    elif scenario == "chiller_plant":
        from scenarios.chiller_plant import main as run
        run()
    elif scenario == "workbench":
        from scenarios.workbench_integration import main as run
        run()
    else:
        print(f"Unknown scenario: {scenario}")
        print("Available: small_office, closed_loop, chiller_plant, workbench")
        sys.exit(1)


if __name__ == "__main__":
    main()
