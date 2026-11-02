"""Check the QA profile on the wire: every device, and every deliberate fault does what it says.

    .venv\\Scripts\\python.exe scripts\\verify_qa.py [--config qa_config.json] [--client 192.168.100.11]
                                                    [--client-port 47820]

Unicast only: no broadcast Who-Is is sent, so it is safe to run while a Niagara station is bound to
.228 (the client must not be on .228 itself). Per device, from profiles/qa/devices.json:

    normal devices        objectName, vendorIdentifier, modelName and the object count match the profile
    "point_values" nan    those points read NaN
    "no_points"           its object list holds no point objects
    "answer": "iam-only"  a unicast Who-Is gets its I-Am back; a read gets no reply at all
    "reply_delay_ms"      a read takes at least that long (and a normal device's read does not)
    "port"                it answers on that port

Exit code 0 only when every check passes."""
import argparse
import asyncio
import json
import math
import os
import sys
import time

import BAC0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES = {'AI': 'analogInput', 'AO': 'analogOutput', 'AV': 'analogValue', 'BI': 'binaryInput',
         'BO': 'binaryOutput', 'BV': 'binaryValue', 'MSI': 'multiStateInput', 'MSO': 'multiStateOutput',
         'MSV': 'multiStateValue'}
failures = []


def check(what, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + what + (f'   [{detail}]' if detail else ''))
    if not ok:
        failures.append(what)


async def read(bac, addr, what, wait=15.0):
    """(value, seconds); value is None when the device did not answer."""
    t0 = time.monotonic()
    try:
        value = await asyncio.wait_for(bac.read(f'{addr} {what}', timeout=10), wait)
    except Exception:
        value = None
    return value, time.monotonic() - t0


def object_kind(obj_id):
    return str(obj_id[0]).replace('-', '').lower()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=os.path.join(ROOT, 'qa_config.json'))
    ap.add_argument('--client', default='192.168.100.11')
    ap.add_argument('--client-port', type=int, default=47820)
    args = ap.parse_args()
    cfg = json.load(open(args.config, encoding='utf-8'))
    net = cfg['network']
    folder = os.path.join(os.path.dirname(os.path.abspath(args.config)), cfg['profile'])
    prof = json.load(open(os.path.join(folder, 'devices.json'), encoding='utf-8'))
    points_dir = os.path.join(folder, prof.get('points_dir', 'points'))
    lists = {}
    if args.client.endswith('.228'):
        sys.exit('The client must not use .228: that address is the Niagara station\'s.')

    BAC0.log_level('error')
    async with BAC0.start(ip=f"{args.client}/{net['subnet_mask_prefix']}", port=args.client_port) as bac:
        fast = None
        for d in prof['devices']:
            if d['type'] not in lists:
                lists[d['type']] = json.load(open(os.path.join(points_dir, d['type'] + '.json'), encoding='utf-8'))
            points = [] if d.get('no_points') else lists[d['type']]
            ip = f"{net['base_ip']}{net['start_octet'] + d['ip_offset']}"
            port = d.get('port', net['bacnet_port'])
            addr = ip if port == 47808 else f'{ip}:{port}'
            dev = f"device {d['device_id']}"
            label = f"{d['name']:7} {addr:22}"

            if d.get('answer') == 'iam-only':
                try:
                    iams = await bac.who_is(address=addr, timeout=4)
                except Exception:
                    iams = []
                ids = [int(i.iAmDeviceIdentifier[1]) for i in iams or []]
                check(f'{label} answers a unicast Who-Is with its I-Am', d['device_id'] in ids, f'I-Am from {ids}')
                value, secs = await read(bac, addr, f'{dev} objectName')
                check(f'{label} never answers a read', value is None, f'got {value!r} after {secs:.1f} s')
                continue

            name, secs = await read(bac, addr, f'{dev} objectName')
            if name is None:
                check(f'{label} answers', False, f'no reply after {secs:.1f} s')
                continue
            vendor, _ = await read(bac, addr, f'{dev} vendorIdentifier')
            model, _ = await read(bac, addr, f'{dev} modelName')
            objs, _ = await read(bac, addr, f'{dev} objectList')
            pts = [o for o in objs or [] if object_kind(o) not in ('device', 'networkport')]
            check(f'{label} is {d["name"]}, vendor {d["vendor_id"]}, {d["model_name"]}, {len(points)} points',
                  str(name) == d['name'] and int(vendor) == d['vendor_id'] and str(model) == d['model_name']
                  and len(pts) == len(points),
                  f'{name}, {vendor}, {model}, {len(pts)} point objects')

            for pname, pvalue in (d.get('point_values') or {}).items():
                p = next(q for q in points if q['name'] == pname)
                value, _ = await read(bac, addr, f"{TYPES[p['type']]} {p['instance']} presentValue")
                want_nan = str(pvalue).lower() == 'nan'
                ok = value is not None and (math.isnan(float(value)) if want_nan else str(value) == str(pvalue))
                check(f'{label} {pname} reads {pvalue}', ok, f'read {value!r}')

            if d.get('reply_delay_ms'):
                _, secs = await read(bac, addr, f'{dev} objectName')
                want = d['reply_delay_ms'] / 1000.0
                check(f'{label} replies at least {want:.1f} s late', secs >= want, f'{secs:.2f} s')
            elif fast is None:
                _, fast = await read(bac, addr, f'{dev} objectName')
                check(f'{label} replies at once (the delay is per device)', fast < 0.4, f'{fast:.2f} s')

    print()
    print(f'{len(failures)} check(s) failed' if failures else 'All checks passed.')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
