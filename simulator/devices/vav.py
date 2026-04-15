"""Generic VAV BACnet device — BAC0 implementation.

Point list per spec 02 §6 (with AV/BV substitutions per doc 04 Flag E).
Twenty instances in the manifest (VAV_1..VAV_20). All share this class;
per-instance behavior is driven off VAVConfig.

Physics lives in simulator/vav_physics.py (architectural invariant #2).
"""
from __future__ import annotations

import logging

import BAC0
from BAC0.core.devices.local.factory import (
    analog_input,
    analog_value,
    binary_input,
    ObjectFactory,
)

from ..config import VAVConfig
from ..site_model import SiteModel
from ..vav_physics import VAVState, compute_vav_state


log = logging.getLogger(__name__)

METRO_VENDOR_ID = 194
METRO_VENDOR_NAME = "Metro Controls"
VAV_MODEL_NAME = "VAV-Sim"
VAV_FIRMWARE = "1.0"


AI_POINTS: list[tuple[int, str, str, str]] = [
    (1, "Zone_Temperature",          "Zone temperature (F)",           "degreesFahrenheit"),
    (2, "Supply_Airflow",            "Supply airflow (CFM)",           "cubicFeetPerMinute"),
    (3, "Discharge_Air_Temperature", "Discharge air temperature (F)",  "degreesFahrenheit"),
]

AV_POINTS: list[tuple[int, str, str, str]] = [
    (1, "Occupied_Cooling_Setpoint", "Occupied cooling setpoint (F)",  "degreesFahrenheit"),
    (2, "Occupied_Heating_Setpoint", "Occupied heating setpoint (F)",  "degreesFahrenheit"),
    (3, "Airflow_Setpoint",          "Airflow setpoint (CFM)",         "cubicFeetPerMinute"),
    # Commandable (spec 02 §6 said AO; doc 04 Flag E overrides to AV)
    (4, "Damper_Position",           "Damper position (%)",            "percent"),
    (5, "Reheat_Valve_Position",     "Reheat valve position (%)",      "percent"),
]

BI_POINTS: list[tuple[int, str, str]] = [
    (1, "Occupancy_Status", "Zone occupancy status"),
]


def _register_vav_points():
    """Register all 9 VAV objects with BAC0's ObjectFactory."""
    obj = None
    for instance, name, desc, units in AI_POINTS:
        obj = analog_input(
            name=name, instance=instance, description=desc,
            presentValue=0.0, properties={"units": units},
        )
    for instance, name, desc, units in AV_POINTS:
        obj = analog_value(
            name=name, instance=instance, description=desc,
            presentValue=0.0, properties={"units": units},
        )
    for instance, name, desc in BI_POINTS:
        obj = binary_input(
            name=name, instance=instance, description=desc,
            presentValue="inactive",
        )
    return obj


class VAV:
    """One generic VAV BACnet device bound to a specific IP.

    vav_config: per-instance config row from site_config.json vavs[].
    vav_index: 0..19 — position in SiteState.vav_valve_positions /
               vav_zone_temps_f tuples (parallel to config order).
    """

    def __init__(
        self,
        device_id: int,
        device_name: str,
        local_ip: str,
        subnet_mask_prefix: int,
        bacnet_port: int,
        site_model: SiteModel,
        vav_config: VAVConfig,
        vav_index: int,
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.local_ip = local_ip
        self.bacnet_port = bacnet_port
        self.site = site_model
        self.vav_config = vav_config
        self.vav_index = vav_index

        ObjectFactory.clear_objects()

        self.bacnet = BAC0.lite(
            ip=f"{local_ip}/{subnet_mask_prefix}",
            port=bacnet_port,
            deviceId=device_id,
            localObjName=device_name,
            vendorId=METRO_VENDOR_ID,
            vendorName=METRO_VENDOR_NAME,
            modelName=VAV_MODEL_NAME,
            firmwareRevision=VAV_FIRMWARE,
            description=f"Metro Controls {VAV_MODEL_NAME} — {device_name} "
                        f"({vav_config.position}, parent {vav_config.parent_ahu})",
            location="32K Michigan Office Demo",
        )

        try:
            bp_app = self.bacnet.this_application.app
            dev_obj = None
            for (otype, inst), obj in bp_app.objectIdentifier.items():
                if inst == device_id and "device" in str(otype).lower():
                    dev_obj = obj
                    break
            if dev_obj is not None:
                dev_obj.vendorName = METRO_VENDOR_NAME
                dev_obj.description = f"Metro Controls {VAV_MODEL_NAME} - {device_name}"
            else:
                log.warning(f"{device_name}: device object not found for vendorName patch")
        except Exception as e:
            log.warning(f"{device_name}: could not patch vendorName: {e}")

        last = _register_vav_points()
        if last is None:
            raise RuntimeError("VAV point creation returned no object")
        last.add_objects_to_application(self.bacnet)

    def update(self) -> None:
        """Refresh all 9 presentValues via vav_physics."""
        if self.site.state is None:
            return
        st: VAVState = compute_vav_state(self.vav_config, self.vav_index, self.site.state)

        analog_fields = [name for _, name, _, _ in AI_POINTS] + \
                        [name for _, name, _, _ in AV_POINTS]
        for name in analog_fields:
            try:
                self.bacnet[name].presentValue = float(getattr(st, name))
            except (KeyError, AttributeError) as e:
                log.warning(f"{self.device_name}: failed to update {name}: {e}")

        for _, name, _ in BI_POINTS:
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
