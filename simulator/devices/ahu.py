"""Generic AHU BACnet device — BAC0 implementation.

Point list per spec 02 §5 (with AV/BV substitutions for commandable points per
doc 04 Flag E). Three instances in the manifest: AHU_1 (single-zone), AHU_2
and AHU_3 (VAV). All share this class; per-instance behavior is driven off
the AHUConfig passed in.

Physics lives in simulator/ahu_physics.py (architectural invariant #2). This
class is a thin wrapper: construct BACnet objects, then each tick call
compute_ahu_state() and ship the result to presentValues.

Vendor name "Metro Controls" — simulator-specific. No public vendor ID for
generic AHUs in ASHRAE's list, so we reuse ONICON's vendor ID slot (194) with
our own vendor name; the model/name tell Niagara this is custom.
"""
from __future__ import annotations

import logging

import BAC0
from BAC0.core.devices.local.factory import (
    analog_input,
    analog_value,
    binary_input,
    binary_value,
    ObjectFactory,
)

from ..ahu_physics import AHUState, compute_ahu_state
from ..config import AHUConfig
from ..site_model import SiteModel


log = logging.getLogger(__name__)

METRO_VENDOR_ID = 194       # placeholder — Metro Controls has no registered ID
METRO_VENDOR_NAME = "Metro Controls"
AHU_MODEL_NAME = "AHU-Sim"
AHU_FIRMWARE = "1.0"


# Point definitions. Tuple layout:
#   (obj_kind, instance, name, description, units_or_None)
# Order matters for instance IDs within each object type.
AI_POINTS: list[tuple[int, str, str, str]] = [
    (1, "Supply_Air_Temperature",        "Supply air temperature (F)",        "degreesFahrenheit"),
    (2, "Return_Air_Temperature",        "Return air temperature (F)",        "degreesFahrenheit"),
    (3, "Mixed_Air_Temperature",         "Mixed air temperature (F)",         "degreesFahrenheit"),
    (4, "Outside_Air_Temperature",       "Outside air temperature (F)",       "degreesFahrenheit"),
    (5, "Supply_Air_Static_Pressure",    "Supply air static pressure (inWC)", "inchesOfWater"),
    (6, "Supply_Air_Flow",               "Supply air flow (CFM)",             "cubicFeetPerMinute"),
    (7, "Filter_Differential_Pressure",  "Filter differential pressure (inWC)", "inchesOfWater"),
    (8, "AHU_Real_Power",                "AHU real power (kW) — fan+comp+aux", "kilowatts"),
]

AV_POINTS: list[tuple[int, str, str, str]] = [
    (1, "Supply_Air_Temp_Setpoint",      "Supply air temp setpoint (F)",      "degreesFahrenheit"),
    (2, "Supply_Static_Pressure_Setpoint", "Supply static pressure setpoint (inWC)", "inchesOfWater"),
    # Commandable AVs (spec 02 said AO; doc 04 Flag E overrides to AV)
    (3, "Fan_VFD_Speed_Command",         "Fan VFD speed command (%)",         "percent"),
    (4, "OA_Damper_Position",            "OA damper position (%)",            "percent"),
    (5, "Heating_Valve_Position",        "Heating valve position (%)",        "percent"),
    (6, "Cooling_Stage_DX_Status",       "Cooling stage / DX status (%)",     "percent"),
]

BI_POINTS: list[tuple[int, str, str]] = [
    (1, "Fan_Status",   "Fan status"),
    (2, "Filter_Alarm", "Filter alarm"),
]

BV_POINTS: list[tuple[int, str, str]] = [
    # Commandable BV (spec 02 said BO; doc 04 Flag E overrides to BV)
    (1, "Fan_Start_Stop", "Fan start/stop command"),
]


def _register_ahu_points():
    """Register all 18 AHU objects with BAC0's ObjectFactory.

    Caller MUST call ObjectFactory.clear_objects() before this. Returns the
    last-created factory object so caller can do add_objects_to_application()
    once.
    """
    obj = None
    for instance, name, desc, units in AI_POINTS:
        obj = analog_input(
            name=name,
            instance=instance,
            description=desc,
            presentValue=0.0,
            properties={"units": units},
        )
    for instance, name, desc, units in AV_POINTS:
        obj = analog_value(
            name=name,
            instance=instance,
            description=desc,
            presentValue=0.0,
            properties={"units": units},
        )
    for instance, name, desc in BI_POINTS:
        obj = binary_input(
            name=name,
            instance=instance,
            description=desc,
            presentValue="inactive",
        )
    for instance, name, desc in BV_POINTS:
        obj = binary_value(
            name=name,
            instance=instance,
            description=desc,
            presentValue="inactive",
        )
    return obj


class AHU:
    """One generic AHU BACnet device bound to a specific IP.

    ahu_config: per-instance config row from site_config.json ahus[].
    ahu_index: 0/1/2 — position in SiteState.ahu_sat_f (parallels config order).
    """

    def __init__(
        self,
        device_id: int,
        device_name: str,
        local_ip: str,
        subnet_mask_prefix: int,
        bacnet_port: int,
        site_model: SiteModel,
        ahu_config: AHUConfig,
        ahu_index: int,
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.local_ip = local_ip
        self.bacnet_port = bacnet_port
        self.site = site_model
        self.ahu_config = ahu_config
        self.ahu_index = ahu_index

        ObjectFactory.clear_objects()

        self.bacnet = BAC0.lite(
            ip=f"{local_ip}/{subnet_mask_prefix}",
            port=bacnet_port,
            deviceId=device_id,
            localObjName=device_name,
            vendorId=METRO_VENDOR_ID,
            vendorName=METRO_VENDOR_NAME,
            modelName=AHU_MODEL_NAME,
            firmwareRevision=AHU_FIRMWARE,
            description=f"Metro Controls {AHU_MODEL_NAME} — {device_name} ({ahu_config.kind})",
            location="32K Michigan Office Demo",
        )

        # BAC0 quirk (same as emon/onicon): patch vendorName directly since the
        # kwarg doesn't propagate.
        try:
            bp_app = self.bacnet.this_application.app
            dev_obj = None
            for (otype, inst), obj in bp_app.objectIdentifier.items():
                if inst == device_id and "device" in str(otype).lower():
                    dev_obj = obj
                    break
            if dev_obj is not None:
                dev_obj.vendorName = METRO_VENDOR_NAME
                dev_obj.description = f"Metro Controls {AHU_MODEL_NAME} - {device_name} ({ahu_config.kind})"
            else:
                log.warning(f"{device_name}: device object not found in registry for vendorName patch")
        except Exception as e:
            log.warning(f"{device_name}: could not patch vendorName: {e}")

        last = _register_ahu_points()
        if last is None:
            raise RuntimeError("AHU point creation returned no object")
        last.add_objects_to_application(self.bacnet)

    def update(self) -> None:
        """Refresh all 18 presentValues from the site model via ahu_physics."""
        if self.site.state is None:
            return
        st: AHUState = compute_ahu_state(
            self.ahu_config, self.ahu_index, self.site.state
        )

        # Analog points: set float presentValue
        analog_fields = [name for _, name, _, _ in AI_POINTS] + \
                        [name for _, name, _, _ in AV_POINTS]
        for name in analog_fields:
            try:
                self.bacnet[name].presentValue = float(getattr(st, name))
            except (KeyError, AttributeError) as e:
                log.warning(f"{self.device_name}: failed to update {name}: {e}")

        # Binary points: set "active"/"inactive" string
        binary_fields = [name for _, name, _ in BI_POINTS] + \
                        [name for _, name, _ in BV_POINTS]
        for name in binary_fields:
            try:
                self.bacnet[name].presentValue = getattr(st, name)
            except (KeyError, AttributeError) as e:
                log.warning(f"{self.device_name}: failed to update {name}: {e}")

    def close(self) -> None:
        if self.bacnet is not None:
            try:
                self.bacnet.disconnect()
            except Exception as e:
                log.warning(f"{self.device_name}: disconnect error: {e}")
