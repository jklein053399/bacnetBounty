"""Turn the demo point-list workbook into the simulator's demo profile.

    .venv\\Scripts\\python.exe scripts\\import_demo_points.py <Demo_Device_Points.xlsx> [profiles\\demo]

Reads the workbook's "Read me" sheet (one row per demo device type: count, controller, vendor) and
each type's sheet (only rows with Keep = Y), and writes:
    profiles/demo/devices.json         the device list: names, BACnet device IDs, IP offsets, vendor
    profiles/demo/points/<TYPE>.json   the points of that type
Run it again whenever the workbook changes, then restart the simulator.
"""
import json
import os
import re
import sys

import openpyxl

ORDER = ['RTU', 'AHU', 'CHWS', 'HWS', 'VAV', 'EF', 'CUH']     # IP and device-ID order
ID_BASE = {'AHU': 200000, 'VAV': 300000, 'RTU': 400000, 'EF': 500000, 'CUH': 600000, 'CHWS': 700000, 'HWS': 800000}


def main():
    xlsx = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'profiles', 'demo')
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    types = {}
    for row in wb['Read me'].iter_rows(values_only=True):
        if row and row[0] in ORDER and row[2]:
            types[row[0]] = {'count': int(row[1]), 'model': row[2], 'vendor_name': row[3], 'vendor_id': int(row[4])}
    os.makedirs(os.path.join(out, 'points'), exist_ok=True)
    devices, offset = [], 0
    for typ in ORDER:
        if typ not in types or typ not in wb.sheetnames:
            continue
        ws = wb[typ]
        head = [c.value for c in ws[1]]
        col = {h: i for i, h in enumerate(head)}
        pts = []
        for r in ws.iter_rows(min_row=2, values_only=True):
            if not r[col['Point name']] or str(r[col['Keep']] or 'Y').strip().upper() != 'Y':
                continue
            obj = str(r[col['BACnet object']] or '')
            if ':' not in obj:
                print(f'  {typ}: "{r[col["Point name"]]}" has no BACnet object ({obj!r}); left out')
                continue
            states = str(r[col['States']] or '')
            sep = ' / ' if ' / ' in states else ', '
            pts.append({'name': str(r[col['Point name']]).strip(), 'type': r[col['Type']], 'instance': int(re.match(r'\d+', obj.split(':')[1]).group(0)),
                        'units': r[col['Units']] or '', 'states': [s.strip() for s in states.split(sep)] if states else [],
                        'writable': str(r[col['Writable']] or '').upper() == 'Y', 'value': str(r[col['Demo value']] if r[col['Demo value']] is not None else '0')})
        json.dump(pts, open(os.path.join(out, 'points', f'{typ}.json'), 'w', encoding='utf-8'), indent=1)
        t = types[typ]
        for i in range(1, t['count'] + 1):
            devices.append({'name': f'{typ}_{i}', 'type': typ, 'device_id': ID_BASE[typ] + i, 'ip_offset': offset,
                            'vendor_id': t['vendor_id'], 'vendor_name': t['vendor_name'], 'model_name': t['model']})
            offset += 1
        print(f'{typ}: {t["count"]} x {t["model"]} ({t["vendor_name"]}), {len(pts)} points')
    json.dump({'location': 'Metro PX demo', 'devices': devices}, open(os.path.join(out, 'devices.json'), 'w', encoding='utf-8'), indent=1)
    print(f'{len(devices)} devices -> {out}')


if __name__ == '__main__':
    main()
