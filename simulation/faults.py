"""
Fault injection system for BACnet simulator.
Simulates real-world equipment failures for training and diagnostic testing.
"""
import random
import time


class FaultManager:
    """Manages active faults across the simulated building."""

    def __init__(self):
        self.active_faults = {}  # fault_id -> Fault instance

    def inject(self, fault):
        """Inject a fault. Takes effect on next simulation tick."""
        self.active_faults[fault.fault_id] = fault
        print(f"  FAULT INJECTED: {fault}")

    def clear(self, fault_id):
        """Clear a fault by ID."""
        if fault_id in self.active_faults:
            fault = self.active_faults.pop(fault_id)
            print(f"  FAULT CLEARED: {fault}")

    def clear_all(self):
        """Clear all active faults."""
        self.active_faults.clear()
        print("  ALL FAULTS CLEARED")

    def get_faults_for_device(self, device_name):
        """Get all active faults affecting a specific device."""
        return [f for f in self.active_faults.values() if f.device == device_name]

    def list_faults(self):
        """Print all active faults."""
        if not self.active_faults:
            print("  No active faults")
            return
        for fid, f in self.active_faults.items():
            print(f"  [{fid}] {f}")


class Fault:
    """Base class for all fault types."""

    def __init__(self, fault_id, device, description):
        self.fault_id = fault_id
        self.device = device
        self.description = description
        self.injected_at = time.time()

    def __str__(self):
        return f"{self.device} — {self.description}"


class StuckDamper(Fault):
    """
    Damper actuator stuck at a fixed position.
    Commands are sent but damper doesn't move. Airflow doesn't match setpoint.
    Common cause: stripped actuator gear, seized shaft, disconnected linkage.
    """

    def __init__(self, device, stuck_position=50.0):
        super().__init__(f"stuck_damper_{device}", device,
                         f"Damper stuck at {stuck_position}%")
        self.stuck_position = stuck_position

    def apply(self, commanded_position):
        """Returns actual position regardless of command."""
        return self.stuck_position


class StuckValve(Fault):
    """
    Valve stuck open or closed.
    Common cause: actuator failure, scale buildup, linkage disconnect.
    """

    def __init__(self, device, point_name, stuck_position=0.0):
        super().__init__(f"stuck_valve_{device}_{point_name}", device,
                         f"{point_name} stuck at {stuck_position}%")
        self.point_name = point_name
        self.stuck_position = stuck_position

    def apply(self, commanded_position):
        return self.stuck_position


class LeakingValve(Fault):
    """
    Valve doesn't fully close — leaks through when commanded to 0%.
    Results in unwanted heating/cooling. G36 FDD should detect this.
    """

    def __init__(self, device, point_name, leak_pct=15.0):
        super().__init__(f"leaking_valve_{device}_{point_name}", device,
                         f"{point_name} leaking at {leak_pct}% when closed")
        self.point_name = point_name
        self.leak_pct = leak_pct

    def apply(self, commanded_position):
        return max(self.leak_pct, commanded_position)


class FanFailure(Fault):
    """
    Fan doesn't start or loses proof during operation.
    Status never goes to proof even when commanded. Triggers fan fail alarm.
    """

    def __init__(self, device):
        super().__init__(f"fan_failure_{device}", device,
                         "Fan failure — no proof of airflow")

    def apply_status(self, commanded):
        """Fan status is always OFF regardless of command."""
        return False


class SensorDrift(Fault):
    """
    Sensor reading slowly drifts from actual value.
    Common cause: calibration drift, fouled sensor, wiring degradation.
    """

    def __init__(self, device, point_name, drift_rate_per_min=0.1, max_drift=5.0):
        super().__init__(f"sensor_drift_{device}_{point_name}", device,
                         f"{point_name} drifting at {drift_rate_per_min}F/min, max {max_drift}F")
        self.point_name = point_name
        self.drift_rate_per_min = drift_rate_per_min
        self.max_drift = max_drift
        self.accumulated_drift = 0.0

    def apply(self, actual_value, dt_sec):
        """Add drift to actual sensor reading."""
        self.accumulated_drift += self.drift_rate_per_min * (dt_sec / 60.0)
        self.accumulated_drift = min(self.accumulated_drift, self.max_drift)
        return actual_value + self.accumulated_drift


class SensorFailure(Fault):
    """
    Sensor fails — reads a fixed value (stuck) or out-of-range.
    Common cause: broken wire, shorted sensor, failed transmitter.
    """

    def __init__(self, device, point_name, failure_value=0.0):
        super().__init__(f"sensor_fail_{device}_{point_name}", device,
                         f"{point_name} failed — reads {failure_value}")
        self.point_name = point_name
        self.failure_value = failure_value

    def apply(self, actual_value):
        return self.failure_value


class CommunicationLoss(Fault):
    """
    Device stops responding on the network.
    All reads return stale values, writes are ignored.
    """

    def __init__(self, device):
        super().__init__(f"comm_loss_{device}", device,
                         "Communication loss — device offline")
        self.frozen_values = {}

    def freeze_values(self, current_values):
        """Capture current values at time of comm loss."""
        self.frozen_values = dict(current_values)

    def apply(self, point_name, live_value):
        """Return frozen value instead of live."""
        return self.frozen_values.get(point_name, live_value)


class IntermittentFault(Fault):
    """
    Fault that comes and goes randomly.
    Simulates loose connections, intermittent sensor issues.
    """

    def __init__(self, device, inner_fault, probability=0.3):
        super().__init__(f"intermittent_{inner_fault.fault_id}", device,
                         f"Intermittent: {inner_fault.description} ({probability*100:.0f}% of time)")
        self.inner_fault = inner_fault
        self.probability = probability
        self.currently_active = False

    def is_active(self):
        """Randomly decide if fault is active this tick."""
        self.currently_active = random.random() < self.probability
        return self.currently_active
