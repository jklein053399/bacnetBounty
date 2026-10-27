"""Point-list device driven by the shared model (profiles/sales).

Same BACnet objects as PointListDevice; update() takes each point's value from shared_points instead
of letting it drift. A model-driven point that is writable gets the value as its relinquish default,
so a write from Niagara at any priority (16 included) wins, and releasing it hands the point back to
the model. Read-only points get the value as their present value.
"""
from __future__ import annotations

import logging

from bacpypes3.primitivedata import Unsigned

from ..shared_model import SharedSiteModel
from ..shared_points import point_value
from .pointlist import PointListDevice

log = logging.getLogger(__name__)


class ModelPointListDevice(PointListDevice):
    def __init__(self, device_type: str, site_model: SharedSiteModel, **kwargs):
        super().__init__(**kwargs)
        self.dtype = device_type
        self.site = site_model

    def update(self) -> None:
        st = self.site.state
        if st is None:
            return
        ts = st.timestamp.timestamp()
        for q in self.points:
            v = point_value(self.dtype, self.device_name, q, st, ts, self.site.seed)
            if v is None:
                continue
            try:
                obj = self.bacnet[q["name"]]
                if q["kind"] in ("BI", "BO", "BV"):
                    v = "active" if v else "inactive"
                elif q["kind"] in ("MSI", "MSO", "MSV"):
                    v = Unsigned(int(v))
                else:
                    v = round(float(v), 2)
                if q["writable"]:
                    obj.relinquishDefault = v
                    obj.recalculating()
                else:
                    obj.presentValue = v
            except Exception as e:
                log.debug(f"{self.device_name}: {q['name']}: {e}")
        for status, command in self.follow.items():
            try:
                self.bacnet[status].presentValue = str(self.bacnet[command].presentValue)
            except Exception as e:
                log.debug(f"{self.device_name}: {status} <- {command}: {e}")
