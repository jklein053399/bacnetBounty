"""E-Mon Class 3200 electrical meter — BAC0 implementation.

Point list per the manufacturer manual §12 (BACnet Object Descriptors),
confirmed in .claude/references/hbt-bms-E-Mon-Class-3200-Meter-Installation-Instructions-62-0390-04.pdf.

One instance = one BACnet device on its own IP. scope="A"|"B"|"C" selects which
meter rollup from the SiteModel drives this device's kW.

Vendor identifier 224 per ASHRAE BACnet Vendor ID list (https://bacnet.org/vendorid/).
E-Mon was acquired by Honeywell Building Technologies; real Class 3200 meters still
expose vendor 224, which is what we match here for Niagara template compatibility.
"""
from __future__ import annotations

import logging
import math
import random as _r

import BAC0
from BAC0.core.devices.local.factory import analog_input, ObjectFactory

from ..site_model import SiteModel


log = logging.getLogger(__name__)

EMON_VENDOR_ID = 224
EMON_VENDOR_NAME = "E-Mon"
EMON_MODEL_NAME = "Class 3200"
EMON_FIRMWARE = "4.11"


# (instance, name, description, units) — names match E-Mon's own documentation
# verbatim so Niagara's E-Mon device template maps cleanly.
POINTS: list[tuple[int, str, str, str | None]] = [
    (1,  "Energy_delivered",           "Energy delivered (kWh)",                 "kilowattHours"),
    (2,  "Energy_received",            "Energy received (kWh)",                  "kilowattHours"),
    (3,  "Reactive_energy_delivered",  "Reactive energy delivered (kVARh)",      "kilovoltAmpereHoursReactive"),
    (4,  "Reactive_energy_received",   "Reactive energy received (kVARh)",       "kilovoltAmpereHoursReactive"),
    (5,  "Real_power",                 "Real power (kW)",                        "kilowatts"),
    (6,  "Reactive_power",             "Reactive power (kVAR)",                  "kilovoltAmperesReactive"),
    (7,  "Apparent_power",             "Apparent power (kVA)",                   "kilovoltAmperes"),
    (8,  "Power_factor",               "Power factor (%)",                       "percent"),
    (9,  "Peak_demand",                "Peak demand kW (15-min fixed window)",   "kilowatts"),
    (10, "Current_average",            "Current average (Amps)",                 "amperes"),
    (11, "Voltage_LN",                 "Voltage line-neutral (Volts)",           "volts"),
    (12, "Voltage_LL",                 "Voltage line-line (Volts)",              "volts"),
    (13, "Frequency",                  "Frequency (Hz)",                         "hertz"),
    (14, "Phase_angle",                "Phase angle (Degrees)",                  "degreesAngular"),
    (15, "Real_power_phase_A",         "Real power phase A (kW)",                "kilowatts"),
    (16, "Real_power_phase_B",         "Real power phase B (kW)",                "kilowatts"),
    (17, "Real_power_phase_C",         "Real power phase C (kW)",                "kilowatts"),
    (18, "Reactive_power_phase_A",     "Reactive power phase A (kVAR)",          "kilovoltAmperesReactive"),
    (19, "Reactive_power_phase_B",     "Reactive power phase B (kVAR)",          "kilovoltAmperesReactive"),
    (20, "Reactive_power_phase_C",     "Reactive power phase C (kVAR)",          "kilovoltAmperesReactive"),
    (21, "Apparent_power_phase_A",     "Apparent power phase A (kVA)",           "kilovoltAmperes"),
    (22, "Apparent_power_phase_B",     "Apparent power phase B (kVA)",           "kilovoltAmperes"),
    (23, "Apparent_power_phase_C",     "Apparent power phase C (kVA)",           "kilovoltAmperes"),
    (24, "Power_factor_phase_A",       "Power factor phase A (%)",               "percent"),
    (25, "Power_factor_phase_B",       "Power factor phase B (%)",               "percent"),
    (26, "Power_factor_phase_C",       "Power factor phase C (%)",               "percent"),
    (27, "Current_phase_A",            "Current phase A (Amps)",                 "amperes"),
    (28, "Current_phase_B",            "Current phase B (Amps)",                 "amperes"),
    (29, "Current_phase_C",            "Current phase C (Amps)",                 "amperes"),
    (30, "Voltage_LN_phase_A",         "Voltage line-neutral phase A-N (Volts)", "volts"),
    (31, "Voltage_LN_phase_B",         "Voltage line-neutral phase B-N (Volts)", "volts"),
    (32, "Voltage_LN_phase_C",         "Voltage line-neutral phase C-N (Volts)", "volts"),
    (33, "Voltage_LL_phase_AB",        "Voltage line-line phase A-B (Volts)",    "volts"),
    (34, "Voltage_LL_phase_BC",        "Voltage line-line phase B-C (Volts)",    "volts"),
    (35, "Voltage_LL_phase_CA",        "Voltage line-line phase C-A (Volts)",    "volts"),
    (36, "Phase_angle_A",              "Phase angle A (Degrees)",                "degreesAngular"),
    (37, "Phase_angle_B",              "Phase angle B (Degrees)",                "degreesAngular"),
    (38, "Phase_angle_C",              "Phase angle C (Degrees)",                "degreesAngular"),
    (39, "Reserve_A",                  "Reserve A",                              "noUnits"),
    (40, "Reserve_B",                  "Reserve B",                              "noUnits"),
    (41, "Reserve_C",                  "Reserve C",                              "noUnits"),
    (42, "External_Input_1",           "External Input 1 (Pulse)",               "noUnits"),
    (43, "External_Input_2",           "External Input 2 (Pulse)",               "noUnits"),
]


def _create_emon_points():
    """Register all 43 AIs with BAC0's ObjectFactory.

    Returns the last-created factory object so the caller can do
    `add_objects_to_application(bacnet)` once.

    Important: caller MUST call ObjectFactory.clear_objects() before this
    if multiple devices are being built in the same process, or later
    devices will inherit earlier devices' points.
    """
    obj = None
    for instance, name, desc, units in POINTS:
        props = {"units": units} if units else {}
        obj = analog_input(
            name=name,
            instance=instance,
            description=desc,
            presentValue=0.0,
            properties=props,
        )
    return obj


class EmonClass3200:
    """One E-Mon Class 3200 BACnet device bound to a specific IP.

    scope: "A" (building), "B" (AHU_2+3 + VAVs), "C" (AHU_2+3 only).
    """

    def __init__(
        self,
        device_id: int,
        device_name: str,
        local_ip: str,
        subnet_mask_prefix: int,
        bacnet_port: int,
        scope: str,
        site_model: SiteModel,
    ):
        if scope not in ("A", "B", "C"):
            raise ValueError(f"EmonClass3200 scope must be A/B/C, got {scope!r}")

        self.device_id = device_id
        self.device_name = device_name
        self.local_ip = local_ip
        self.bacnet_port = bacnet_port
        self.scope = scope
        self.site = site_model

        # Multi-device pattern: clear any points carried over from a prior device
        ObjectFactory.clear_objects()

        self.bacnet = BAC0.lite(
            ip=f"{local_ip}/{subnet_mask_prefix}",
            port=bacnet_port,
            deviceId=device_id,
            localObjName=device_name,
            vendorId=EMON_VENDOR_ID,
            vendorName=EMON_VENDOR_NAME,
            modelName=EMON_MODEL_NAME,
            firmwareRevision=EMON_FIRMWARE,
            description=f"E-Mon Class 3200 electrical meter — scope {scope}",
            location="32K Michigan Office Demo",
        )

        # BAC0 quirk: vendorName kwarg is accepted but doesn't propagate to the
        # actual DeviceObject on the wire (stays as BAC0 default "Servisys inc.").
        # vendorIdentifier and modelName DO propagate. Find the device object by
        # iterating the registry (keys are ObjectType-enum tuples, not strings)
        # and patch vendorName directly.
        try:
            bp_app = self.bacnet.this_application.app
            dev_obj = None
            for (otype, inst), obj in bp_app.objectIdentifier.items():
                if inst == device_id and "device" in str(otype).lower():
                    dev_obj = obj
                    break
            if dev_obj is not None:
                dev_obj.vendorName = EMON_VENDOR_NAME
                dev_obj.description = f"E-Mon Class 3200 electrical meter - scope {scope}"
            else:
                log.warning(f"{device_name}: device object not found in registry for vendorName patch")
        except Exception as e:
            log.warning(f"{device_name}: could not patch vendorName: {e}")

        last = _create_emon_points()
        if last is None:
            raise RuntimeError("EMON point creation returned no object")
        last.add_objects_to_application(self.bacnet)

        # Deterministic per-device RNG for phase imbalance jitter
        self._rng = _r.Random(device_id)

    # ---------- Per-tick update ----------

    def update(self) -> None:
        """Refresh all 43 AI presentValues from the SiteModel."""
        s = self.site.state
        if s is None:
            return
        cfg = self.site.config.magnitudes

        if self.scope == "A":
            real_kw = s.meter_a_kw
            kwh = s.meter_a_kwh
        elif self.scope == "B":
            real_kw = s.meter_b_kw
            kwh = s.meter_b_kwh
        else:
            real_kw = s.meter_c_kw
            kwh = s.meter_c_kwh

        pf = cfg.power_factor_nominal
        v_ln = cfg.voltage_phase_nominal
        v_ll = cfg.voltage_nominal

        # --- Primary and derived totals ---
        kvar = real_kw * math.tan(math.acos(pf)) if pf < 1 else 0.0
        kva = real_kw / pf if pf > 0 else real_kw
        reactive_kvarh = kwh * math.tan(math.acos(pf)) if pf < 1 else 0.0
        current_avg = (real_kw * 1000.0) / (v_ll * math.sqrt(3) * pf) if pf > 0 else 0.0
        peak_demand = self.site.peak_demand_kw(self.scope)

        # --- Per-phase split with small ±3% imbalance ---
        imb_a = 1.0 + self._rng.uniform(-0.03, 0.03)
        imb_b = 1.0 + self._rng.uniform(-0.03, 0.03)
        imb_c = 3.0 - imb_a - imb_b
        # Reseed for stable jitter across ticks (we want consistent imbalance, not drift)
        self._rng = _r.Random(self.device_id)

        kw_a = real_kw / 3.0 * imb_a
        kw_b = real_kw / 3.0 * imb_b
        kw_c = real_kw / 3.0 * imb_c
        kvar_a = kvar / 3.0 * imb_a
        kvar_b = kvar / 3.0 * imb_b
        kvar_c = kvar / 3.0 * imb_c
        kva_a = kva / 3.0 * imb_a
        kva_b = kva / 3.0 * imb_b
        kva_c = kva / 3.0 * imb_c
        i_a = (kw_a * 1000.0) / (v_ln * pf) if pf > 0 else 0.0
        i_b = (kw_b * 1000.0) / (v_ln * pf) if pf > 0 else 0.0
        i_c = (kw_c * 1000.0) / (v_ln * pf) if pf > 0 else 0.0

        v_ln_a = v_ln + self._rng.uniform(-0.5, 0.5)
        v_ln_b = v_ln + self._rng.uniform(-0.5, 0.5)
        v_ln_c = v_ln + self._rng.uniform(-0.5, 0.5)
        v_ab = ((v_ln_a + v_ln_b) / 2) * math.sqrt(3)
        v_bc = ((v_ln_b + v_ln_c) / 2) * math.sqrt(3)
        v_ca = ((v_ln_c + v_ln_a) / 2) * math.sqrt(3)

        values: dict[str, float] = {
            "Energy_delivered": kwh,
            "Energy_received": 0.0,
            "Reactive_energy_delivered": reactive_kvarh,
            "Reactive_energy_received": 0.0,
            "Real_power": real_kw,
            "Reactive_power": kvar,
            "Apparent_power": kva,
            "Power_factor": pf * 100.0,
            "Peak_demand": peak_demand,
            "Current_average": current_avg,
            "Voltage_LN": v_ln,
            "Voltage_LL": v_ll,
            "Frequency": 60.0,
            "Phase_angle": 0.0,
            "Real_power_phase_A": kw_a,
            "Real_power_phase_B": kw_b,
            "Real_power_phase_C": kw_c,
            "Reactive_power_phase_A": kvar_a,
            "Reactive_power_phase_B": kvar_b,
            "Reactive_power_phase_C": kvar_c,
            "Apparent_power_phase_A": kva_a,
            "Apparent_power_phase_B": kva_b,
            "Apparent_power_phase_C": kva_c,
            "Power_factor_phase_A": pf * 100.0,
            "Power_factor_phase_B": pf * 100.0,
            "Power_factor_phase_C": pf * 100.0,
            "Current_phase_A": i_a,
            "Current_phase_B": i_b,
            "Current_phase_C": i_c,
            "Voltage_LN_phase_A": v_ln_a,
            "Voltage_LN_phase_B": v_ln_b,
            "Voltage_LN_phase_C": v_ln_c,
            "Voltage_LL_phase_AB": v_ab,
            "Voltage_LL_phase_BC": v_bc,
            "Voltage_LL_phase_CA": v_ca,
            "Phase_angle_A": 0.0,
            "Phase_angle_B": -120.0,
            "Phase_angle_C": 120.0,
            "Reserve_A": 0.0,
            "Reserve_B": 0.0,
            "Reserve_C": 0.0,
            "External_Input_1": 0.0,
            "External_Input_2": 0.0,
        }

        for name, value in values.items():
            try:
                self.bacnet[name].presentValue = float(value)
            except (KeyError, AttributeError) as e:
                log.warning(f"{self.device_name}: failed to update {name}: {e}")

    def close(self) -> None:
        if self.bacnet is not None:
            try:
                self.bacnet.disconnect()
            except Exception as e:
                log.warning(f"{self.device_name}: disconnect error: {e}")
