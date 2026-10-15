"""Point-list BACnet device: any controller, built from a list of its real points.

Used by profiles (see profiles/demo/): each device copies a controller integrated on a real job,
with its object names, object types and instances, units and state texts, and reports that
controller's vendor and model in its device object. Nothing about the equipment is modelled; the
values only have to look right on a graphic:

    measured values (AI, and AV that is not writable) drift a little around their starting value
    writable objects (AO, BO, MSO and writable AV, BV, MSV) are commandable and stay where written
    a binary status follows its command when the names pair up (SF-S with SF-C, Fan_Status with
    Fan_Command ...), otherwise it stays put; alarms start Normal

Point record (profiles/<name>/points/<TYPE>.json):
    {"name": "ZN-T", "type": "AI", "instance": 1, "units": "fahrenheit", "states": [],
     "writable": false, "value": "72.0"}
"""
from __future__ import annotations

import logging
import random
import re

import BAC0
from BAC0.core.devices.local.factory import (
    ObjectFactory,
    analog_input,
    analog_output,
    analog_value,
    binary_input,
    binary_output,
    binary_value,
    make_state_text,
    multistate_input,
    multistate_output,
    multistate_value,
)
from bacpypes3.primitivedata import Unsigned
from bacpypes3.service.object import ReadWritePropertyServices


log = logging.getLogger(__name__)


# BACnet: a WriteProperty with no priority on a commandable property is a write at priority 16.
# bacpypes3 only accepts a NULL (a release) when a priority is given, so Niagara's release at 16,
# which leaves the priority out, came back "REJECT: invalid Tag" and faulted every writable point.
_write_property = ReadWritePropertyServices.do_WritePropertyRequest


async def _write_property_default_16(self, apdu):
    if apdu.priority is None and str(apdu.propertyIdentifier) == 'present-value':
        try:
            obj = self.get_object_id(apdu.objectIdentifier)
            if obj is not None and getattr(obj, 'priorityArray', None) is not None:
                apdu.priority = 16
        except Exception as e:                       # never let the check itself fail the request
            log.debug(f'priority check: {e}')
    return await _write_property(self, apdu)


ReadWritePropertyServices.do_WritePropertyRequest = _write_property_default_16

# Niagara unit names (as integrated) -> BACnet engineering units
UNITS = {
    'fahrenheit': 'degreesFahrenheit', 'celsius': 'degreesCelsius', 'percent': 'percent',
    'percent relative humidity': 'percentRelativeHumidity', 'parts per million': 'partsPerMillion',
    'cubic feet per minute': 'cubicFeetPerMinute', 'inches of water': 'inchesOfWater',
    'pounds per square inch': 'poundsForcePerSquareInch', 'gallons per minute': 'usGallonsPerMinute',
    'kilowatt': 'kilowatts', 'kilowatts': 'kilowatts', 'kilowatt hour': 'kilowattHours', 'hour': 'hours',
    'hours': 'hours', 'volt': 'volts', 'ampere': 'amperes', 'hertz': 'hertz', 'second': 'seconds',
    'minute': 'minutes', 'feet per minute': 'feetPerMinute', 'btu per hour': 'btusPerHour',
}
ANALOG = {'AI': analog_input, 'AO': analog_output, 'AV': analog_value}
BINARY = {'BI': binary_input, 'BO': binary_output, 'BV': binary_value}
MULTI = {'MSI': multistate_input, 'MSO': multistate_output, 'MSV': multistate_value}
ALWAYS_WRITABLE = ('AO', 'BO', 'MSO')
STATUS_TAIL = re.compile(r'([-_ ]?(S|STS|STAT|STATUS|Status|Sts))$')
COMMAND_TAIL = re.compile(r'([-_ ]?(C|CMD|COMMAND|Command|Cmd|O|SS))$')


def stem(name: str, tail: re.Pattern) -> str | None:
    m = tail.search(name)
    return name[:m.start()].lower() if m else None


def unescape(text: str) -> str:
    """Niagara slot escapes in state texts: $20 space, $2d '-', $2b '+' ..."""
    return re.sub(r'\$([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), text)


class PointListDevice:
    def __init__(self, device_id: int, device_name: str, local_ip: str, subnet_mask_prefix: int, bacnet_port: int,
                 vendor_id: int, vendor_name: str, model_name: str, points: list[dict], description: str = '',
                 location: str = '', seed: int = 0, **_ignored):
        self.device_id, self.device_name = device_id, device_name
        self.rng = random.Random(seed or device_id)
        ObjectFactory.clear_objects()
        self.bacnet = BAC0.lite(
            ip=f'{local_ip}/{subnet_mask_prefix}', port=bacnet_port, deviceId=device_id, localObjName=device_name,
            vendorId=vendor_id, vendorName=vendor_name, modelName=model_name, firmwareRevision='demo',
            description=description or f'{model_name} {device_name}', location=location)
        try:      # BAC0 does not pass vendorName on to the device object (same patch as the other devices)
            app = self.bacnet.this_application.app
            for (otype, inst), obj in app.objectIdentifier.items():
                if inst == device_id and 'device' in str(otype).lower():
                    obj.vendorName = vendor_name
                    break
        except Exception as e:
            log.warning(f'{device_name}: could not set vendorName: {e}')

        self.points, seen, last = [], set(), None
        for p in points:
            kind, inst = p['type'], int(p['instance'])
            if (kind, inst) in seen:
                log.warning(f'{device_name}: {kind}:{inst} defined twice; "{p["name"]}" left out')
                continue
            seen.add((kind, inst))
            writable = bool(p.get('writable')) or kind in ALWAYS_WRITABLE
            commandable = writable and kind not in ALWAYS_WRITABLE     # AO/BO/MSO already have a priority array
            desc = p.get('description') or p['name']
            states = [unescape(s) for s in p.get('states') or []]
            try:
                if kind in ANALOG:
                    v = float(p.get('value') or 0)
                    last = ANALOG[kind](name=p['name'], instance=inst, description=desc, presentValue=v,
                                        is_commandable=commandable,
                                        properties={'units': UNITS.get((p.get('units') or '').lower(), 'noUnits')})
                elif kind in BINARY:
                    on = str(p.get('value')).lower() in ('true', '1', 'active', 'on')
                    props = {}
                    if len(states) == 2:
                        props = {'inactiveText': states[0], 'activeText': states[1]}
                    last = BINARY[kind](name=p['name'], instance=inst, description=desc,
                                        presentValue='active' if on else 'inactive', is_commandable=commandable,
                                        properties=props)
                elif kind in MULTI:
                    texts = states or ['State 1', 'State 2']
                    v = max(1, min(len(texts), int(float(p.get('value') or 1))))
                    last = MULTI[kind](name=p['name'], instance=inst, description=desc, presentValue=Unsigned(v),
                                       is_commandable=commandable,
                                       properties={'stateText': make_state_text(texts), 'numberOfStates': Unsigned(len(texts))})
                else:
                    log.warning(f'{device_name}: "{p["name"]}" has object type {kind!r}; left out')
                    continue
            except Exception as e:
                log.warning(f'{device_name}: could not create "{p["name"]}" ({kind}:{inst}): {e}')
                continue
            base = float(p.get('value') or 0) if kind in ANALOG else 0.0
            self.points.append({'name': p['name'], 'kind': kind, 'writable': writable, 'base': base,
                                'drift': kind == 'AI' or (kind == 'AV' and not writable)})
        if last is None:
            raise RuntimeError(f'{device_name}: no points')
        last.add_objects_to_application(self.bacnet)

        # statuses that follow a command
        commands = {stem(q['name'], COMMAND_TAIL): q['name'] for q in self.points
                    if q['kind'] in ('BO', 'BV') and q['writable'] and stem(q['name'], COMMAND_TAIL)}
        self.follow = {}
        for q in self.points:
            s = stem(q['name'], STATUS_TAIL) if q['kind'] in ('BI', 'BV') and not q['writable'] else None
            if s and s in commands:
                self.follow[q['name']] = commands[s]
        log.debug(f'{device_name}: {len(self.points)} objects, {len(self.follow)} statuses follow a command')

    def update(self) -> None:
        for q in self.points:
            if not q['drift'] or q['base'] == 0:
                continue
            span = 1.5 if abs(q['base']) < 200 else abs(q['base']) * 0.01
            try:
                obj = self.bacnet[q['name']]
                now = float(obj.presentValue)
                step = self.rng.uniform(-0.15, 0.15) * span
                pull = (q['base'] - now) * 0.1                       # stay near the starting value
                obj.presentValue = round(now + step + pull, 2)
            except Exception as e:
                log.debug(f'{self.device_name}: {q["name"]}: {e}')
        for status, command in self.follow.items():
            try:
                self.bacnet[status].presentValue = str(self.bacnet[command].presentValue)
            except Exception as e:
                log.debug(f'{self.device_name}: {status} <- {command}: {e}')

    def close(self) -> None:
        try:
            self.bacnet.disconnect()
        except Exception as e:
            log.warning(f'{self.device_name}: disconnect error: {e}')
