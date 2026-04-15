"""ONICON F-3500 water meter — BAC0 implementation.

Point list per spec doc 02 section 4. Three Analog Inputs: Flow Rate (GPM),
Totalizer (Gallons), Water Temperature (degF).

One instance = one BACnet device on its own IP. Domestic cold water only
(no irrigation, no cooling tower makeup).

Vendor identifier 194 per ASHRAE BACnet Vendor ID list
(https://bacnet.org/vendorid/) — registered to ONICON Incorporated.
"""
from __future__ import annotations

import logging

import BAC0
from BAC0.core.devices.local.factory import analog_input, ObjectFactory

from ..site_model import SiteModel


log = logging.getLogger(__name__)

ONICON_VENDOR_ID = 194
ONICON_VENDOR_NAME = "ONICON Incorporated"
ONICON_WATER_MODEL_NAME = "F-3500"
ONICON_WATER_FIRMWARE = "3.05"


# (instance, name, description, units) per spec doc 02 section 4
POINTS: list[tuple[int, str, str, str | None]] = [
    (1, "Flow_Rate",         "Water flow rate (GPM)",       "usGallonsPerMinute"),
    (2, "Totalizer",         "Water totalizer (Gallons)",   "usGallons"),
    (3, "Water_Temperature", "Water pipe temperature (F)",  "degreesFahrenheit"),
]


def _create_onicon_water_points():
    """Register the 3 AIs with BAC0's ObjectFactory.

    Returns the last-created factory object so caller can do
    `add_objects_to_application(bacnet)` once. Caller MUST call
    ObjectFactory.clear_objects() before this if multiple devices are
    being built in the same process.
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


class OniconF3500Water:
    """One ONICON F-3500 water meter BACnet device bound to a specific IP."""

    def __init__(
        self,
        device_id: int,
        device_name: str,
        local_ip: str,
        subnet_mask_prefix: int,
        bacnet_port: int,
        site_model: SiteModel,
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.local_ip = local_ip
        self.bacnet_port = bacnet_port
        self.site = site_model

        # Multi-device pattern: clear any points carried over from a prior device
        ObjectFactory.clear_objects()

        self.bacnet = BAC0.lite(
            ip=f"{local_ip}/{subnet_mask_prefix}",
            port=bacnet_port,
            deviceId=device_id,
            localObjName=device_name,
            vendorId=ONICON_VENDOR_ID,
            vendorName=ONICON_VENDOR_NAME,
            modelName=ONICON_WATER_MODEL_NAME,
            firmwareRevision=ONICON_WATER_FIRMWARE,
            description=f"ONICON F-3500 water meter — {device_name}",
            location="32K Michigan Office Demo",
        )

        # BAC0 quirk (same as emon): vendorName kwarg doesn't propagate to the
        # DeviceObject on the wire. Patch directly after construction.
        try:
            bp_app = self.bacnet.this_application.app
            dev_obj = None
            for (otype, inst), obj in bp_app.objectIdentifier.items():
                if inst == device_id and "device" in str(otype).lower():
                    dev_obj = obj
                    break
            if dev_obj is not None:
                dev_obj.vendorName = ONICON_VENDOR_NAME
                dev_obj.description = f"ONICON F-3500 water meter - {device_name}"
            else:
                log.warning(f"{device_name}: device object not found in registry for vendorName patch")
        except Exception as e:
            log.warning(f"{device_name}: could not patch vendorName: {e}")

        last = _create_onicon_water_points()
        if last is None:
            raise RuntimeError("ONICON water point creation returned no object")
        last.add_objects_to_application(self.bacnet)

    def update(self) -> None:
        """Refresh all 3 AI presentValues from the SiteModel."""
        s = self.site.state
        if s is None:
            return

        values: dict[str, float] = {
            "Flow_Rate":         s.water_gpm,
            "Totalizer":         s.water_gallons_total,
            "Water_Temperature": s.water_temp_f,
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
