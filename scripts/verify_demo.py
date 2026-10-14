"""Check the demo profile on the wire, from a BACnet client on another address.

    .venv\\Scripts\\python.exe scripts\\verify_demo.py [client-ip]      (default 192.168.100.11, port 47809)

Who-Is; every device's vendor, model and object count; a measured value drifting; a write to a fan
command at priority 8 and its status following it on the next tick; the write released after."""
import asyncio
import sys

import BAC0

CLIENT = sys.argv[1] if len(sys.argv) > 1 else '192.168.100.11'
NET = '192.168.100.'


async def main():
    BAC0.log_level('error')
    async with BAC0.start(ip=f'{CLIENT}/24', port=47809) as bac:
        found = await bac.who_is()
        ids = sorted(int(str(i.iAmDeviceIdentifier[1])) for i in found)
        print(f'Who-Is: {len(ids)} devices answered: {ids}')
        for dev_id in ids:
            ip = f'{NET}{200 + _offset(dev_id)}'
            name = await bac.read(f'{ip} device {dev_id} objectName')
            vendor = await bac.read(f'{ip} device {dev_id} vendorName')
            model = await bac.read(f'{ip} device {dev_id} modelName')
            objs = await bac.read(f'{ip} device {dev_id} objectList')
            print(f'  {dev_id} {str(name):8} {ip:16} {vendor} | {model} | {len(objs) - 1} objects')
        # drift: RTU_1 supply air temperature, twice, a tick apart
        rtu = f'{NET}200'
        a = await bac.read(f'{rtu} analogInput 1 presentValue')
        await asyncio.sleep(11)
        b = await bac.read(f'{rtu} analogInput 1 presentValue')
        print(f'RTU_1 AI1 drifts: {a} -> {b}')
        # command and status: EF_1 (offset 14)
        ef = f'{NET}214'
        objs = await bac.read(f'{ef} device 500001 objectList')
        print('EF_1 objects:', [str(o) for o in objs])
        bo = next(o for o in objs if 'binary-output' in str(o).lower() or 'binaryoutput' in str(o).lower())
        bi = next(o for o in objs if 'binary-input' in str(o).lower() or 'binaryinput' in str(o).lower())
        bo_t, bo_i = str(bo[0]), int(bo[1])
        bi_t, bi_i = str(bi[0]), int(bi[1])
        before = await bac.read(f'{ef} {bi_t} {bi_i} presentValue')
        await bac._write(f'{ef} {bo_t} {bo_i} presentValue inactive - 8')
        await asyncio.sleep(11)
        after = await bac.read(f'{ef} {bi_t} {bi_i} presentValue')
        pa = await bac.read(f'{ef} {bo_t} {bo_i} priorityArray')
        print(f'EF_1 command written inactive @8: status {before} -> {after}; priority 8 holds {pa[7] if pa else pa}')
        await bac._write(f'{ef} {bo_t} {bo_i} presentValue null - 8')
        await asyncio.sleep(11)
        print('EF_1 released: status', await bac.read(f'{ef} {bi_t} {bi_i} presentValue'))


def _offset(dev_id):
    import json
    import os
    prof = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'profiles', 'demo', 'devices.json')))
    return next(d['ip_offset'] for d in prof['devices'] if d['device_id'] == dev_id)


if __name__ == '__main__':
    asyncio.run(main())
